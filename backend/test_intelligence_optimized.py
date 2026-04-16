import sys
from pathlib import Path
import time
import pandas as pd

# Add backend to path
curr_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(curr_dir))
sys.path.append(str(curr_dir / "backend"))

from app.services.market_data import MarketDataService

def test_batch_performance():
    symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "HUL", "AXISBANK", "KOTAKBANK",
        "LT", "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "BAJFINANCE", "ONGC", "JSWSTEEL", "ADANIENT",
        "COALINDIA", "TATASTEEL", "TATAMOTORS", "POWERGRID", "NTPC", "HINDALCO", "INDUSINDBK", "TECHM", "HCLTECH", "NESTLEIND",
        "DRREDDY", "CIPLA", "BAJAJFINSV", "HEROMOTOCO", "EICHERMOT", "BRITANNIA", "APOLLOHOSP", "DIVISLAB", "ADANIPORTS", "GRASIM",
        "SHRIRAMFIN", "TATACONSUM", "SBILIFE", "HDFCLIFE", "LTIM", "BAJAJ-AUTO", "ADANIPOWER", "ADANIGREEN", "SIEMENS", "HAVELLS"
    ]
    tf = "1D"
    
    print(f"--- Testing Batch Fetch for {len(symbols)} symbols ---")
    t0 = time.time()
    results = MarketDataService.get_ohlcv_batch(symbols, tf)
    t1 = time.time()
    
    print(f"Batch fetch took: {t1 - t0:.2f} seconds")
    print(f"Results returned: {len(results)}")
    
    for sym in symbols:
        res = results.get(sym)
        if res and res[0] is not None:
            df = res[0]
            source = res[3]
            print(f"  [OK] {sym}: {len(df)} rows, Source: {source}")
            # Verify columns
            assert 'close' in df.columns, f"Missing 'close' in {sym}"
            # Verify timezone (should be naive)
            tz = getattr(df.index, 'tz', None)
            assert tz is None, f"Index for {sym} still has timezone: {tz}"
        else:
            print(f"  [FAIL] {sym}: {res[2] if res else 'No result'}")

    # Test cache hit (should be near instant)
    print("\n--- Testing Cache Hit (Near Instant) ---")
    t0 = time.time()
    results_cache = MarketDataService.get_ohlcv_batch(symbols, tf)
    t1 = time.time()
    print(f"Cache fetch took: {t1 - t0:.4f} seconds")
    
    for sym in symbols:
        source = results_cache[sym][3]
        if results_cache[sym][0] is not None:
            assert source == "cache", f"Expected source 'cache', got '{source}' for {sym}"
        else:
            print(f"  [INFO] {sym} remains in error state (expected for invalid tickers)")

if __name__ == "__main__":
    test_batch_performance()
