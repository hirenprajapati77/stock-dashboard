import sys
import os
import pandas as pd
from pathlib import Path

# Add project root and backend to path
base_dir = Path(__file__).parent.absolute()
sys.path.append(str(base_dir))
sys.path.append(str(base_dir / "backend"))

from app.services.market_data import MarketDataService

def test_fetch_symbols(symbols):
    print(f"--- Testing Fundamental Proxy Fetch (Query2/Query1 Fallback) ---")
    for sym in symbols:
        print(f"\n[+] Processing: {sym}")
        try:
            # We are testing the proxy path directly
            # This requires RENDER=1 or similar to trigger proxy use in stats logic
            os.environ["RENDER"] = "1"
            
            stats = MarketDataService.get_yahoo_stats_via_proxy(sym)
            
            if stats:
                print(f"    SUCCESS: Data retrieved for {sym}")
                info = stats.get('info', {})
                qf = stats.get('quarterly_financials')
                
                print(f"    Price: {info.get('currentPrice')}")
                print(f"    Market Cap: {info.get('marketCap')}")
                print(f"    Quarters: {len(qf.columns) if qf is not None else 0}")
                
                if qf is not None and not qf.empty:
                    print(f"    Sample Row (Total Revenue): {qf.loc['Total Revenue'][0] if 'Total Revenue' in qf.index else 'N/A'}")
            else:
                print(f"    FAILED: No stats returned via proxy for {sym}")
                
        except Exception as e:
            print(f"    CRITICAL ERROR for {sym}: {e}")

if __name__ == "__main__":
    test_symbols = ["INDUSINDBK", "KOTAKBANK", "HCLTECH", "TCS", "INFY"]
    test_fetch_symbols(test_symbols)
