import pandas as pd
import yfinance as yf
from app.services.screener_service import ScreenerService
from app.services.market_data import MarketDataService

def test_full_screener():
    print("Running Full Momentum Screener Scan...")
    hits = ScreenerService.get_screener_data(timeframe="1D")
    print(f"Total Hits Found: {len(hits)}")
    if hits:
        print(f"Sample Hit: {hits[0]['symbol']} | Vol Ratio: {hits[0]['volRatio']} | Sector: {hits[0]['sector']}")
    else:
        print("WARNING: Zero hits found. Checking why...")

if __name__ == "__main__":
    test_full_screener()
