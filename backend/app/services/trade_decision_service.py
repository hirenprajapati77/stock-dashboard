from __future__ import annotations

from typing import Any
import math
from app.ai.commentary import AICommentaryService


class TradeDecisionService:
    """
    Execution-layer annotation service.
    Additive only: does not modify scoring, filter logic, or signal generation.
    """

    @classmethod
    def annotate_many(cls, hits: list[dict[str, Any]], market_phase: str = "OPEN") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for hit in hits or []:
            row = dict(hit)
            
            # --- V5 INTELLIGENCE SYNC (NEW) ---
            # If the hit already has V5 decision data from the background engine, 
            # we respect it and skip legacy re-computation.
            v5_decision = row.get("decision")
            if isinstance(v5_decision, dict) and v5_decision.get("meta_score"):
                # Map V5 metrics to hit-level fields for UI consistency
                row["confidence"] = v5_decision.get("meta_score", {}).get("meta_score") or v5_decision.get("confidence")
                row["grade"] = v5_decision.get("meta_score", {}).get("trade_grade") or v5_decision.get("quality")
                row["entryStatus"] = v5_decision.get("meta_score", {}).get("final_decision") or v5_decision.get("entry_status")
                row["tradeDecisionTag"] = row["entryStatus"]
                row["action"] = row["entryStatus"]
                row["aiCommentary"] = v5_decision.get("narrative") or row.get("aiCommentary")
                
                # Sync execution plan
                if not row.get("executionPlan") or not row["executionPlan"].get("entry"):
                    row["executionPlan"] = {
                        "entry": v5_decision.get("entry"),
                        "stopLoss": v5_decision.get("stop_loss"),
                        "target1": v5_decision.get("targets", [None])[0],
                        "riskRewardToT1": v5_decision.get("risk_reward"),
                        "tradeQuality": v5_decision.get("quality"),
                        "executionConfidence": v5_decision.get("meta_score", {}).get("final_decision")
                    }
                
                out.append(row)
                continue

            # --- LEGACY FALLBACK (Only used if V5 is missing) ---
            # 0. Capture Engine Recommendation (if any)
            engine_status = str(row.get("entryStatus") or row.get("entryTag") or "WATCHLIST").upper()
            engine_side = str(row.get("side") or "LONG").upper()
            
            # 1. Compute Trade Score and Decision
            decision_data = cls.compute_trade_score(row, market_phase)
            row.update(decision_data)
            
            # 2. Build Execution Plan (Original logic, kept for compatibility)
            plan = cls.build_plan(row)
            row["executionPlan"] = plan
            
            # 3. Dynamic Side Detection Alignment
            row["side"] = engine_side
            
            # 4. Final Decision Mapping (Respecting Engine + Decision Logic)
            # If engine is very confident (STRONG_ENTRY), we elevate WATCH to BUY
            final_action = decision_data.get("action", "OBSERVE")
            if engine_status == "STRONG_ENTRY" and final_action in ["WATCHLIST", "MONITOR", "ANALYZING"]:
                final_action = "BUY"
                row["reasonTags"] = list(set(row.get("reasonTags", []) + ["Engine Strong"]))[:4]
            
            row["tradeDecisionTag"] = final_action
            row["action"] = final_action

            # 5. AI Insights & Commentary (Phase 2 Enhancement)
            ai_context = {
                "entityType": "stock",
                "symbol": row.get("symbol"),
                "currentQuadrant": row.get("sectorState", "NEUTRAL"),
                "RS": row.get("volRatio", 1.0), 
                "RM": 0.05 if row.get("momentumStrength") == "STRONG" else 0.0,
                "setupType": row.get("technical", {}).get("setupType", "MOMENTUM_HIT"),
                "qualityScore": row.get("score", 50),
                "side": engine_side
            }
            row["aiCommentary"] = AICommentaryService.generate_commentary(ai_context)
            
            out.append(row)
        return out

    @classmethod
    def compute_trade_score(cls, hit: dict[str, Any], market_phase: str = "OPEN") -> dict[str, Any]:
        """
        Decision Engine v2.1 (Recalibrated)
        Computes a 0-100 score with relaxed thresholds and bounce support.
        """
        tech = hit.get("technical") or {}
        insights = hit.get("insights") or {}
        summary = hit.get("summary") or {}
        
        # 0. Entry Data
        entry = cls._f(hit.get("price") or summary.get("cmp") or hit.get("meta", {}).get("cmp"))

        # 1. Trend Strength (ADX): Weight 20
        adx = cls._f(hit.get("adx") or tech.get("adx") or insights.get("adx"))
        trend_score = 0
        if adx > 25: trend_score = 20
        elif adx > 15: trend_score = 10
        else: trend_score = 5
        
        # 2. Setup Quality: Weight 25 (Increased from 20)
        retest = bool(hit.get("retest") or tech.get("retest") or insights.get("retest"))
        breakout = bool(tech.get("isBreakout") or insights.get("breakout"))
        
        # New: Bounce detection (Price near level + reversal volume)
        is_bounce = False
        dist_to_sup = cls._f(hit.get("nearest_support_dist") or (hit.get("nearest_support") and entry > 0 and abs(entry - hit["nearest_support"])/entry))
        if dist_to_sup > 0 and dist_to_sup <= 0.015:
            is_bounce = True

        setup_score = 0
        if retest and breakout: setup_score = 25
        elif retest or breakout: setup_score = 20
        elif is_bounce: setup_score = 15 # Bounce counts as a valid setup
        else: setup_score = 5 # Relaxed from 0: Observation is worth something
        
        # 3. Volume: Weight 15
        vol_ratio = cls._f(hit.get("volRatio") or hit.get("volume_ratio") or tech.get("volRatio"))
        vol_score = 0
        if vol_ratio > 1.2: vol_score = 15
        elif vol_ratio >= 0.8: vol_score = 10
        else: vol_score = 5
        
        # 4. Risk-Reward: Weight 15
        sl = cls._f(hit.get("stopLoss") or summary.get("stop_loss"))
        tgt = cls._f(hit.get("target") or summary.get("target"))
        
        rr = 0
        if entry > 0 and sl > 0 and abs(entry - sl) > 0.0001:
            risk = abs(entry - sl)
            reward = abs(tgt - entry) if tgt > 0 else (risk * 2) 
            rr = reward / risk
            
        rr_score = 0
        if rr >= 2.0: rr_score = 15
        elif rr >= 1.5: rr_score = 10
        elif rr >= 1.0: rr_score = 5
        else: rr_score = 0  # RR < 1 is a major penalty
        
        # 5. Support/Resistance Proximity (Integrated into S/R score): Weight 10
        sr_score = 5 # Neutral start
        if is_bounce: sr_score = 10 
        elif retest: sr_score = 8
        
        # 6. Momentum: Weight 10
        momentum_strength = str(tech.get("momentumStrength") or "WEAK").upper()
        mo_score = 10 if momentum_strength == "STRONG" else 5 if momentum_strength == "MODERATE" else 2
        
        # 7. Volatility: Weight 10
        vol_high = bool(tech.get("volHigh"))
        vola_score = 5 if vol_high else 10 # Prefer stable volatility for setups

        # Calculate final normalized score
        final_score = trend_score + setup_score + vol_score + rr_score + sr_score + mo_score + vola_score
        final_score = min(100.0, float(final_score))
        
        # Action Mapping & Safety Rules (RECALIBRATED for Responsiveness)
        action = "WAIT"
        if rr > 0 and rr < 1.0:
            action = "REJECT" # Poor RR is a direct rejection
        elif final_score >= 75:
            action = "EXECUTE"
        elif final_score >= 60:
            action = "WATCH"
        elif final_score >= 45:
            action = "WAIT"
        elif final_score >= 35:
            action = "WAIT"
        else:
            action = "REJECT"
        
        # Tags (max 4)
        tags = []
        if action == "OBSERVE" or action == "MONITOR":
            if rr > 0 and rr < 1.0: tags.append("Poor RR")
            if final_score < 35: tags.append("Weak Metrics")
        else:
            if retest: tags.append("Retest Confirmed")
            if breakout: tags.append("Breakout Confirmed")
            if is_bounce: tags.append("Bounce Found")
            if vol_score >= 15: tags.append("Volume Strong")
            if trend_score >= 20: tags.append("Strong Trend")

        # Factors for UI
        factors = [
            {"label": "Trend Strength", "value": f"+{trend_score}%", "positive": trend_score >= 15},
            {"label": "Setup Quality", "value": f"+{setup_score}%", "positive": setup_score >= 15},
            {"label": "Volume Profile", "value": f"+{vol_score}%", "positive": vol_score >= 10},
            {"label": "Risk-Reward", "value": f"+{rr_score}%", "positive": rr_score >= 10},
            {"label": "S/R Focus", "value": f"+{sr_score}%", "positive": sr_score >= 8},
            {"label": "Momentum", "value": f"+{mo_score}%", "positive": mo_score >= 8},
            {"label": "Volatility", "value": f"+{vola_score}%", "positive": vola_score >= 10},
        ]
            
        # Market Phase Overrides
        if action in ["EXECUTE", "WATCH"]:
            if market_phase == "CLOSED":
                action = "REJECT"
                tags.append("Market Closed")
            elif market_phase == "POST_MARKET":
                action = "WAIT"
                tags.append("Post-Market")
            elif market_phase == "PRE_MARKET":
                action = "WAIT"
                tags.append("Pre-Market")
        
        # Factors for UI
        factors = [
            {"label": "Trend Strength", "value": f"+{trend_score}%", "positive": trend_score >= 15},
            {"label": "Setup Quality", "value": f"+{setup_score}%", "positive": setup_score >= 15},
            {"label": "Volume Profile", "value": f"+{vol_score}%", "positive": vol_score >= 10},
            {"label": "Risk-Reward", "value": f"+{rr_score}%", "positive": rr_score >= 10},
            {"label": "S/R Proximity", "value": f"{sr_score - 5:+}%", "positive": sr_score > 5},
            {"label": "Momentum", "value": f"+{mo_score}%", "positive": mo_score >= 8},
            {"label": "Volatility", "value": f"+{vola_score}%", "positive": vola_score >= 10},
        ]

        return {
            "score": int(final_score),
            "confidence": int(final_score),
            "action": action,
            "reasonTags": list(tags[:4]),
            "confidenceFactors": factors,
            "rr": float(round(rr, 2))
        }

    @classmethod
    def build_plan(cls, hit: dict[str, Any]) -> dict[str, Any]:
        price = cls._f(hit.get("price"))
        tech = hit.get("technical") or {}
        entry_tag = str(hit.get("entryTag") or "WATCHLIST").upper()
        filter_category = str(hit.get("filterCategory") or "LOW").upper()

        vwap = cls._f(tech.get("vwap"))
        atr = cls._f(tech.get("atrExpansion"))
        stop_distance_pct = cls._f(tech.get("stopDistance"))
        swing_low = cls._f(tech.get("swingLow") or hit.get("swingLow"))
        recent_high = cls._f(tech.get("recentHigh") or hit.get("recentHigh"))
        vol_ratio = cls._f(hit.get("volRatio"))
        sector_state = str(hit.get("sectorState") or "NEUTRAL").upper()
        momentum_strength = str(tech.get("momentumStrength") or "WEAK").upper()

        entry, entry_logic, confirmation_mode = cls._entry_price(price, vwap, recent_high, swing_low, entry_tag, vol_ratio)
        stop_loss, stop_logic = cls._stop_loss(entry, swing_low, atr, stop_distance_pct)

        risk = max(entry - stop_loss, 0.0)
        target1 = entry + (1.5 * risk)
        target2 = entry + (2.0 * risk)

        rr_to_t1 = float(round(float(((target1 - entry) / risk)), 2)) if risk > 0 else 0.0
        rr_valid = rr_to_t1 >= 1.5

        strong_medium = (
            filter_category == "MEDIUM"
            and momentum_strength == "STRONG"
            and sector_state in {"LEADING", "IMPROVING"}
        )
        execution_allowed = rr_valid and (filter_category == "HIGH PROBABILITY" or strong_medium)
        trade_quality = "HIGH QUALITY TRADE" if execution_allowed else "LOW QUALITY TRADE"

        execution_confidence = cls._execution_confidence(filter_category, momentum_strength, sector_state)

        trade_tag = "WATCHLIST"
        if entry_tag == "STRONG_ENTRY":
            trade_tag = "READY TO TRADE" if execution_allowed else "CONDITIONAL ENTRY"
        elif entry_tag == "ENTRY_READY":
            trade_tag = "CONDITIONAL ENTRY" if rr_valid else "WATCHLIST"

        return {
            "entry": float(round(float(entry), 2)),
            "stopLoss": float(round(float(stop_loss), 2)),
            "target1": float(round(float(target1), 2)),
            "target2": float(round(float(target2), 2)),
            "riskPerUnit": float(round(float(risk), 2)),
            "riskRewardToT1": rr_to_t1,
            "passesRiskReward": rr_valid,
            "tradeQuality": trade_quality,
            "executionAllowed": execution_allowed,
            "executionConfidence": execution_confidence,
            "confirmationMode": confirmation_mode,
            "trailAfter1R": True,
            "moveStopToBreakevenAtR": 1.0,
            "entryLogic": entry_logic,
            "stopLogic": stop_logic,
            "tradeTag": trade_tag,
        }

    @staticmethod
    def _entry_price(
        price: float,
        vwap: float,
        recent_high: float,
        swing_low: float,
        entry_tag: str,
        vol_ratio: float,
    ) -> tuple[float, str, str]:
        if entry_tag == "STRONG_ENTRY":
            support_zone = swing_low if (swing_low > 0 and swing_low < price) else (price * 0.99)
            if vwap > 0:
                pullback = max(vwap, support_zone)
                return pullback, "Prefer pullback to VWAP/support zone", "PULLBACK_TO_VALUE"
            return support_zone, "Prefer pullback to support zone", "PULLBACK_TO_VALUE"

        if entry_tag == "ENTRY_READY":
            rh = recent_high if recent_high > 0 else (price * 1.003)
            mode = "CLOSE_ABOVE_LEVEL_OR_VOLUME_CONFIRMATION" if vol_ratio >= 1.5 else "CLOSE_ABOVE_LEVEL"
            return rh, "Breakout above recent high with confirmation", mode

        return price, "Observation only", "NONE"

    @staticmethod
    def _stop_loss(entry: float, swing_low: float, atr: float, stop_distance_pct: float) -> tuple[float, str]:
        # Primary: structure (recent swing low)
        if swing_low > 0 and swing_low < entry:
            return swing_low, "Recent swing low"

        # Fallback: ATR-based protective stop (1.2-1.5x band; using 1.35x midpoint)
        atr_mult = 1.35
        atr_based = entry - max((atr * atr_mult), 0.0)

        # Optional stopDistance guard if available
        pct_based = entry * (1 - (stop_distance_pct / 100.0)) if stop_distance_pct > 0 else atr_based
        candidate = min(atr_based, pct_based)

        # Prevent overly-tight stop (<0.8%); widen to 1.0% if needed
        min_buffer = entry * 0.01
        if (entry - candidate) < min_buffer:
            candidate = entry - min_buffer

        if candidate < entry:
            return candidate, "ATR-based fallback (1.35x)"

        return entry * 0.985, "Fallback 1.5% protective stop"

    @staticmethod
    def _execution_confidence(filter_category: str, momentum_strength: str, sector_state: str) -> str:
        score = 0
        if filter_category == "HIGH PROBABILITY":
            score += 2
        elif filter_category == "MEDIUM":
            score += 1

        if momentum_strength == "STRONG":
            score += 1
        if sector_state in {"LEADING", "IMPROVING"}:
            score += 1

        if score >= 4:
            return "HIGH CONFIDENCE"
        if score >= 2:
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
