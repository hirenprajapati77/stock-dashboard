import yfinance as yf
t = yf.Ticker("COALINDIA.NS")
info = t.info
print("Keys available:", list(info.keys()))
print("ROCE check:", info.get('returnOnCapitalEmployed'))
print("ROE check:", info.get('returnOnEquity'))
print("PE check:", info.get('trailingPE'))
