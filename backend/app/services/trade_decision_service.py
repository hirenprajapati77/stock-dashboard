from __future__ import annotations

from typing import Any
import logging
import math

from app.engine.regime import MarketRegimeEngine


logger = logging.getLogger(__name__)


class TradeDecisionService:
    """
    Execution-layer annotation service.
    Promotes only the best validated BUY setups into a prioritized execution list.
    """

    DEFAULT_ACCOUNT_BALANCE = 100000.0
    DEFAULT_RISK_PCT = 0.01

    MIN_TREND_ADX = 20.0
    MIN_VALID_CONFIDENCE = 50.0
    WATCH_CONFIDENCE = 60.0
    BUY_CONFIDENCE = 70.0
    BUY_RR = 1.5
    SAFE_TOP_PICK_CONFIDENCE = 70.0
    SAFE_TOP_PICK_RR = 2.0
    AGGRESSIVE_TOP_PICK_CONFIDENCE = 65.0
    AGGRESSIVE_TOP_PICK_RR = 1.5
    MAX_TOP_TRADES = 3

    @classmethod
    def annotate_many(
        cls,
        hits: list[dict[str, Any]],
        account_balance: float = DEFAULT_ACCOUNT_BALANCE,
        risk_pct: float = DEFAULT_RISK_PCT,
        mode: str = "safe",
    ) -> list[dict[str, Any]]:
        adaptive_intelligence = cls._load_adaptive_intelligence()
        out: list[dict[str, Any]] = []
        for hit in hits or []:
            row = dict(hit)
            try:
                decision_data = cls.compute_trade_score(row, adaptive_intelligence=adaptive_intelligence)
                row.update(decision_data)
                plan = cls.build_plan(row, account_balance=account_balance, risk_pct=risk_pct)
            except Exception:  # pragma: no cover - defensive fail-safe
                logger.exception("Trade annotation failed for %s", row.get("symbol", "<unknown>"))
                decision_data = cls._system_failure_payload()
                row.update(decision_data)
                plan = cls._invalid_plan(account_balance=account_balance, risk_pct=risk_pct)

            row["executionPlan"] = plan
            row["tradeDecisionTag"] = decision_data.get("action", plan.get("tradeTag", "NO TRADE"))
            row["executeLabel"] = "Execute Plan" if row.get("action") == "BUY" else None
            row["userMode"] = str(mode).lower()
            cls._apply_trade_contract(row, plan)
            out.append(row)
        return out

    @classmethod
    def derive_market_context(cls, hits: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(hits or [])
        if total == 0:
            return {
                "regime": "RANGE",
                "sectorAlignment": "WEAK",
                "lowConviction": True,
                "message": "Low conviction market. Trade cautiously.",
            }

        aligned = sum(1 for h in hits if str(h.get("sectorState") or "").upper() in {"LEADING", "IMPROVING"})
        strong_momentum = sum(1 for h in hits if str((h.get("technical") or {}).get("momentumStrength") or "").upper() == "STRONG")
        buy_ready = sum(1 for h in hits if str(h.get("action") or "").upper() == "BUY")

        alignment_ratio = aligned / total
        momentum_ratio = strong_momentum / total
        buy_ratio = buy_ready / total

        if alignment_ratio >= 0.55 and momentum_ratio >= 0.35 and buy_ratio >= 0.2:
            regime = "TREND"
            sector_alignment = "STRONG"
            low_conviction = False
            message = "Market regime is supportive with strong sector alignment. Top trades can be executed if confirmation holds."
        elif alignment_ratio >= 0.35 and buy_ratio >= 0.1:
            regime = "NEUTRAL"
            sector_alignment = "MIXED"
            low_conviction = False
            message = "Market participation is mixed. Prioritize only the cleanest setups."
        else:
            regime = "RANGE"
            sector_alignment = "WEAK"
            low_conviction = True
            message = "Low conviction market. Trade cautiously."

        return {
            "regime": regime,
            "sectorAlignment": sector_alignment,
            "lowConviction": low_conviction,
            "message": message,
        }

    @classmethod
    def select_top_trades(
        cls,
        hits: list[dict[str, Any]],
        mode: str = "safe",
        market_context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        mode = str(mode or "safe").lower()
        market_context = market_context or cls.derive_market_context(hits)
        low_conviction = bool(market_context.get("lowConviction"))

        if mode == "aggressive":
            min_confidence = cls.AGGRESSIVE_TOP_PICK_CONFIDENCE
            min_rr = cls.AGGRESSIVE_TOP_PICK_RR
        else:
            min_confidence = cls.SAFE_TOP_PICK_CONFIDENCE
            min_rr = cls.SAFE_TOP_PICK_RR

        if low_conviction and mode == "safe":
            min_confidence = max(min_confidence, 78.0)
            min_rr = max(min_rr, 2.2)

        ranked: list[dict[str, Any]] = []
        for hit in hits or []:
            action = str(hit.get("action") or "NO TRADE").upper()
            confidence = cls._f(hit.get("confidence"))
            rr = cls._f(hit.get("executionPlan", {}).get("riskRewardToT1") or hit.get("rr"))
            sector_state = str(hit.get("sectorState") or "NEUTRAL").upper()
            adaptive_thresholds = hit.get("adaptiveThresholds") or {}
            min_confidence_for_hit = max(min_confidence, cls._f(adaptive_thresholds.get("topPickConfidence") or 0))
            min_rr_for_hit = max(min_rr, cls._f(adaptive_thresholds.get("topPickRR") or 0))
            if action != "BUY" or confidence < min_confidence_for_hit or rr < min_rr_for_hit:
                continue
            if mode == "safe" and sector_state not in {"LEADING", "IMPROVING"}:
                continue
            if low_conviction and sector_state != "LEADING":
                continue
            row = dict(hit)
            row["modeQualified"] = mode
            ranked.append(row)

        ranked.sort(key=lambda item: (
            cls._f(item.get("score")),
            cls._f(item.get("confidence")),
            cls._f((item.get("trustSignals") or {}).get("performanceMultiplier") or 1.0),
            cls._f(item.get("executionPlan", {}).get("riskRewardToT1") or item.get("rr")),
        ), reverse=True)

        top = []
        for idx, hit in enumerate(ranked[: cls.MAX_TOP_TRADES], start=1):
            row = dict(hit)
            row["topTradeRank"] = idx
            row["isTopTrade"] = True
            row["marketContext"] = market_context
            logger.info(
                "Selected top trade #%s for %s with score=%s confidence=%s rr=%s",
                idx,
                row.get("symbol", "<unknown>"),
                row.get("score"),
                row.get("confidence"),
                row.get("executionPlan", {}).get("riskRewardToT1") or row.get("rr"),
            )
            top.append(row)
        return top

    @classmethod
    def compute_trade_score(
        cls,
        hit: dict[str, Any],
        *,
        adaptive_intelligence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            tech = hit.get("technical") or {}
            insights = hit.get("insights") or {}
            summary = hit.get("summary") or {}
            meta = hit.get("meta") or {}
            adaptive_intelligence = adaptive_intelligence or cls._load_adaptive_intelligence()

            entry = cls._f(hit.get("price") or summary.get("entry") or summary.get("cmp") or meta.get("cmp"))
            adx = cls._f(hit.get("adx") or tech.get("adx") or insights.get("adx") or summary.get("adx"))
            retest = bool(hit.get("retest") or tech.get("retest") or insights.get("retest"))
            breakout = bool(tech.get("isBreakout") or tech.get("breakout") or insights.get("breakout"))
            setup_type = cls._detect_setup(retest, breakout)
            sector_label = str(hit.get("sector") or hit.get("sectorName") or "UNKNOWN").upper()

            support, resistance, sr_sources = cls._resolve_support_resistance(hit, entry)
            stop_loss = cls._f(hit.get("stopLoss") or summary.get("stop_loss"))
            target = cls._f(hit.get("target") or summary.get("target"))
            if stop_loss <= 0 and support > 0 and entry > support:
                stop_loss = max(0.0, support * 0.995)
            if target <= 0 and resistance > entry:
                target = resistance

            rr = 0.0
            if entry > 0 and stop_loss > 0 and entry > stop_loss:
                risk = entry - stop_loss
                reward = target - entry if target > entry else (risk * 2.0)
                rr = reward / risk if risk > 0 else 0.0

            vol_ratio = cls._f(hit.get("volRatio") or hit.get("volume_ratio") or tech.get("volRatio"))
            momentum_strength = str(tech.get("momentumStrength") or "WEAK").upper()
            vol_high = bool(tech.get("volHigh"))
            sector_state = str(hit.get("sectorState") or hit.get("sector_info", {}).get("state") or "NEUTRAL").upper()
            regime = str(summary.get("market_regime") or hit.get("marketRegime") or "STABLE").upper()

            trend_points = 20 if adx >= 25 else 10 if adx >= cls.MIN_TREND_ADX else 0
            setup_points = 20 if setup_type == "BREAKOUT_RETEST" else 12 if setup_type != "NONE" else 0
            volume_points = 15 if vol_ratio >= 1.5 else 10 if vol_ratio >= 1.0 else 5
            rr_points = 15 if rr >= 2.0 else 10 if rr >= cls.BUY_RR else 5 if rr >= 1.0 else 0
            sr_points = cls._support_resistance_points(entry, support, resistance)
            momentum_points = 10 if momentum_strength == "STRONG" else 5 if momentum_strength == "MODERATE" else 2
            volatility_points = 5 if vol_high else 10
            sector_points = 5 if sector_state in {"LEADING", "IMPROVING"} else 0
            regime_penalty = -10 if regime in {"RANGE", "WEAK_TREND", "RISK-OFF"} else 0

            base_confidence = float(min(100.0, max(0.0, trend_points + setup_points + volume_points + rr_points + sr_points + momentum_points + volatility_points + sector_points + regime_penalty)))
            thresholds = adaptive_intelligence.get("thresholds", {}) if isinstance(adaptive_intelligence, dict) else {}
            setup_profile = cls._lookup_profile((adaptive_intelligence or {}).get("setupProfiles"), setup_type)
            sector_profile = cls._lookup_profile((adaptive_intelligence or {}).get("sectorProfiles"), sector_label)
            setup_weight = cls._f(setup_profile.get("weight") or 1.0)
            sector_weight = cls._f(sector_profile.get("weight") or 1.0)
            setup_win_rate = cls._f(setup_profile.get("winRate") or 50.0)
            sector_win_rate = cls._f(sector_profile.get("winRate") or 50.0)
            sector_recent_pnl = cls._f(sector_profile.get("recentPnLPct") or sector_profile.get("avgPnLPct"))
            setup_multiplier_weight = 0.45 * max(0.0, setup_weight - 0.75)
            sector_multiplier_weight = 0.35 * max(0.0, sector_weight - 0.75)
            performance_multiplier = cls._clamp(
                1.0
                + (((setup_win_rate - 50.0) / 100.0) * setup_multiplier_weight)
                + (((sector_win_rate - 50.0) / 100.0) * sector_multiplier_weight),
                0.8,
                1.3,
            )
            confidence_adjustment = cls._clamp(
                cls._f(setup_profile.get("confidenceAdjustment"))
                + (cls._f(sector_profile.get("confidenceAdjustment")) * 0.5),
                -12.0,
                12.0,
            )
            confidence = cls._clamp(base_confidence + confidence_adjustment, 0.0, 100.0)

            validation_reasons: list[str] = []
            if support <= 0:
                validation_reasons.append("No valid support/resistance: support could not be confirmed.")
            if resistance <= 0:
                validation_reasons.append("No valid support/resistance: resistance could not be confirmed.")
            if setup_type == "NONE":
                validation_reasons.append("No setup confirmation: neither breakout nor retest is present.")
            if adx < cls.MIN_TREND_ADX:
                validation_reasons.append(f"Weak trend: ADX {adx:.1f} is below the {int(cls.MIN_TREND_ADX)} threshold.")
            if regime in {"RANGE", "WEAK_TREND", "RISK-OFF"}:
                validation_reasons.append("Market regime is not fully supportive for aggressive execution.")

            is_valid_trade = not any(reason.startswith(("No valid support/resistance", "No setup confirmation", "Weak trend")) for reason in validation_reasons)
            min_valid_confidence = max(cls.MIN_VALID_CONFIDENCE, cls._f(thresholds.get("watchConfidence") or cls.MIN_VALID_CONFIDENCE - 5))
            buy_confidence_threshold = max(cls.BUY_CONFIDENCE, cls._f(thresholds.get("buyConfidence") or cls.BUY_CONFIDENCE))
            watch_confidence_threshold = max(cls.WATCH_CONFIDENCE, cls._f(thresholds.get("watchConfidence") or cls.WATCH_CONFIDENCE))
            adaptive_top_pick_confidence = max(cls.SAFE_TOP_PICK_CONFIDENCE, cls._f(thresholds.get("topPickConfidence") or cls.SAFE_TOP_PICK_CONFIDENCE))
            adaptive_top_pick_rr = max(cls.SAFE_TOP_PICK_RR, cls._f(thresholds.get("topPickRR") or cls.SAFE_TOP_PICK_RR))

            if confidence < min_valid_confidence:
                validation_reasons.append("Low confidence: score is below the minimum actionable threshold.")
                is_valid_trade = False

            if not is_valid_trade:
                action = "NO TRADE"
                confidence = min(confidence, 45.0)
            elif confidence >= buy_confidence_threshold and rr >= cls.BUY_RR:
                action = "BUY"
            elif confidence >= watch_confidence_threshold:
                action = "WATCH"
            else:
                action = "NO TRADE"
                confidence = min(confidence, 45.0)
                validation_reasons.append("Low confidence: setup quality is not strong enough for execution.")
                is_valid_trade = False

            trend_strength_score = cls._trend_strength_score(adx)
            risk_reward_score = cls._risk_reward_score(rr)
            setup_quality_score = cls._setup_quality_score(setup_type, vol_ratio)
            base_score = float(round(
                (confidence * 0.4)
                + (risk_reward_score * 0.2)
                + (trend_strength_score * 0.2)
                + (setup_quality_score * 0.2),
                2,
            ))
            ranking_score = float(round(base_score * performance_multiplier, 2))

            confidence_label = cls._confidence_label(confidence)
            top_rank_reason = cls._why_ranked_top(
                trend_strength_score=trend_strength_score,
                risk_reward_score=risk_reward_score,
                setup_quality_score=setup_quality_score,
                sector_state=sector_state,
                regime=regime,
                performance_multiplier=performance_multiplier,
                setup_profile=setup_profile,
                sector_profile=sector_profile,
            )
            invalidation = cls._invalidation_reasons(setup_type, support, vol_ratio, sector_state)
            failure_points = cls._failure_scenarios(setup_type, vol_ratio, sector_state)
            explanation = cls._build_explanation(
                action=action,
                setup_type=setup_type,
                adx=adx,
                support=support,
                resistance=resistance,
                rr=rr,
                vol_ratio=vol_ratio,
                top_rank_reason=top_rank_reason,
                validation_reasons=validation_reasons,
                trust_message=cls._trust_message(setup_type, setup_profile, sector_label, sector_profile),
            )

            tags = cls._reason_tags(
                action=action,
                breakout=breakout,
                retest=retest,
                adx=adx,
                rr=rr,
                sector_state=sector_state,
                confidence=confidence,
            )

            factors = [
                {"label": "Confidence", "value": f"{int(confidence)}%", "positive": confidence >= cls.MIN_VALID_CONFIDENCE},
                {"label": "Trend Strength", "value": f"{trend_strength_score:.0f}/100", "positive": adx >= cls.MIN_TREND_ADX},
                {"label": "Risk-Reward", "value": f"{risk_reward_score:.0f}/100", "positive": rr >= cls.BUY_RR},
                {"label": "Setup Quality", "value": f"{setup_quality_score:.0f}/100", "positive": setup_type != "NONE"},
                {"label": "Setup Win Rate", "value": f"{setup_win_rate:.0f}%", "positive": setup_win_rate >= 55.0},
                {"label": "Sector Performance", "value": f"{sector_recent_pnl:+.1f}%", "positive": sector_recent_pnl >= 0.0},
                {"label": "Sector Alignment", "value": sector_state, "positive": sector_state in {"LEADING", "IMPROVING"}},
                {"label": "Market Regime", "value": regime, "positive": regime not in {"RANGE", "WEAK_TREND", "RISK-OFF"}},
                {"label": "Adaptive Multiplier", "value": f"{performance_multiplier:.2f}x", "positive": performance_multiplier >= 1.0},
                {"label": "Priority Score", "value": f"{ranking_score:.0f}", "positive": action == "BUY"},
            ]

            if action == "NO TRADE":
                logger.info(
                    "Trade rejected for %s: %s",
                    hit.get("symbol", "<unknown>"),
                    "; ".join(validation_reasons[:6]) or "System unable to validate setup",
                )

            confidence_value = int(round(confidence))
            return {
                "score": ranking_score,
                "confidence": confidence_value,
                "confidenceLabel": confidence_label,
                "confidenceBucket": confidence_label,
                "grade": cls._grade_from_confidence(confidence_value),
                "action": action,
                "setupType": setup_type,
                "reasonTags": tags,
                "confidenceFactors": factors,
                "rr": float(round(rr, 2)),
                "isValidTrade": bool(is_valid_trade),
                "validationReasons": validation_reasons[:6],
                "explanation": explanation,
                "nearestSupport": float(round(support, 2)) if support > 0 else None,
                "nearestResistance": float(round(resistance, 2)) if resistance > 0 else None,
                "hasFallbackLevels": any(src != "direct" for src in sr_sources.values()),
                "supportResistanceSources": sr_sources,
                "rankingComponents": {
                    "confidence": round(confidence, 2),
                    "baseConfidence": round(base_confidence, 2),
                    "confidenceAdjustment": round(confidence_adjustment, 2),
                    "riskRewardScore": round(risk_reward_score, 2),
                    "trendStrengthScore": round(trend_strength_score, 2),
                    "setupQualityScore": round(setup_quality_score, 2),
                    "baseScore": round(base_score, 2),
                    "performanceMultiplier": round(performance_multiplier, 3),
                },
                "topPickEligible": (
                    action == "BUY"
                    and confidence >= adaptive_top_pick_confidence
                    and rr >= adaptive_top_pick_rr
                    and performance_multiplier >= 1.0
                    and confidence_adjustment >= 0.0
                ),
                "executeLabel": "Execute Plan" if action == "BUY" else None,
                "whyRankedTop": top_rank_reason,
                "trustSignals": {
                    "setupWinRate": round(setup_win_rate, 2),
                    "setupTrades": int(setup_profile.get("trades") or 0),
                    "sectorWinRate": round(sector_win_rate, 2),
                    "sectorPerformancePct": round(sector_recent_pnl, 2),
                    "sectorTrades": int(sector_profile.get("trades") or 0),
                    "performanceMultiplier": round(performance_multiplier, 3),
                    "confidenceAdjustment": round(confidence_adjustment, 2),
                    "trustMessage": cls._trust_message(setup_type, setup_profile, sector_label, sector_profile),
                },
                "adaptiveThresholds": {
                    "buyConfidence": round(buy_confidence_threshold, 2),
                    "watchConfidence": round(watch_confidence_threshold, 2),
                    "topPickConfidence": round(adaptive_top_pick_confidence, 2),
                    "topPickRR": round(adaptive_top_pick_rr, 2),
                },
                "whatInvalidates": invalidation,
                "whatCanGoWrong": failure_points,
            }
        except Exception:
            logger.exception("Trade score calculation failed for %s", hit.get("symbol", "<unknown>"))
            return cls._system_failure_payload()

    @classmethod
    def build_plan(
        cls,
        hit: dict[str, Any],
        account_balance: float = DEFAULT_ACCOUNT_BALANCE,
        risk_pct: float = DEFAULT_RISK_PCT,
    ) -> dict[str, Any]:
        try:
            action = str(hit.get("action") or "NO TRADE").upper()
            if action == "NO TRADE" or not bool(hit.get("isValidTrade")):
                return cls._invalid_plan(account_balance=account_balance, risk_pct=risk_pct, hit=hit)

            price = cls._f(hit.get("price") or hit.get("meta", {}).get("cmp") or hit.get("summary", {}).get("cmp"))
            support = cls._f(hit.get("nearestSupport") or hit.get("summary", {}).get("nearest_support"))
            resistance = cls._f(hit.get("nearestResistance") or hit.get("summary", {}).get("nearest_resistance"))
            setup_type = str(hit.get("setupType") or "NONE").upper()
            confidence = cls._f(hit.get("confidence"))
            rr = cls._f(hit.get("rr"))
            vol_ratio = cls._f(hit.get("volRatio") or (hit.get("technical") or {}).get("volRatio"))

            if setup_type in {"BREAKOUT", "BREAKOUT_RETEST"} and resistance > price:
                entry = resistance
                entry_type = "Breakout entry"
                entry_logic = "Execute on breakout above resistance"
                confirmation_mode = "BREAKOUT_TRIGGER"
                confirmations = ["Wait for candle close above level"]
                if vol_ratio >= 1.0:
                    confirmations.append("Volume confirmation required")
            else:
                entry = max(price, support * 1.003) if support > 0 else price
                entry_type = "Pullback entry"
                entry_logic = "Execute on pullback hold above support"
                confirmation_mode = "PULLBACK_HOLD"
                confirmations = ["Wait for support hold on candle close", "Volume confirmation required"]

            stop_loss = support if 0 < support < entry else (entry * 0.985)
            risk = max(entry - stop_loss, 0.0)
            target1 = cls._f(hit.get("target") or hit.get("summary", {}).get("target"))
            if target1 <= entry:
                target1 = entry + (risk * max(rr, 2.0 if action == "BUY" else 1.5))
            one_r = entry + risk
            if one_r > entry:
                target1 = max(target1, one_r)
            target2 = max(target1, entry + (risk * max(rr + 0.5, 2.5)))

            rr_to_t1 = float(round(((target1 - entry) / risk), 2)) if risk > 0 else 0.0
            risk_pct_value = float(risk_pct or cls.DEFAULT_RISK_PCT)
            account_balance_value = float(account_balance or cls.DEFAULT_ACCOUNT_BALANCE)
            capital_at_risk = account_balance_value * risk_pct_value
            position_units = int(capital_at_risk // risk) if risk > 0 else 0
            risk_pct_per_unit = ((risk / entry) * 100.0) if entry > 0 else 0.0
            position_sizing = cls._position_sizing_suggestion(risk_pct_per_unit, confidence, position_units)

            return {
                "title": "Execute Plan" if action == "BUY" else "Watch Plan",
                "entry": float(round(entry, 2)),
                "stopLoss": float(round(stop_loss, 2)),
                "target1": float(round(target1, 2)),
                "target2": float(round(target2, 2)),
                "riskPerUnit": float(round(risk, 2)),
                "riskRewardToT1": rr_to_t1,
                "passesRiskReward": rr_to_t1 >= cls.BUY_RR,
                "tradeQuality": "PRIORITIZED EXECUTION" if action == "BUY" else "DEVELOPING SETUP",
                "executionAllowed": action == "BUY",
                "executionConfidence": "HIGH" if confidence >= 80 else "MEDIUM",
                "confirmationMode": confirmation_mode,
                "entryType": entry_type,
                "entryConfirmation": confirmations,
                "executeNotice": "Execute only if conditions are met",
                "entryLogic": entry_logic,
                "stopLogic": "Fixed stop below validated support",
                "tradeTag": "EXECUTE PLAN" if action == "BUY" else "WATCH",
                "positionSizing": position_sizing,
                "positionSizingSuggestion": position_sizing,
                "positionSizeUnits": position_units,
                "accountBalance": round(account_balance_value, 2),
                "riskPct": round(risk_pct_value * 100.0, 2),
                "capitalAtRisk": round(capital_at_risk, 2),
                "partialProfitPlan": "Take 50% profit at 1R.",
                "trailingStopPlan": "Trail SL to cost after 1R achieved.",
                "whatInvalidates": hit.get("whatInvalidates") or [],
                "whatCanGoWrong": hit.get("whatCanGoWrong") or [],
            }
        except Exception:
            logger.exception("Execution plan build failed for %s", hit.get("symbol", "<unknown>"))
            return cls._invalid_plan(account_balance=account_balance, risk_pct=risk_pct, hit=hit)

    @staticmethod
    def _detect_setup(retest: bool, breakout: bool) -> str:
        if retest and breakout:
            return "BREAKOUT_RETEST"
        if breakout:
            return "BREAKOUT"
        if retest:
            return "RETEST"
        return "NONE"

    @classmethod
    def _resolve_support_resistance(cls, hit: dict[str, Any], entry: float) -> tuple[float, float, dict[str, str]]:
        summary = hit.get("summary") or {}
        tech = hit.get("technical") or {}

        support = cls._f(summary.get("nearest_support") or hit.get("nearestSupport") or hit.get("nearest_support"))
        resistance = cls._f(summary.get("nearest_resistance") or hit.get("nearestResistance") or hit.get("nearest_resistance"))
        sources = {"support": "direct", "resistance": "direct"}

        swing_low = cls._f(tech.get("swingLow") or hit.get("swingLow"))
        recent_high = cls._f(tech.get("recentHigh") or hit.get("recentHigh"))
        if support <= 0 and swing_low > 0 and swing_low < entry:
            support = swing_low
            sources["support"] = "swing_low"
        if resistance <= 0 and recent_high > entry:
            resistance = recent_high
            sources["resistance"] = "recent_high"

        if support <= 0 or resistance <= 0:
            fb_support, fb_resistance = cls._fallback_levels_from_ohlcv(hit.get("ohlcv"), entry)
            if support <= 0 and fb_support > 0:
                support = fb_support
                sources["support"] = "pivot_or_previous_low"
            if resistance <= 0 and fb_resistance > 0:
                resistance = fb_resistance
                sources["resistance"] = "pivot_or_previous_high"

        return support, resistance, sources

    @classmethod
    def _fallback_levels_from_ohlcv(cls, ohlcv: Any, entry: float) -> tuple[float, float]:
        if not isinstance(ohlcv, list) or len(ohlcv) < 3:
            return 0.0, 0.0

        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        for row in ohlcv[-30:]:
            if not isinstance(row, dict):
                continue
            high = cls._f(row.get("high"))
            low = cls._f(row.get("low"))
            close = cls._f(row.get("close"))
            if high > 0:
                highs.append(high)
            if low > 0:
                lows.append(low)
            if close > 0:
                closes.append(close)

        if len(highs) < 2 or len(lows) < 2 or not closes:
            return 0.0, 0.0

        support_candidates = [v for v in lows[:-1] if 0 < v < entry]
        resistance_candidates = [v for v in highs[:-1] if v > entry]
        prev_high = highs[-2]
        prev_low = lows[-2]
        prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
        pivot = (prev_high + prev_low + prev_close) / 3.0
        support_candidates.extend(v for v in (prev_low, (2 * pivot) - prev_high, pivot - (prev_high - prev_low)) if 0 < v < entry)
        resistance_candidates.extend(v for v in (prev_high, (2 * pivot) - prev_low, pivot + (prev_high - prev_low)) if v > entry)
        support = max((v for v in support_candidates if v > 0), default=0.0)
        resistance = min((v for v in resistance_candidates if v > entry), default=0.0)
        return support, resistance

    @classmethod
    def _support_resistance_points(cls, entry: float, support: float, resistance: float) -> int:
        points = 0
        if support > 0 and entry > 0:
            dist_s = (entry - support) / entry
            if dist_s <= 0.02:
                points += 10
            elif dist_s <= 0.04:
                points += 5
        if resistance > 0 and entry > 0:
            dist_r = (resistance - entry) / entry
            if dist_r < 0.02:
                points -= 5
            elif dist_r >= 0.04:
                points += 2
        return max(0, min(10, points))

    @staticmethod
    def _trend_strength_score(adx: float) -> float:
        if adx <= 20:
            return 0.0
        return min(100.0, ((adx - 20.0) / 15.0) * 100.0)

    @staticmethod
    def _risk_reward_score(rr: float) -> float:
        if rr <= 0:
            return 0.0
        return min(100.0, (rr / 3.0) * 100.0)

    @staticmethod
    def _setup_quality_score(setup_type: str, vol_ratio: float) -> float:
        base = {
            "BREAKOUT_RETEST": 100.0,
            "BREAKOUT": 82.0,
            "RETEST": 72.0,
            "NONE": 0.0,
        }.get(setup_type, 0.0)
        if base > 0 and vol_ratio >= 1.5:
            base = min(100.0, base + 5.0)
        return base

    @staticmethod
    def _why_ranked_top(
        *,
        trend_strength_score: float,
        risk_reward_score: float,
        setup_quality_score: float,
        sector_state: str,
        regime: str,
        performance_multiplier: float,
        setup_profile: dict[str, Any],
        sector_profile: dict[str, Any],
    ) -> str:
        setup_rate = float(setup_profile.get("winRate") or 50.0)
        sector_perf = float(sector_profile.get("recentPnLPct") or sector_profile.get("avgPnLPct") or 0.0)
        return (
            f"Ranked highly because trend strength scored {trend_strength_score:.0f}/100, "
            f"risk-reward scored {risk_reward_score:.0f}/100, and setup quality scored {setup_quality_score:.0f}/100. "
            f"Historical performance applies a {performance_multiplier:.2f}x adaptive multiplier from setup win rate {setup_rate:.0f}% "
            f"and sector performance {sector_perf:+.1f}%. Sector alignment is {sector_state} and market regime is {regime}."
        )

    @staticmethod
    def _invalidation_reasons(setup_type: str, support: float, vol_ratio: float, sector_state: str) -> list[str]:
        items = []
        if support > 0:
            items.append(f"Close below support {support:.2f}")
        if setup_type in {"BREAKOUT", "BREAKOUT_RETEST"}:
            items.append("Breakout candle closes back below trigger")
        if vol_ratio < 1.5:
            items.append("Volume fails to confirm the move")
        if sector_state not in {"LEADING", "IMPROVING"}:
            items.append("Sector loses leadership")
        return items[:4]

    @staticmethod
    def _failure_scenarios(setup_type: str, vol_ratio: float, sector_state: str) -> list[str]:
        items = []
        if setup_type in {"BREAKOUT", "BREAKOUT_RETEST"}:
            items.append("Breakout failure")
        if vol_ratio < 1.5:
            items.append("Low volume")
        if sector_state not in {"LEADING", "IMPROVING"}:
            items.append("Sector weakness")
        items.append("Market reverses into range")
        return items[:4]

    @classmethod
    def _reason_tags(
        cls,
        *,
        action: str,
        breakout: bool,
        retest: bool,
        adx: float,
        rr: float,
        sector_state: str,
        confidence: float,
    ) -> list[str]:
        tags: list[str] = []
        if action == "BUY":
            tags.append("Execute Plan")
            tags.append("Breakout" if breakout else "Pullback")
            if retest:
                tags.append("Retest Confirmed")
            if adx >= 25:
                tags.append("Strong Trend")
            if rr >= 2:
                tags.append("RR > 2")
        elif action == "WATCH":
            tags.extend(["Watch Setup", "Need Confirmation"])
        else:
            if confidence < cls.MIN_VALID_CONFIDENCE:
                tags.append("Low Confidence")
            if sector_state not in {"LEADING", "IMPROVING"}:
                tags.append("Sector Weakness")
            tags.append("No Trade")
        return tags[:4]

    @classmethod
    def _build_explanation(
        cls,
        *,
        action: str,
        setup_type: str,
        adx: float,
        support: float,
        resistance: float,
        rr: float,
        vol_ratio: float,
        top_rank_reason: str,
        validation_reasons: list[str],
        trust_message: str,
    ) -> str:
        if action == "NO TRADE":
            return f"{' '.join(validation_reasons)} Avoid entering this trade."
        setup_label = setup_type.replace("_", " ").lower()
        if action == "BUY":
            return (
                f"This trade is selected due to strong trend, confirmed {setup_label}, and volume at {vol_ratio:.2f}x average. "
                f"Risk-reward is favorable above {rr:.2f}. {trust_message} {top_rank_reason} "
                f"Execute only if conditions are met between support {support:.2f} and resistance {resistance:.2f}."
            )
        return (
            f"This setup is developing with {setup_label} structure and ADX {adx:.1f}. {trust_message} "
            f"Wait for stronger confirmation before executing."
        )

    @staticmethod
    def _lookup_profile(profiles: Any, label: str) -> dict[str, Any]:
        if not isinstance(profiles, dict):
            return {}
        return dict(profiles.get(str(label or "UNKNOWN").upper()) or profiles.get(str(label or "UNKNOWN")) or {})

    @classmethod
    def _load_adaptive_intelligence(cls) -> dict[str, Any]:
        try:
            from .trade_tracking_service import TradeTrackingService

            return TradeTrackingService.get_adaptive_intelligence()
        except Exception:
            return {}

    @staticmethod
    def _trust_message(setup_type: str, setup_profile: dict[str, Any], sector_label: str, sector_profile: dict[str, Any]) -> str:
        setup_rate = float(setup_profile.get("winRate") or 50.0)
        sector_perf = float(sector_profile.get("recentPnLPct") or sector_profile.get("avgPnLPct") or 0.0)
        setup_trades = int(setup_profile.get("trades") or 0)
        sector_trades = int(sector_profile.get("trades") or 0)
        return (
            f"This {setup_type.replace('_', ' ').lower()} setup has a {setup_rate:.0f}% historical success rate "
            f"across {setup_trades} tracked trades, while {sector_label.replace('_', ' ')} is running at {sector_perf:+.1f}% "
            f"across {sector_trades} tracked trades."
        )

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _position_sizing_suggestion(risk_pct_per_unit: float, confidence: float, units: int) -> str:
        if units <= 0:
            return "No position"
        if confidence >= 85 and risk_pct_per_unit <= 1.5:
            return f"Full size · {units} units"
        if confidence >= 75 and risk_pct_per_unit <= 2.5:
            return f"Half size · {units} units"
        return f"Starter size · {units} units"

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 75:
            return "HIGH"
        if score >= 50:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _f(v: Any) -> float:
        try:
            if v is None:
                return 0.0
            val = float(v)
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return val
        except Exception:
            return 0.0

    @staticmethod
    def _grade_from_confidence(confidence: float) -> str:
        return MarketRegimeEngine.get_grade(int(round(confidence)))

    @classmethod
    def _system_failure_payload(cls, explanation: str = "System unable to validate setup") -> dict[str, Any]:
        try:
            from .observability_service import ObservabilityService

            ObservabilityService.record_fail_safe("TradeDecisionService", {"explanation": explanation})
        except Exception:
            pass
        return {
            "score": 0.0,
            "confidence": 0,
            "confidenceLabel": "LOW",
            "confidenceBucket": "LOW",
            "grade": cls._grade_from_confidence(0),
            "action": "NO TRADE",
            "setupType": "NONE",
            "reasonTags": ["System Failure", "No Trade"],
            "confidenceFactors": [],
            "rr": 0.0,
            "isValidTrade": False,
            "validationReasons": [explanation],
            "explanation": explanation,
            "nearestSupport": None,
            "nearestResistance": None,
            "hasFallbackLevels": False,
            "supportResistanceSources": {"support": "none", "resistance": "none"},
            "rankingComponents": {
                "confidence": 0.0,
                "riskRewardScore": 0.0,
                "trendStrengthScore": 0.0,
                "setupQualityScore": 0.0,
            },
            "topPickEligible": False,
            "executeLabel": None,
            "whyRankedTop": explanation,
            "trustSignals": {
                "setupWinRate": 0.0,
                "setupTrades": 0,
                "sectorWinRate": 0.0,
                "sectorPerformancePct": 0.0,
                "sectorTrades": 0,
                "performanceMultiplier": 1.0,
                "confidenceAdjustment": 0.0,
                "trustMessage": explanation,
            },
            "adaptiveThresholds": {
                "buyConfidence": cls.BUY_CONFIDENCE,
                "watchConfidence": cls.WATCH_CONFIDENCE,
                "topPickConfidence": cls.SAFE_TOP_PICK_CONFIDENCE,
                "topPickRR": cls.SAFE_TOP_PICK_RR,
            },
            "whatInvalidates": [],
            "whatCanGoWrong": ["System unable to validate setup"],
        }

    @classmethod
    def _invalid_plan(
        cls,
        *,
        account_balance: float = DEFAULT_ACCOUNT_BALANCE,
        risk_pct: float = DEFAULT_RISK_PCT,
        hit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        hit = hit or {}
        return {
            "title": "No valid trade setup available",
            "entry": None,
            "stopLoss": None,
            "target1": None,
            "target2": None,
            "riskPerUnit": None,
            "riskRewardToT1": 0.0,
            "passesRiskReward": False,
            "tradeQuality": "INVALID SETUP",
            "executionAllowed": False,
            "executionConfidence": "LOW",
            "confirmationMode": "NONE",
            "entryType": None,
            "entryConfirmation": [],
            "executeNotice": "System unable to validate setup",
            "entryLogic": "No valid trade setup available",
            "stopLogic": "No valid trade setup available",
            "tradeTag": "NO TRADE",
            "positionSizing": "No position",
            "positionSizingSuggestion": "No position",
            "positionSizeUnits": 0,
            "accountBalance": float(account_balance),
            "riskPct": float(risk_pct),
            "capitalAtRisk": 0.0,
            "partialProfitPlan": "No plan",
            "trailingStopPlan": "No plan",
            "whatInvalidates": hit.get("whatInvalidates") or [],
            "whatCanGoWrong": hit.get("whatCanGoWrong") or ["System unable to validate setup"],
        }

    @classmethod
    def _apply_trade_contract(cls, row: dict[str, Any], plan: dict[str, Any]) -> None:
        row["grade"] = row.get("grade") or cls._grade_from_confidence(cls._f(row.get("confidence")))
        row["entry"] = plan.get("entry")
        row["stop_loss"] = plan.get("stopLoss")
        row["target"] = plan.get("target1")
        row["execution_plan"] = {
            "entry": plan.get("entry"),
            "stop_loss": plan.get("stopLoss"),
            "target": plan.get("target1"),
            "target_2": plan.get("target2"),
            "risk_per_unit": plan.get("riskPerUnit"),
            "risk_reward_to_t1": plan.get("riskRewardToT1"),
            "position_sizing": plan.get("positionSizingSuggestion"),
            "position_size_units": plan.get("positionSizeUnits"),
            "trade_tag": plan.get("tradeTag"),
            "execute_notice": plan.get("executeNotice"),
        }
