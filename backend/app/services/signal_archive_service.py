import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

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
        
        valid_completed = [
            {
                "symbol": h["symbol"],
                "hitAsOf": h["hitAsOf"],
                "forward3dReturn": h["forward3dReturn"],
                "sector": h.get("sector", "Unknown"),
                "confidence": h.get("confidence", "C"),
                "qualityScore": h.get("technical", {}).get("qualityScore", 0),
                "archivedAt": datetime.now().isoformat()
            }
            for h in hits if h.get("forward3dReturn") is not None
        ]

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
        sector_stats = {}
        for s in signals:
            sector = s["sector"]
            sector_stats.setdefault(sector, []).append(s["forward3dReturn"])

        sector_accuracy = {}
        for sector, returns in sector_stats.items():
            win_count = len([r for r in returns if r > 0])
            sector_accuracy[sector] = (win_count / len(returns)) * 100

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
            accuracy_by_grade[grade] = round((win_count / len(returns)) * 100, 2)

        return {
            "totalSignals": total,
            "winRate": round(win_rate, 2),
            "avgReturn": round(avg_return, 2),
            "bestSector": best_sector,
            "worstSector": worst_sector,
            "accuracyByGrade": accuracy_by_grade,
            "sectorAccuracy": {k: round(v, 2) for k, v in sector_accuracy.items()}
        }
