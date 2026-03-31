import requests
import json
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.market_data import MarketDataService

def test_proxy_stats(symbol="RELIANCE"):
    print(f"Testing proxy stats for {symbol}...")
    stats = MarketDataService.get_yahoo_stats_via_proxy(symbol)
    if stats:
        print("SUCCESS! Found stats:")
        print(f"Name: {stats['info'].get('longName')}")
        print(f"PE: {stats['info'].get('pe_ratio')}")
        print(f"Quarterly Financials (first 1 rows):")
        print(stats['quarterly_financials'].head(1))
    else:
        print("FAILED: No stats retrieved via proxy.")

if __name__ == "__main__":
    test_proxy_stats()
