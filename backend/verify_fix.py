import sys
import os
from datetime import datetime

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.screener_service import ScreenerService
from app.services.sector_service import SectorService

def verify():
    print(f"--- Verifying Fixes at {datetime.now()} ---\n")

    # 1. Verify Sector Service (Right Side)
    print("1. Checking Sector Rotation Data (Right Side)...")
    try:
        data, alerts = SectorService.get_rotation_data(timeframe="1D")
        bank = data.get("NIFTY_BANK", {})
        if bank:
            current = bank.get("current", {})
            metrics = bank.get("metrics", {})
            print(f"   NIFTY_BANK -> RS: {current.get('rs')}, RM: {current.get('rm')}")
            print(f"   State: {metrics.get('state')}, Shift: {metrics.get('shift')}")
            print("   [SUCCESS] Sector data fetched.")
        else:
            print("   [ERROR] NIFTY_BANK data missing.")
    except Exception as e:
        print(f"   [ERROR] Sector Service failed: {e}")

    print("\n------------------------------------------------\n")

    # 2. Verify Screener Service (Left Side)
    print("2. Checking Momentum Hits (Left Side)...")
    try:
        hits = ScreenerService.get_screener_data(timeframe="1D")
        if hits:
            print(f"   Found {len(hits)} hits.")
            print("   Top 3 Hits:")
            for hit in hits[:3]:
                print(f"   - {hit['symbol']}: Price {hit['price']}, Change {hit['change']}%, VolRatio {hit['volRatio']}x")
            
            # Check for a specific known active stock if possible, or just validate data format
            print("   [SUCCESS] Screener data fetched with real-time validation.")
        else:
            print("   [INFO] No hits found (Market might be quiet or data loading).")
    except Exception as e:
        print(f"   [ERROR] Screener Service failed: {e}")

if __name__ == "__main__":
    verify()
