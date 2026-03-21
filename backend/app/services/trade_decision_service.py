from __future__ import annotations

from typing import Any
import math


class TradeDecisionService:
    """
    Execution-layer annotation service.
    Additive only: does not modify scoring, filter logic, or signal generation.
    """

    @classmethod
    def annotate_many(cls, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for hit in hits or []:
            row = dict(hit)
            
            # 1. Compute Trade Score and Decision
            decision_data = cls.compute_trade_score(row)
            row.update(decision_data)
            
            # 2. Build Execution Plan (Original logic, kept for compatibility)
            plan = cls.build_plan(row)
            row["executionPlan"] = plan
            row["tradeDecisionTag"] = decision_data.get("action", plan.get("tradeTag", "WATCHLIST"))
            
            out.append(row)
        return out

    @classmethod
    def compute_trade_score(cls, hit: dict[str, Any]) -> dict[str, Any]:
        """
        Decision Engine v2.0
        Computes a 0-100 score based on user-defined weights.
        """
        tech = hit.get("technical") or {}
        insights = hit.get("insights") or {}
        summary = hit.get("summary") or {}
        
        # 1. Trend Strength (ADX): Weight 20
        adx = cls._f(hit.get("adx") or tech.get("adx") or insights.get("adx"))
        trend_score = 0
        if adx > 25: trend_score = 20
        elif adx > 15: trend_score = 10
        else: trend_score = 5
        
        # 2. Setup Quality: Weight 20
        retest = bool(hit.get("retest") or tech.get("retest") or insights.get("retest"))
        breakout = bool(tech.get("isBreakout") or insights.get("breakout"))
        setup_score = 0
        if retest and breakout: setup_score = 20
        elif retest or breakout: setup_score = 15
        elif not retest and not breakout:
            # FORCE NO TRADE if both are missing
            setup_score = 0
        else: setup_score = 5
        
        # 3. Volume: Weight 15
        vol_ratio = cls._f(hit.get("volRatio") or hit.get("volume_ratio") or tech.get("volRatio"))
        vol_score = 0
        if vol_ratio > 1.2: vol_score = 15
        elif vol_ratio >= 0.8: vol_score = 10
        else: vol_score = 5
        
        # 4. Risk-Reward: Weight 15
        entry = cls._f(hit.get("price") or summary.get("cmp") or hit.get("meta", {}).get("cmp"))
        sl = cls._f(hit.get("stopLoss") or summary.get("stop_loss"))
        tgt = cls._f(hit.get("target") or summary.get("target"))
        
        rr = 0
        if entry > 0 and sl > 0 and entry > sl:
            risk = entry - sl
            reward = tgt - entry if tgt > entry else (risk * 2) 
            rr = reward / risk if risk > 0 else 0
            
        rr_score = 0
        if rr >= 2.0: rr_score = 15
        elif rr >= 1.5: rr_score = 10
        elif rr >= 1.0: rr_score = 5
        else: rr_score = 0  # RR < 1 is a major penalty
        
        # 5. Support/Resistance Proximity: Weight 10
        s0 = cls._f(summary.get("nearest_support") or hit.get("nearest_support"))
        r0 = cls._f(summary.get("nearest_resistance") or hit.get("nearest_resistance"))
        
        sr_score = 5 # Neutral start
        if s0 > 0 and entry > 0:
            dist_s = (entry - s0) / entry
            if dist_s < 0.02: sr_score += 5 # Near support (positive)
        if r0 > 0 and entry > 0:
            dist_r = (r0 - entry) / entry
            if dist_r < 0.02: sr_score -= 5 # Near resistance (negative)
        sr_score = max(0, min(10, sr_score))

        # 6. Momentum: Weight 10
        momentum_strength = str(tech.get("momentumStrength") or "WEAK").upper()
        mo_score = 10 if momentum_strength == "STRONG" else 5 if momentum_strength == "MODERATE" else 2
        
        # 7. Volatility: Weight 10
        vol_high = bool(tech.get("volHigh"))
        vola_score = 5 if vol_high else 10 # Prefer stable volatility for setups

        # Calculate final normalized score (Weight total: 20+20+15+15+10+10+10 = 100)
        final_score = trend_score + setup_score + vol_score + rr_score + sr_score + mo_score + vola_score
        final_score = min(100.0, float(final_score))
        
        # Action Mapping & Safety Rules
        action = "AVOID"
        if not retest and not breakout:
            action = "AVOID" # Strict rule: No setup = No trade
        elif rr < 1.0:
            action = "AVOID" # Strict rule: RR < 1 = Avoid
        elif final_score >= 80:
            action = "STRONG BUY"
        elif final_score >= 70:
            action = "BUY"
        elif final_score >= 60:
            action = "WATCH"
        else:
            action = "AVOID"
        
        # Tags (max 4)
        tags = []
        if action == "AVOID":
            if rr < 1.0: tags.append("Poor RR")
            if not retest and not breakout: tags.append("No Setup")
            if final_score < 60: tags.append("Weak Metrics")
        else:
            if retest: tags.append("Retest Confirmed")
            if breakout: tags.append("Breakout Confirmed")
            if vol_score >= 15: tags.append("Volume Strong")
            if trend_score >= 20: tags.append("Strong Trend")
            if rr_score >= 15: tags.append("High RR")
        
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
