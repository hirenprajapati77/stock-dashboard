import yfinance as yf
import time
from datetime import datetime

symbol = "RELIANCE.NS"
ticker = yf.Ticker(symbol)

print(f"Monitoring {symbol} for 10 seconds...")

for i in range(5):
    # Fetch history
    df = ticker.history(period="1d", interval="1m")
    hist_price = df['Close'].iloc[-1] if not df.empty else "N/A"
    
    # Fetch fast_info
    fast = ticker.fast_info
    fast_price = fast.get('lastPrice') or fast.get('last_price')
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Hist: {hist_price} | Fast: {fast_price}")
    time.sleep(2)
