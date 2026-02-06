import yfinance as yf
from datetime import datetime
import time

def check_freshness(symbol):
    print(f"\n--- Checking {symbol} ---")
    ticker = yf.Ticker(symbol)
    
    # Method 1: history
    start = time.time()
    df = ticker.history(period="1d", interval="1m")
    end = time.time()
    print(f"History (1m) fetch took {end-start:.2f}s")
    if not df.empty:
        last_candle_time = df.index[-1]
        last_close = df['Close'].iloc[-1]
        print(f"  Last Candle Time: {last_candle_time}")
        print(f"  Last Close: {last_close}")
    
    # Method 2: fast_info
    try:
        fast = ticker.fast_info
        print(f"  Fast Info Last Price: {fast['last_price']}")
        print(f"  Current Time: {datetime.now()}")
    except Exception as e:
        print(f"  Fast Info Failed: {e}")

if __name__ == "__main__":
    check_freshness("RELIANCE.NS")
    check_freshness("BTC-USD") # Always open, good for testing
