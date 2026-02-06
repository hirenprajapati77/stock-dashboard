import yfinance as yf
from app.services.market_data import MarketDataService
import pandas as pd
import time

def compare_real_time(symbol):
    print(f"\nComparing {symbol}...")
    norm = MarketDataService.normalize_symbol(symbol)
    ticker = yf.Ticker(norm)
    
    # 1. Fetch History
    df_hist = ticker.history(period="1d", interval="1m")
    hist_price = df_hist['Close'].iloc[-1] if not df_hist.empty else None
    
    # 2. Fetch via our service (which uses fast_info)
    df_serv = MarketDataService.get_ohlcv(norm, "1D")
    serv_price = df_serv['close'].iloc[-1] if not df_serv.empty else None
    
    # 3. Fetch fast_info directly
    fast_price = ticker.fast_info.get('lastPrice') or ticker.fast_info.get('last_price')
    
    print(f"  History Last Close: {hist_price}")
    print(f"  Fast Info Price:    {fast_price}")
    print(f"  Service Final Price:{serv_price}")
    
    # Use small epsilon for float comparison
    if serv_price and fast_price and abs(serv_price - fast_price) < 0.0001:
        print("  SUCCESS: Service is using real-time price!")
    else:
        print(f"  WARNING: Diff is {abs(serv_price - fast_price) if serv_price and fast_price else 'N/A'}")

if __name__ == "__main__":
    compare_real_time("RELIANCE")
    compare_real_time("BTC-USD")
