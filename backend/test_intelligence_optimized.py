
import sys
import os
import time
import json
import pandas as pd

# Add backend to path
sys.path.append(os.path.join(os.getcwd()))

from app.services.sector_service import SectorService
from app.services.screener_service import ScreenerService

def test_sector_rotation():
    print("--- Testing Sector Rotation (Optimized) ---")
    start_time = time.time()
    try:
        data, alerts = SectorService.get_rotation_data(timeframe="1D")
        elapsed = time.time() - start_time
        print(f"Fetch completed in {elapsed:.2f}s")
        print(f"Sectors found: {len(data)}")
        if not data:
            print("WARNING: No data returned from SectorService!")
        for name, details in list(data.items())[:3]:
            print(f"  {name}: RS={details['current']['rs']}, State={details['metrics']['state']}")
        print(f"Alerts generated: {len(alerts)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR in Sector Rotation: {e}")

def test_momentum_hits():
    print("\n--- Testing Momentum Hits (Optimized) ---")
    start_time = time.time()
    try:
        data = ScreenerService.get_screener_data()
        elapsed = time.time() - start_time
        print(f"Fetch completed in {elapsed:.2f}s")
        print(f"Hits found: {len(data)}")
        for hit in data[:5]:
            print(f"  {hit['symbol']}: {hit['change']}% | VolRatio: {hit['volRatio']} | Sector: {hit['sector']}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR in Momentum Hits: {e}")

if __name__ == "__main__":
    test_sector_rotation()
    test_momentum_hits()
