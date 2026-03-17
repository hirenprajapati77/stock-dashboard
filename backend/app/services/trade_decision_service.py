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
            plan = cls.build_plan(row)
            row["executionPlan"] = plan
            row["tradeDecisionTag"] = plan.get("tradeTag", "WATCHLIST")
            out.append(row)
        return out

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

        rr_to_t1 = round(((target1 - entry) / risk), 2) if risk > 0 else 0.0
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
            "entry": round(entry, 2),
            "stopLoss": round(stop_loss, 2),
            "target1": round(target1, 2),
            "target2": round(target2, 2),
            "riskPerUnit": round(risk, 2),
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
