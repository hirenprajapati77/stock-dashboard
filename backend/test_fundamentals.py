from app.services.fundamentals import FundamentalService
from app.services.market_data import MarketDataService

def test_fundamentals():
    test_symbols = ["RELIANCE", "TCS", "^NSEI", "AAPL", "BTC-USD"]
    
    for sym in test_symbols:
        norm_sym = MarketDataService.normalize_symbol(sym)
        print(f"\n--- Testing Fundamentals for {sym} (Normalized: {norm_sym}) ---")
        data = FundamentalService.get_fundamentals(norm_sym)
        
        if data:
            print(f"✅ Success!")
            print(f"   Name: {data.get('long_name')}")
            print(f"   Sector: {data.get('sector')}")
            print(f"   Market Cap: {data.get('market_cap')}")
            print(f"   PE Ratio: {data.get('pe_ratio')}")
            print(f"   52W Range: {data.get('52w_low')} - {data.get('52w_high')}")
        else:
            print(f"❌ Failed to fetch fundamentals.")

if __name__ == "__main__":
    test_fundamentals()
