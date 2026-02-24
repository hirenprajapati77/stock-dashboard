import yfinance as yf
import pandas as pd
from datetime import datetime

def check_data_freshness():
    symbols = ["ITC.NS", "ADANIENSOL.NS", "^NSEI"]
    print(f"Checking data for: {symbols} at {datetime.now()}")
    
    # Simulate what ScreenerService does
    df = yf.download(
        tickers=" ".join(symbols),
        period="5d",
        interval="1d",
        progress=False,
        group_by="ticker",
        auto_adjust=False,
        threads=True
    )
    
    for sym in symbols:
        print(f"\n--- {sym} ---")
        try:
            data = df[sym] if len(symbols) > 1 else df
            if data.empty:
                print("No data returned.")
                continue
                
            last_row = data.iloc[-1]
            last_date = data.index[-1]
            
            print(f"Last Candle Date: {last_date}")
            print(f"Close: {last_row['Close']}")
            
            # Check fast_info directly for comparison
            ticker = yf.Ticker(sym)
            fast_price = ticker.fast_info.get('lastPrice')
            print(f"Real-Time fast_info Price: {fast_price}")
            
            diff = fast_price - last_row['Close']
            print(f"Difference (RealTime - BatchLast): {diff}")
            
        except Exception as e:
            print(f"Error checking {sym}: {e}")

if __name__ == "__main__":
    check_data_freshness()
