import json
import time
from pathlib import Path

def seed_fallback():
    data = {
        "NIFTY_BANK": {
            "current": {"date": "2026-02-09", "rs": 1.05, "rm": 0.002},
            "history": [{"date": "2026-02-09", "rs": 1.05, "rm": 0.002}],
            "weight": 0.33,
            "rank": 1,
            "metrics": {"breadth": 75.0, "relVolume": 1.5, "state": "SHINING", "momentumScore": 150.0, "shift": "GAINING"},
            "commentary": "Nifty Bank showing strong relative strength and momentum. Retail and PSU banks leading the charge."
        },
        "NIFTY_IT": {
            "current": {"date": "2026-02-09", "rs": 1.02, "rm": -0.001},
            "history": [{"date": "2026-02-09", "rs": 1.02, "rm": -0.001}],
            "weight": 0.14,
            "rank": 2,
            "metrics": {"breadth": 60.0, "relVolume": 1.1, "state": "NEUTRAL", "momentumScore": 105.0, "shift": "NEUTRAL"},
            "commentary": "Nifty IT is consolidating after a recent run-up. High-growth midcaps are decoupling from majors."
        },
        "NIFTY_FMCG": {
            "current": {"date": "2026-02-09", "rs": 0.98, "rm": -0.004},
            "history": [{"date": "2026-02-09", "rs": 0.98, "rm": -0.004}],
            "weight": 0.09,
            "rank": 3,
            "metrics": {"breadth": 40.0, "relVolume": 0.8, "state": "WEAK", "momentumScore": 80.0, "shift": "LOSING"},
            "commentary": "FMCG remains defensive but lacks aggressive buying interest at these levels."
        }
    }
    
    fallback_data = {
        "data": data,
        "alerts": [
            {"symbol": "NIFTY_BANK", "type": "ENTER_SHINING", "rs": 1.05, "rm": 0.002, "priority": "HIGH", "timestamp": time.time()}
        ],
        "timestamp": time.time(),
        "timeframe": "1D"
    }
    
    fallback_path = Path("app/data/sector_fallback.json")
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fallback_path, "w") as f:
        json.dump(fallback_data, f, indent=4)
    print(f"Seeded fallback at {fallback_path.absolute()}")

if __name__ == "__main__":
    seed_fallback()
