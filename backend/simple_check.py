import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")
print(f"Fast Info: {ticker.fast_info.get('last_price')}")
df = ticker.history(period="1d", interval="1m")
print(f"History Last: {df['Close'].iloc[-1] if not df.empty else 'EMPTY'}")
