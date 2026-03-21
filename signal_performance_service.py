from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SignalPerformance:
    earlySetups: int
    entryReady: int
    strongEntry: int
    convertedToEntryReady: int
    convertedToStrongEntry: int
    conversionRateEarlyToEntry: int
    conversionRateEntryToStrong: int
    asOfDate: str
    asOfTime: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "earlySetups": self.earlySetups,
            "entryReady": self.entryReady,
            "strongEntry": self.strongEntry,
            "convertedToEntryReady": self.convertedToEntryReady,
            "convertedToStrongEntry": self.convertedToStrongEntry,
            "conversionRateEarlyToEntry": self.conversionRateEarlyToEntry,
            "conversionRateEntryToStrong": self.conversionRateEntryToStrong,
            "asOfDate": self.asOfDate,
            "asOfTime": self.asOfTime,
        }


class SignalPerformanceService:
    """
    Analytics/performance layer for signal tracking.
    Does NOT modify scoring, SectorService, or screener signal generation.

    Conversion tracking is implemented as a 'same-scan overlap' metric:
    - Early → Entry Ready: symbols that appear in Early Setups AND have ENTRY_READY now
    - Early → Strong Entry: symbols that appear in Early Setups AND have STRONG_ENTRY now

    This is a stable first step; deeper intraday evolution can be added later using time-series logs.
    """

    _log_path = Path(__file__).resolve().parent.parent / "data" / "signal_performance_daily.json"

    @classmethod
    def compute(cls, timeframe: str = "1D", limit: int = 2000) -> SignalPerformance:
        from app.services.screener_service import ScreenerService

        hits = ScreenerService.get_screener_data(timeframe=timeframe) or []
        early = ScreenerService.get_early_breakout_setups(timeframe=timeframe, limit=limit) or []

        entry_ready_syms = {h.get("symbol") for h in hits if (h.get("entryTag") == "ENTRY_READY")}
        strong_entry_syms = {h.get("symbol") for h in hits if (h.get("entryTag") == "STRONG_ENTRY")}

        early_syms = {e.get("symbol") for e in early}

        converted_entry = len({s for s in early_syms if s in entry_ready_syms})
        converted_strong = len({s for s in early_syms if s in strong_entry_syms})

        early_count = len(early)
        entry_ready_count = len(entry_ready_syms)
        strong_entry_count = len(strong_entry_syms)

        conv_early_to_entry = int(round((converted_entry / early_count) * 100)) if early_count else 0
        conv_entry_to_strong = int(round((strong_entry_count / entry_ready_count) * 100)) if entry_ready_count else 0

        now = datetime.now()
        perf = SignalPerformance(
            earlySetups=early_count,
            entryReady=entry_ready_count,
            strongEntry=strong_entry_count,
            convertedToEntryReady=converted_entry,
            convertedToStrongEntry=converted_strong,
            conversionRateEarlyToEntry=conv_early_to_entry,
            conversionRateEntryToStrong=conv_entry_to_strong,
            asOfDate=now.strftime("%Y-%m-%d"),
            asOfTime=now.strftime("%H:%M:%S"),
        )
        cls._log_daily(perf)
        return perf

    @classmethod
    def _log_daily(cls, perf: SignalPerformance) -> None:
        """
        Persist one record per date (overwrites for the day on each compute).
        This keeps the file small and enables longitudinal analysis.
        """
        try:
            cls._log_path.parent.mkdir(parents=True, exist_ok=True)
            existing: dict[str, Any] = {}
            if cls._log_path.exists():
                try:
                    existing = json.loads(cls._log_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    existing = {}

            existing[str(perf.asOfDate)] = perf.to_dict()
            cls._log_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        except Exception:
            # Logging must never break the API.
            return

