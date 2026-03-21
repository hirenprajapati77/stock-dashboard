from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .observability_service import ObservabilityService


class TradeTrackingService:
    LOG_FILE = Path(__file__).parent.parent / "data" / "trade_log.json"
    MAX_LOG = 2000
    EXPIRY_DAYS = 3
    PROFILE_MIN_SAMPLE = 3
    PROFILE_RECENT_WINDOW = 10
    ADAPTIVE_LOOKBACK = 30

    @classmethod
    def _load(cls) -> list[dict[str, Any]]:
        try:
            if cls.LOG_FILE.exists():
                return json.loads(cls.LOG_FILE.read_text(encoding="utf-8")) or []
        except Exception:
            pass
        return []

    @classmethod
    def _save(cls, rows: list[dict[str, Any]]) -> None:
        cls.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.LOG_FILE.write_text(json.dumps(rows[: cls.MAX_LOG], indent=2), encoding="utf-8")

    @classmethod
    def log_trades(
        cls,
        hits: list[dict[str, Any]],
        *,
        market_context: dict[str, Any] | None = None,
        mode: str = "safe",
    ) -> None:
        rows = cls._load()
        existing = {str(r.get("tradeKey")): idx for idx, r in enumerate(rows)}

        for hit in hits or []:
            row = cls._build_trade_row(hit, market_context=market_context, mode=mode)
            key = str(row["tradeKey"])
            if key in existing:
                rows[existing[key]] = row
            else:
                rows.insert(0, row)
                existing = {str(r.get("tradeKey")): idx for idx, r in enumerate(rows)}

        cls._save(rows)

    @classmethod
    def get_performance(cls) -> dict[str, Any]:
        rows = cls._load()
        actionable = [r for r in rows if str(r.get("action", "")).upper() == "BUY"]
        resolved = [r for r in actionable if r.get("outcome") in {"HIT_TARGET", "HIT_STOP_LOSS", "EXPIRED", "NO_ENTRY_TRIGGERED"}]
        executed = [r for r in resolved if r.get("outcome") != "NO_ENTRY_TRIGGERED"]
        wins = [r for r in resolved if r.get("outcome") == "HIT_TARGET"]
        losses = [r for r in resolved if r.get("outcome") == "HIT_STOP_LOSS"]
        no_trade_rows = [r for r in rows if str(r.get("action", "")).upper() == "NO TRADE"]

        realized_rrs = [cls._f(r.get("realizedRR")) for r in executed if r.get("realizedRR") is not None]
        win_rate = round((len(wins) / len(executed)) * 100, 2) if executed else 0.0
        avg_rr_achieved = round(sum(realized_rrs) / len(realized_rrs), 2) if realized_rrs else 0.0
        profit_factor = cls._profit_factor(executed)
        no_trade_rate = round((len(no_trade_rows) / len(rows)) * 100, 2) if rows else 0.0

        setup_performance = cls._aggregate_by_key(executed, "setupType")
        sector_performance = cls._aggregate_by_key(executed, "sector")
        outcome_breakdown = cls._outcome_breakdown(rows)
        recent_trend = cls._daily_trend(actionable)
        alerts = cls._build_alerts(rows, executed, no_trade_rate, win_rate)
        observability = ObservabilityService.get_summary()
        adaptive_intelligence = cls.get_adaptive_intelligence()

        return {
            "totalTrades": len(rows),
            "actionableTrades": len(actionable),
            "resolvedTrades": len(resolved),
            "openTrades": max(0, len(actionable) - len(resolved)),
            "winRate": win_rate,
            "avgR": avg_rr_achieved,
            "avgRRAchieved": avg_rr_achieved,
            "maxDrawdownR": cls._max_drawdown([cls._f(r.get("realizedRR")) for r in executed]),
            "profitFactor": profit_factor,
            "noTradeRate": no_trade_rate,
            "bestPerformingSetup": cls._best_group(setup_performance, best=True),
            "worstPerformingSetup": cls._best_group(setup_performance, best=False),
            "performanceBySector": sector_performance,
            "setupPerformance": setup_performance,
            "outcomes": outcome_breakdown,
            "recentTrend": recent_trend,
            "recentTrades": rows[:15],
            "alerts": alerts,
            "observability": observability,
            "adaptiveIntelligence": adaptive_intelligence,
            "strategyInsights": {
                "bestPerformingSetup": cls._best_group(setup_performance, best=True),
                "worstPerformingSetup": cls._best_group(setup_performance, best=False),
                "suggestedFocusAreas": adaptive_intelligence.get("focusAreas", []),
                "confidenceThreshold": adaptive_intelligence.get("thresholds", {}).get("buyConfidence", 70.0),
            },
            # Backward-compatible fields
            "bestSetups": cls._best_rows(executed, best=True),
            "worstSetups": cls._best_rows(executed, best=False),
            "breakdown": {
                "sector": sector_performance,
                "setupType": setup_performance,
                "mode": cls._aggregate_by_key(executed, "mode"),
                "action": cls._aggregate_by_key(rows, "action", include_non_executed=True),
            },
        }

    @classmethod
    def get_adaptive_intelligence(cls, market_context: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = cls._load()
        actionable = [r for r in rows if str(r.get("action", "")).upper() == "BUY"]
        resolved = [r for r in actionable if r.get("outcome") in {"HIT_TARGET", "HIT_STOP_LOSS", "EXPIRED", "NO_ENTRY_TRIGGERED"}]
        executed = [r for r in resolved if r.get("outcome") != "NO_ENTRY_TRIGGERED"]
        recent_executed = executed[: cls.ADAPTIVE_LOOKBACK]

        setup_profiles = cls._build_performance_profiles(recent_executed, "setupType")
        sector_profiles = cls._build_performance_profiles(recent_executed, "sector")
        recent_win_rate = cls._win_rate(recent_executed)
        recent_avg_rr = cls._average([cls._f(r.get("realizedRR")) for r in recent_executed if r.get("realizedRR") is not None])
        regime = str((market_context or {}).get("regime") or "NEUTRAL").upper()

        buy_confidence = 70.0
        watch_confidence = 60.0
        top_pick_confidence = 70.0
        top_pick_rr = 2.0

        if recent_win_rate >= 62.0 and recent_avg_rr >= 0.8:
            buy_confidence -= 4.0
            watch_confidence -= 3.0
            top_pick_confidence -= 3.0
        elif recent_win_rate <= 45.0 or recent_avg_rr <= 0.15:
            buy_confidence += 5.0
            watch_confidence += 4.0
            top_pick_confidence += 5.0
            top_pick_rr += 0.2

        if regime in {"RANGE", "RISK-OFF", "WEAK"}:
            buy_confidence += 3.0
            top_pick_confidence += 3.0
            top_pick_rr += 0.1

        buy_confidence = cls._clamp(buy_confidence, 62.0, 82.0)
        watch_confidence = cls._clamp(watch_confidence, 52.0, 72.0)
        top_pick_confidence = cls._clamp(top_pick_confidence, 65.0, 85.0)
        top_pick_rr = cls._clamp(top_pick_rr, 1.5, 2.4)

        focus_areas = cls._build_focus_areas(setup_profiles, sector_profiles, recent_win_rate, recent_avg_rr)
        alerts = cls._performance_drop_alerts(setup_profiles, recent_win_rate)

        return {
            "sampleSize": len(recent_executed),
            "recentWinRate": round(recent_win_rate, 2),
            "recentAvgRR": round(recent_avg_rr, 2),
            "setupProfiles": setup_profiles,
            "sectorProfiles": sector_profiles,
            "focusAreas": focus_areas,
            "alerts": alerts,
            "thresholds": {
                "buyConfidence": round(buy_confidence, 2),
                "watchConfidence": round(watch_confidence, 2),
                "topPickConfidence": round(top_pick_confidence, 2),
                "topPickRR": round(top_pick_rr, 2),
            },
        }

    @classmethod
    def _build_trade_row(
        cls,
        hit: dict[str, Any],
        *,
        market_context: dict[str, Any] | None,
        mode: str,
    ) -> dict[str, Any]:
        plan = hit.get("executionPlan") or {}
        symbol = str(hit.get("symbol") or "UNKNOWN")
        hit_as_of = str(hit.get("hitAsOf") or hit.get("asOf") or datetime.now(timezone.utc).isoformat())
        timestamp = datetime.now(timezone.utc).isoformat()
        action = str(hit.get("action") or "NO TRADE").upper()
        entry = cls._f(plan.get("entry") or hit.get("entry"))
        stop_loss = cls._f(plan.get("stopLoss") or hit.get("stop_loss"))
        target = cls._f(plan.get("target1") or hit.get("target"))
        rr = cls._f(plan.get("riskRewardToT1") or hit.get("rr"))
        scan_price = cls._f(hit.get("price"))
        setup_type = str(hit.get("setupType") or "UNKNOWN")

        row = {
            "tradeKey": f"{symbol}_{action}_{mode}_{hit_as_of}",
            "symbol": symbol,
            "action": action,
            "score": cls._f(hit.get("score")),
            "confidence": cls._f(hit.get("confidence")),
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "rr": rr,
            "market_context": market_context or hit.get("marketContext") or {},
            "mode": str(mode or hit.get("userMode") or "safe"),
            "timestamp": timestamp,
            "hitAsOf": hit_as_of,
            "scanPrice": scan_price,
            "sector": str(hit.get("sector") or "UNKNOWN"),
            "setupType": setup_type,
            "explanation": str(hit.get("explanation") or ""),
            "forward3dReturn": hit.get("forward3dReturn"),
            "entryType": plan.get("entryType"),
            "confirmationMode": plan.get("confirmationMode"),
            "entryTriggered": bool(entry > 0 and (scan_price >= entry or plan.get("confirmationMode") != "BREAKOUT_TRIGGER")),
        }
        outcome = cls._evaluate_outcome(row)
        row.update(outcome)
        return row

    @classmethod
    def _evaluate_outcome(cls, row: dict[str, Any]) -> dict[str, Any]:
        action = str(row.get("action") or "NO TRADE").upper()
        if action != "BUY":
            return {"outcome": "NO_ENTRY_TRIGGERED", "realizedRR": 0.0, "pnlPct": 0.0}

        entry = cls._f(row.get("entry"))
        stop = cls._f(row.get("stop_loss"))
        target = cls._f(row.get("target"))
        scan_price = cls._f(row.get("scanPrice"))
        forward = row.get("forward3dReturn")
        age_days = cls._age_days(row.get("hitAsOf"))
        risk_pct = ((entry - stop) / entry) * 100 if entry > stop > 0 else 0.0

        if entry <= 0 or target <= 0 or risk_pct <= 0:
            return {"outcome": "NO_ENTRY_TRIGGERED", "realizedRR": 0.0, "pnlPct": 0.0}

        if forward is None:
            if age_days >= cls.EXPIRY_DAYS:
                if entry > scan_price and not bool(row.get("entryTriggered")):
                    return {"outcome": "NO_ENTRY_TRIGGERED", "realizedRR": 0.0, "pnlPct": 0.0}
                return {"outcome": "EXPIRED", "realizedRR": 0.0, "pnlPct": 0.0}
            return {"outcome": "PENDING", "realizedRR": None, "pnlPct": None}

        pnl_pct = cls._f(forward)
        target_pct = ((target - entry) / entry) * 100
        realized_rr = round((pnl_pct / risk_pct), 2) if risk_pct > 0 else 0.0

        if pnl_pct >= target_pct:
            return {"outcome": "HIT_TARGET", "realizedRR": max(realized_rr, cls._f(row.get("rr")) or 1.0), "pnlPct": round(pnl_pct, 2)}
        if pnl_pct <= -risk_pct:
            return {"outcome": "HIT_STOP_LOSS", "realizedRR": -1.0, "pnlPct": round(pnl_pct, 2)}
        return {"outcome": "EXPIRED", "realizedRR": round(realized_rr, 2), "pnlPct": round(pnl_pct, 2)}

    @classmethod
    def _aggregate_by_key(
        cls,
        rows: list[dict[str, Any]],
        key: str,
        *,
        include_non_executed: bool = False,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            buckets.setdefault(label, []).append(row)

        out: list[dict[str, Any]] = []
        for label, bucket in buckets.items():
            wins = [r for r in bucket if r.get("outcome") == "HIT_TARGET"]
            resolved = [r for r in bucket if include_non_executed or r.get("outcome") in {"HIT_TARGET", "HIT_STOP_LOSS", "EXPIRED"}]
            rr_values = [cls._f(r.get("realizedRR")) for r in resolved if r.get("realizedRR") is not None]
            out.append({
                "label": label,
                "count": len(bucket),
                "resolved": len(resolved),
                "winRate": round((len(wins) / len(resolved)) * 100, 2) if resolved else 0.0,
                "avgRR": round(sum(rr_values) / len(rr_values), 2) if rr_values else 0.0,
            })

        out.sort(key=lambda item: (item["winRate"], item["avgRR"], item["count"]), reverse=True)
        return out

    @classmethod
    def _best_group(cls, groups: list[dict[str, Any]], *, best: bool) -> dict[str, Any]:
        if not groups:
            return {"label": "—", "winRate": 0.0, "avgRR": 0.0}
        sorted_groups = sorted(groups, key=lambda item: (item["winRate"], item["avgRR"], item["count"]), reverse=best)
        return sorted_groups[0]

    @classmethod
    def _best_rows(cls, rows: list[dict[str, Any]], *, best: bool) -> list[dict[str, Any]]:
        sorted_rows = sorted(rows, key=lambda r: cls._f(r.get("realizedRR")), reverse=best)
        return [
            {
                "symbol": r.get("symbol"),
                "pnlR": cls._f(r.get("realizedRR")),
                "sector": r.get("sector"),
                "setupType": r.get("setupType"),
                "mode": r.get("mode"),
            }
            for r in sorted_rows[:5]
        ]

    @classmethod
    def _outcome_breakdown(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        labels = ["HIT_TARGET", "HIT_STOP_LOSS", "EXPIRED", "NO_ENTRY_TRIGGERED", "PENDING"]
        counts = {label: 0 for label in labels}
        for row in rows:
            outcome = str(row.get("outcome") or "PENDING")
            counts[outcome] = counts.get(outcome, 0) + 1
        return [{"label": label, "count": counts.get(label, 0)} for label in labels]

    @classmethod
    def _daily_trend(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            day = str(row.get("timestamp", ""))[:10] or "UNKNOWN"
            bucket = buckets.setdefault(day, {"date": day, "count": 0, "wins": 0, "rrTotal": 0.0, "resolved": 0})
            bucket["count"] += 1
            if row.get("outcome") == "HIT_TARGET":
                bucket["wins"] += 1
            if row.get("outcome") in {"HIT_TARGET", "HIT_STOP_LOSS", "EXPIRED"}:
                bucket["resolved"] += 1
                bucket["rrTotal"] += cls._f(row.get("realizedRR"))

        trend = []
        for day, bucket in sorted(buckets.items()):
            resolved = int(bucket["resolved"])
            trend.append({
                "date": day,
                "count": int(bucket["count"]),
                "winRate": round((int(bucket["wins"]) / resolved) * 100, 2) if resolved else 0.0,
                "avgRR": round(float(bucket["rrTotal"]) / resolved, 2) if resolved else 0.0,
            })
        return trend[-10:]

    @classmethod
    def _build_alerts(
        cls,
        all_rows: list[dict[str, Any]],
        executed_rows: list[dict[str, Any]],
        no_trade_rate: float,
        win_rate: float,
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if no_trade_rate >= 80.0 and len(all_rows) >= 10:
            alerts.append({
                "severity": "warning",
                "type": "NO_TRADE_CLUSTER",
                "message": f"No-trade rate is elevated at {no_trade_rate:.1f}%.",
            })

        recent_resolved = executed_rows[:10]
        previous_resolved = executed_rows[10:20]
        if recent_resolved and previous_resolved:
            recent_win = round((sum(1 for r in recent_resolved if r.get("outcome") == "HIT_TARGET") / len(recent_resolved)) * 100, 2)
            prev_win = round((sum(1 for r in previous_resolved if r.get("outcome") == "HIT_TARGET") / len(previous_resolved)) * 100, 2)
            if recent_win <= prev_win - 20:
                alerts.append({
                    "severity": "critical",
                    "type": "WIN_RATE_DROP",
                    "message": f"Recent win rate dropped from {prev_win:.1f}% to {recent_win:.1f}%.",
                })

        inconsistent = [r for r in all_rows if cls._has_data_inconsistency(r)]
        if inconsistent:
            alerts.append({
                "severity": "warning",
                "type": "DATA_INCONSISTENCY",
                "message": f"{len(inconsistent)} trade records have inconsistent entry/stop/target values.",
            })
            ObservabilityService.record_data_inconsistency("trade_log", {"count": len(inconsistent)})

        adaptive_alerts = cls._performance_drop_alerts(cls._build_performance_profiles(executed_rows[: cls.ADAPTIVE_LOOKBACK], "setupType"), win_rate)
        alerts.extend(adaptive_alerts)

        if not alerts and win_rate == 0 and executed_rows:
            alerts.append({
                "severity": "info",
                "type": "PERFORMANCE_MONITOR",
                "message": "No winning trades recorded in the latest resolved sample.",
            })
        return alerts

    @classmethod
    def _has_data_inconsistency(cls, row: dict[str, Any]) -> bool:
        action = str(row.get("action") or "").upper()
        if action != "BUY":
            return False
        entry = cls._f(row.get("entry"))
        stop = cls._f(row.get("stop_loss"))
        target = cls._f(row.get("target"))
        rr = cls._f(row.get("rr"))
        return entry <= 0 or stop <= 0 or target <= 0 or not (stop < entry < target) or rr < 0

    @classmethod
    def _profit_factor(cls, rows: list[dict[str, Any]]) -> float:
        gains = sum(max(cls._f(r.get("realizedRR")), 0.0) for r in rows)
        losses = abs(sum(min(cls._f(r.get("realizedRR")), 0.0) for r in rows))
        if losses == 0:
            return round(gains, 2) if gains else 0.0
        return round(gains / losses, 2)

    @classmethod
    def _max_drawdown(cls, pnl_rs: list[float]) -> float:
        if not pnl_rs:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnl_rs:
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
        return round(max_dd, 2)

    @staticmethod
    def _age_days(hit_as_of: Any) -> int:
        try:
            text = str(hit_as_of)
            if text.endswith("Z"):
                text = text.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days)
        except Exception:
            return 0

    @staticmethod
    def _f(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0

    @classmethod
    def _build_performance_profiles(cls, rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            buckets.setdefault(label, []).append(row)

        profiles: dict[str, dict[str, Any]] = {}
        for label, bucket in buckets.items():
            recent = bucket[: cls.PROFILE_RECENT_WINDOW]
            win_rate = cls._win_rate(bucket)
            recent_win_rate = cls._win_rate(recent)
            avg_rr = cls._average([cls._f(r.get("realizedRR")) for r in bucket if r.get("realizedRR") is not None])
            recent_avg_rr = cls._average([cls._f(r.get("realizedRR")) for r in recent if r.get("realizedRR") is not None])
            avg_pnl_pct = cls._average([cls._f(r.get("pnlPct")) for r in bucket if r.get("pnlPct") is not None])
            recent_pnl_pct = cls._average([cls._f(r.get("pnlPct")) for r in recent if r.get("pnlPct") is not None])
            trend_delta = round(recent_win_rate - win_rate, 2)
            sample_ratio = min(1.0, len(bucket) / max(float(cls.PROFILE_MIN_SAMPLE), 1.0))
            edge = (((win_rate - 50.0) / 100.0) * 0.6) + (avg_rr * 0.08)
            weight = cls._clamp(1.0 + (edge * sample_ratio), 0.75, 1.25)
            confidence_adjustment = cls._clamp((((win_rate - 50.0) / 5.0) + (trend_delta / 10.0)) * sample_ratio, -10.0, 10.0)

            profiles[label] = {
                "label": label,
                "trades": len(bucket),
                "winRate": round(win_rate, 2),
                "recentWinRate": round(recent_win_rate, 2),
                "winRateDelta": trend_delta,
                "avgRR": round(avg_rr, 2),
                "recentAvgRR": round(recent_avg_rr, 2),
                "avgPnLPct": round(avg_pnl_pct, 2),
                "recentPnLPct": round(recent_pnl_pct, 2),
                "weight": round(weight, 3),
                "confidenceAdjustment": round(confidence_adjustment, 2),
                "underperforming": len(bucket) >= cls.PROFILE_MIN_SAMPLE and (recent_win_rate <= 40.0 or trend_delta <= -20.0 or recent_avg_rr < 0),
            }

        return profiles

    @classmethod
    def _build_focus_areas(
        cls,
        setup_profiles: dict[str, dict[str, Any]],
        sector_profiles: dict[str, dict[str, Any]],
        recent_win_rate: float,
        recent_avg_rr: float,
    ) -> list[str]:
        focus: list[str] = []
        sorted_setups = sorted(setup_profiles.values(), key=lambda item: (item["weight"], item["winRate"], item["avgRR"]), reverse=True)
        sorted_sectors = sorted(sector_profiles.values(), key=lambda item: (item["weight"], item["recentPnLPct"], item["winRate"]), reverse=True)
        lagging_setups = [item for item in setup_profiles.values() if item.get("underperforming")]

        if sorted_setups:
            top_setup = sorted_setups[0]
            focus.append(f"Lean into {top_setup['label']} setups ({top_setup['winRate']:.0f}% win rate, {top_setup['avgRR']:.2f} avg RR).")
        if sorted_sectors:
            top_sector = sorted_sectors[0]
            focus.append(f"Favor {top_sector['label']} when signals align ({top_sector['recentPnLPct']:+.1f}% recent sector performance).")
        if lagging_setups:
            weakest = sorted(lagging_setups, key=lambda item: (item["recentWinRate"], item["recentAvgRR"]))[0]
            focus.append(f"Reduce size or wait for stronger confirmation on {weakest['label']} until the win rate stabilizes.")
        if recent_win_rate <= 45.0:
            focus.append("Raise execution standards temporarily because recent trade win rate has cooled off.")
        elif recent_avg_rr >= 1.0:
            focus.append("Recent payoff quality is strong; keep prioritizing high-RR confirmations.")

        return focus[:4]

    @classmethod
    def _performance_drop_alerts(cls, setup_profiles: dict[str, dict[str, Any]], overall_win_rate: float) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        if overall_win_rate and overall_win_rate < 45.0:
            alerts.append({
                "severity": "warning",
                "type": "WIN_RATE_BELOW_THRESHOLD",
                "message": f"Execution win rate slipped to {overall_win_rate:.1f}%. Tighten confidence thresholds until performance recovers.",
            })

        for profile in sorted(setup_profiles.values(), key=lambda item: (item["recentWinRate"], item["winRateDelta"])):
            if not profile.get("underperforming"):
                continue
            alerts.append({
                "severity": "warning",
                "type": "SETUP_UNDERPERFORMING",
                "message": f"{profile['label']} win rate fell to {profile['recentWinRate']:.1f}% ({profile['winRateDelta']:.1f} pts vs baseline).",
            })
            if len(alerts) >= 3:
                break

        return alerts

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @classmethod
    def _win_rate(cls, rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        wins = sum(1 for row in rows if row.get("outcome") == "HIT_TARGET")
        return (wins / len(rows)) * 100.0

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
