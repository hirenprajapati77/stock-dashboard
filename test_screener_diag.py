import requests
import json

def diagnostic():
    try:
        # We need the admin token usually, but internal calls might work or I can use the local IP
        # Actually, let's just try to call the service directly via a python script
        import sys
        sys.path.append('backend')
        from app.services.screener_service import ScreenerService
        from app.services.market_data import MarketDataService
        
        # Try to get data
        hits = ScreenerService.get_screener_data(timeframe="1D", force=True)
        print(f"Total Hits Found: {len(hits)}")
        
        if hits:
            for h in hits[:3]:
                print(f"Symbol: {h['symbol']}, Sector: {h['sectorState']}, Confidence: {h['grade']}, Score: {h['technical'].get('qualityScore')}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnostic()
