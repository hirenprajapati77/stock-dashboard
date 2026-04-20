import os, sys
sys.path.append(os.getcwd())
from app.services.market_data import MarketDataService
import pandas as pd

symbols = ["^NSEI", "^NSEBANK", "RELIANCE.NS"]
tf = "15m"
res = MarketDataService.get_ohlcv_batch(symbols, tf, count=5)

for sym, (df, curr, err, src) in res.items():
    print(f"Symbol: {sym} | Source: {src} | Rows: {len(df) if df is not None else 0} | Error: {err}")
