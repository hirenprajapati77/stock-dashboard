from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class TradeTrackingService:
    LOG_FILE = Path(__file__).parent.parent / "data" / "trade_log.json"
    MAX_LOG = 1000

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
    def log_trades(cls, hits: list[dict[str, Any]]) -> None:
        rows = cls._load()
        existing = {r.get("tradeKey") for r in rows}

        for h in hits or []:
            plan = h.get("executionPlan") or {}
            symbol = h.get("symbol")
            hit_as_of = h.get("hitAsOf") or h.get("asOf") or datetime.now().strftime("%Y-%m-%d")
            key = f"{symbol}_{hit_as_of}"
            if key in existing:
                continue

            entry = cls._f(plan.get("entry"))
            stop = cls._f(plan.get("stopLoss"))
            t1 = cls._f(plan.get("target1"))
            t2 = cls._f(plan.get("target2"))
            fwd = h.get("forward3dReturn")

            outcome, pnl_r, pnl_pct = cls._evaluate_outcome(entry, stop, t1, t2, fwd)

            rows.insert(0, {
                "tradeKey": key,
                "symbol": symbol,
                "timestamp": datetime.now().isoformat(),
                "hitAsOf": hit_as_of,
                "entry": entry,
                "stopLoss": stop,
                "target1": t1,
                "target2": t2,
                "tradeQuality": plan.get("tradeQuality", "LOW QUALITY TRADE"),
                "executionConfidence": plan.get("executionConfidence", "LOW"),
                "filterCategory": h.get("filterCategory", "UNKNOWN"),
                "sector": h.get("sector", "UNKNOWN"),
                "riskRewardToT1": cls._f(plan.get("riskRewardToT1")),
                "outcome": outcome,
                "pnlR": round(pnl_r, 2),
                "pnlPct": round(pnl_pct, 2),
                "forward3dReturn": fwd,
            })
            existing.add(key)

        cls._save(rows)

    @classmethod
    def get_performance(cls) -> dict[str, Any]:
        rows = cls._load()
        resolved = [r for r in rows if r.get("outcome") in {"HIT_SL", "HIT_T1", "HIT_T2"}]
        pnl_rs = [cls._f(r.get("pnlR")) for r in resolved]

        wins = [r for r in resolved if cls._f(r.get("pnlR")) > 0]
        losses = [r for r in resolved if cls._f(r.get("pnlR")) < 0]

        total = len(rows)
        resolved_n = len(resolved)
        win_rate = round((len(wins) / resolved_n) * 100, 2) if resolved_n else 0.0
        avg_r = round(sum(pnl_rs) / resolved_n, 2) if resolved_n else 0.0

        gross_profit = sum(cls._f(r.get("pnlR")) for r in wins)
        gross_loss_abs = abs(sum(cls._f(r.get("pnlR")) for r in losses))
        profit_factor = round(gross_profit / gross_loss_abs, 2) if gross_loss_abs > 0 else (round(gross_profit, 2) if gross_profit > 0 else 0.0)

        max_dd = cls._max_drawdown(pnl_rs)

        return {
            "totalTrades": total,
            "resolvedTrades": resolved_n,
            "openTrades": total - resolved_n,
            "winRate": win_rate,
            "avgR": avg_r,
            "maxDrawdownR": max_dd,
            "profitFactor": profit_factor,
            "bestSetups": cls._best_worst(rows, best=True),
            "worstSetups": cls._best_worst(rows, best=False),
            "breakdown": {
                "filterCategory": cls._breakdown(rows, "filterCategory"),
                "sector": cls._breakdown(rows, "sector"),
                "tradeQuality": cls._breakdown(rows, "tradeQuality"),
                "executionConfidence": cls._breakdown(rows, "executionConfidence"),
            },
        }

    @classmethod
    def _evaluate_outcome(cls, entry: float, stop: float, t1: float, t2: float, forward3d_return: Any) -> tuple[str, float, float]:
        if forward3d_return is None:
            return "STILL_OPEN", 0.0, 0.0

        ret_pct = cls._f(forward3d_return)
        if entry <= 0:
            return ("HIT_T1" if ret_pct > 0 else "HIT_SL"), (1.0 if ret_pct > 0 else -1.0), ret_pct

        t1_pct = ((t1 - entry) / entry) * 100 if t1 > 0 else 0.0
        t2_pct = ((t2 - entry) / entry) * 100 if t2 > 0 else 0.0
        sl_pct = ((entry - stop) / entry) * 100 if stop > 0 and entry > stop else 1.0

        if ret_pct >= t2_pct > 0:
            return "HIT_T2", 2.0, ret_pct
        if ret_pct >= t1_pct > 0:
            return "HIT_T1", 1.5, ret_pct
        if ret_pct <= -sl_pct:
            return "HIT_SL", -1.0, ret_pct
        return "STILL_OPEN", 0.0, ret_pct

    @classmethod
    def _breakdown(cls, rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        bucket: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            k = str(r.get(key, "UNKNOWN"))
            bucket.setdefault(k, []).append(r)

        out: dict[str, Any] = {}
        for k, vals in bucket.items():
            resolved = [v for v in vals if v.get("outcome") in {"HIT_SL", "HIT_T1", "HIT_T2"}]
            wins = [v for v in resolved if cls._f(v.get("pnlR")) > 0]
            out[k] = {
                "count": len(vals),
                "resolved": len(resolved),
                "winRate": round((len(wins) / len(resolved)) * 100, 2) if resolved else 0.0,
                "avgR": round(sum(cls._f(v.get("pnlR")) for v in resolved) / len(resolved), 2) if resolved else 0.0,
            }
        return out

    @classmethod
    def _best_worst(cls, rows: list[dict[str, Any]], best: bool) -> list[dict[str, Any]]:
        resolved = [r for r in rows if r.get("outcome") in {"HIT_SL", "HIT_T1", "HIT_T2"}]
        sorted_rows = sorted(resolved, key=lambda r: cls._f(r.get("pnlR")), reverse=best)
        return [
            {
                "symbol": r.get("symbol"),
                "pnlR": cls._f(r.get("pnlR")),
                "sector": r.get("sector"),
                "filterCategory": r.get("filterCategory"),
                "tradeQuality": r.get("tradeQuality"),
            }
            for r in sorted_rows[:5]
        ]

    @classmethod
    def _max_drawdown(cls, pnl_rs: list[float]) -> float:
        if not pnl_rs:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in pnl_rs:
            equity += r
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)
        return round(max_dd, 2)

    @staticmethod
    def _f(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0
