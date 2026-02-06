import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")
print(f"Basic Info: {ticker.basic_info.get('last_price')}")
print(f"Info Regular: {ticker.info.get('regularMarketPrice')}")
