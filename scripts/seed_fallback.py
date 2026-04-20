import json
import time
from pathlib import Path

def seed_fallbacks():
    data_dir = Path("backend/app/data")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Seed Sector Fallback
    sector_data = {
        "NIFTY_AUTO": {"metrics": {"state": "LEADING", "momentumScore": 120.5, "rotationScore": 8.5}, "rank": 1},
        "NIFTY_IT": {"metrics": {"state": "IMPROVING", "momentumScore": 95.2, "rotationScore": 6.2}, "rank": 2},
        "NIFTY_FMCG": {"metrics": {"state": "WEAKENING", "momentumScore": 75.8, "rotationScore": 4.1}, "rank": 3},
        "NIFTY_METAL": {"metrics": {"state": "LAGGING", "momentumScore": 45.3, "rotationScore": 2.1}, "rank": 4},
        "NIFTY_BANK": {"metrics": {"state": "LEADING", "momentumScore": 115.7, "rotationScore": 7.9}, "rank": 5},
        "NIFTY_PHARMA": {"metrics": {"state": "NEUTRAL", "momentumScore": 60.1, "rotationScore": 3.5}, "rank": 6},
        "NIFTY_REALTY": {"metrics": {"state": "LEADING", "momentumScore": 130.2, "rotationScore": 9.1}, "rank": 7},
        "NIFTY_ENERGY": {"metrics": {"state": "IMPROVING", "momentumScore": 88.4, "rotationScore": 5.8}, "rank": 8},
        "NIFTY_PSU_BANK": {"metrics": {"state": "LAGGING", "momentumScore": 32.1, "rotationScore": 1.5}, "rank": 9}
    }
    
    with open(data_dir / "sector_fallback.json", "w") as f:
        json.dump({
            "data": sector_data,
            "alerts": [],
            "timestamp": time.time(),
            "timeframe": "15m"
        }, f)
        
    # 2. Seed Screener Fallback
    hits_data = [
        {
            "symbol": "BRIGADE",
            "sector": "REALTY",
            "price": 745.3,
            "change": 0.04,
            "volume": 1250000,
            "confidence": 65,
            "grade": "B",
            "entryTag": "ENTRY_READY",
            "isLatestSession": True,
            "technical": {"qualityScore": 65, "institutionalActivity": "HIGH", "momentumStrength": "STRONG"}
        },
        {
            "symbol": "TCS",
            "sector": "IT",
            "price": 3850.5,
            "change": 1.2,
            "volume": 2100000,
            "confidence": 72,
            "grade": "A",
            "entryTag": "WATCHLIST",
            "isLatestSession": True,
            "technical": {"qualityScore": 72, "institutionalActivity": "MODERATE", "momentumStrength": "STABLE"}
        }
    ]
    
    with open(data_dir / "screener_fallback.json", "w") as f:
        json.dump({
            "data": hits_data,
            "timestamp": time.time(),
            "timeframe": "15m"
        }, f)

    print("Successfully seeded fallback data files.")

if __name__ == "__main__":
    seed_fallbacks()
