import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")
print("Keys:", ticker.fast_info.keys())
print("lastPrice:", ticker.fast_info.get('lastPrice'))
print("last_price:", ticker.fast_info.get('last_price'))
