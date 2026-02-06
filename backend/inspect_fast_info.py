import yfinance as yf
ticker = yf.Ticker("RELIANCE.NS")
print(f"Fast Info Keys: {list(ticker.fast_info.keys())}")
for k, v in ticker.fast_info.items():
    print(f"{k}: {v}")
