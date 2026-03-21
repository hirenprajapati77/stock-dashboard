import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from app.services.signal_filter_service import SignalFilterService

class SignalArchiveService:
    ARCHIVE_FILE = Path(__file__).parent.parent / "data" / "signal_archive.json"
    MAX_ARCHIVE_SIZE = 500  # Total signals to keep in history
    STATS_WINDOW = 100      # Window for rolling stats

    @classmethod
    def initialize(cls):
        """Ensures the archive file and data directory exist."""
        cls.ARCHIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not cls.ARCHIVE_FILE.exists():
            with open(cls.ARCHIVE_FILE, "w") as f:
                json.dump([], f)

    @classmethod
    def archive_signals(cls, hits: List[Dict]):
        """
        Archives signals that have a valid outcome (forward3dReturn).
        Prevents duplicate archiving by checking symbol and hit date.
        """
        cls.initialize()
        
        valid_completed = []
        for h in (hits or []):
            if not isinstance(h, dict) or h.get("forward3dReturn") is None:
                continue

            meta = h.get("filterMeta") if isinstance(h.get("filterMeta"), dict) else SignalFilterService.compute_filter_meta(h).to_dict()
            if meta is None: meta = {}
            valid_completed.append({
                "symbol": str(h.get("symbol", "UNKNOWN")),
                "hitAsOf": str(h.get("hitAsOf", "")),
                "forward3dReturn": float(h["forward3dReturn"]),
                "sector": str(h.get("sector", "Unknown")),
                "confidence": str(h.get("confidence", "C")),
                "qualityScore": float(h.get("technical", {}).get("qualityScore", 0.0)),
                "filterCategory": str(meta.get("filterCategory", "UNKNOWN")),
                "filterScore": int(meta.get("filterScore", 0)),
                "archivedAt": datetime.now().isoformat()
            })

        if not valid_completed:
            return

        with open(cls.ARCHIVE_FILE, "r") as f:
            archive = json.load(f)

        existing_keys = {f"{s['symbol']}_{s['hitAsOf']}" for s in archive}
        
        newly_added = 0
        for signal in valid_completed:
            key = f"{signal['symbol']}_{signal['hitAsOf']}"
            if key not in existing_keys:
                archive.append(signal)
                newly_added += 1

        if newly_added > 0:
            # Sort by hitAsOf descending and trim
            archive.sort(key=lambda x: x["hitAsOf"], reverse=True)
            archive = archive[:cls.MAX_ARCHIVE_SIZE]
            
            with open(cls.ARCHIVE_FILE, "w") as f:
                json.dump(archive, f, indent=2)
            print(f"DEBUG: Archived {newly_added} new signals. Total archive: {len(archive)}")

    @classmethod
    def get_performance_metrics(cls) -> Dict:
        """
        Calculates advanced performance metrics from the last STATS_WINDOW completed signals.
        """
        cls.initialize()
        with open(cls.ARCHIVE_FILE, "r") as f:
            archive = json.load(f)

        # We evaluate signals AFTER outcome known (already filtered by forward3dReturn is not None)
        signals = archive[:cls.STATS_WINDOW]
        
        if not signals:
            return {
                "totalSignals": 0,
                "winRate": 0,
                "avgReturn": 0,
                "bestSector": "N/A",
                "worstSector": "N/A",
                "accuracyByGrade": {"A": 0, "B": 0, "C": 0, "D": 0}
            }

        total = len(signals)
        wins = [s for s in signals if s["forward3dReturn"] > 0]
        win_rate = (len(wins) / total) * 100
        avg_return = sum(s["forward3dReturn"] for s in signals) / total

        # Sector Stats
        sector_stats: Dict[str, List[float]] = {}
        for s in signals:
            sector = str(s.get("sector", "Unknown"))
            if sector not in sector_stats: sector_stats[sector] = []
            sector_stats[sector].append(float(s.get("forward3dReturn", 0.0)))

        sector_accuracy = {}
        for sector, returns in sector_stats.items():
            valid_returns = [float(r) for r in returns if r is not None]
            if not valid_returns:
                sector_accuracy[sector] = 0.0
                continue
            win_count = len([r for r in valid_returns if r > 0])
            sector_accuracy[sector] = (win_count / len(valid_returns)) * 100

        best_sector = max(sector_accuracy.items(), key=lambda x: x[1])[0] if sector_accuracy else "N/A"
        worst_sector = min(sector_accuracy.items(), key=lambda x: x[1])[0] if sector_accuracy else "N/A"

        # Grade Accuracy
        grade_stats = {"A": [], "B": [], "C": [], "D": []}
        for s in signals:
            grade = s["confidence"]
            if grade in grade_stats:
                grade_stats[grade].append(s["forward3dReturn"])

        accuracy_by_grade = {}
        for grade, returns in grade_stats.items():
            if not returns:
                accuracy_by_grade[grade] = 0.0
                continue
            win_count = len([r for r in returns if r > 0])
            accuracy_by_grade[grade] = float(round((win_count / len(returns)) * 100.0, 2))

        # Filter category tracking (post-scoring optimization layer)
        category_stats = {"HIGH PROBABILITY": [], "MEDIUM": [], "LOW": []}
        for s in signals:
            cat = s.get("filterCategory")
            if cat in category_stats:
                category_stats[cat].append(s["forward3dReturn"])

        win_rate_by_filter = {}
        count_by_filter = {}
        for cat, returns in category_stats.items():
            count_by_filter[cat] = len(returns)
            if not returns:
                win_rate_by_filter[cat] = 0.0
                continue
            wins_cat = len([r for r in returns if r > 0])
            win_rate_by_filter[cat] = float(round((wins_cat / len(returns)) * 100.0, 2))

        high_med = category_stats["HIGH PROBABILITY"] + category_stats["MEDIUM"]
        prioritized_win_rate = float(round((len([r for r in high_med if r > 0]) / len(high_med)) * 100.0, 2)) if high_med else 0.0

        res = {
            "totalSignals": total,
            "winRate": float(round(win_rate, 2)),
            "avgReturn": float(round(avg_return, 2)),
            "bestSector": best_sector,
            "worstSector": worst_sector,
            "accuracyByGrade": accuracy_by_grade,
            "sectorAccuracy": {k: float(round(v, 2)) for k, v in sector_accuracy.items()},
            "filterCategoryWinRate": win_rate_by_filter,
            "filterCategoryCounts": count_by_filter,
            "prioritizedWinRate": prioritized_win_rate,
            "winRateLiftVsBaseline": float(round(prioritized_win_rate - round(win_rate, 2), 2)) if high_med else 0.0,
        }

        # Improvement 3: System Performance Stability
        if total < 30:
            res["insufficientData"] = True
            # Mask sensitive metrics when data is insufficient for reliable stats
            res["winRate"] = 0
            res["avgReturn"] = 0
            
        return res
