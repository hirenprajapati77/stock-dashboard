from app.services.market_data import MarketDataService
import pandas as pd
import time

def test_tf(symbol, tf):
    print(f"Testing {symbol} {tf}...")
    start = time.time()
    try:
        df = MarketDataService.get_ohlcv(symbol, tf)
        end = time.time()
        print(f"  Success! {len(df)} candles found in {end-start:.2f}s")
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False

if __name__ == "__main__":
    for tf in ["1D", "1W", "1M"]:
        test_tf("RELIANCE", tf)
