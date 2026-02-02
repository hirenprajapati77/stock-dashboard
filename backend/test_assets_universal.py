import requests
import json

def test_asset(symbol, name):
    print(f"\n--- Testing {name} ({symbol}) ---")
    try:
        url = f"http://localhost:8000/api/v1/dashboard?symbol={symbol}&tf=1D"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "error":
                print(f"❌ Error: {data.get('message')}")
            else:
                meta = data.get("meta", {})
                print(f"✅ Success! Correct Symbol used: {meta.get('symbol')}")
                print(f"   CMP: {meta.get('cmp')}")
                print(f"   Levels Found: {len(data['levels']['primary']['supports']) + len(data['levels']['primary']['resistances'])}")
        else:
            print(f"❌ HTTP Error: {response.status_code}")
    except Exception as e:
        print(f"❌ Library Error: {e}")

if __name__ == "__main__":
    assets = [
        # Indices
        ("^NSEI", "Nifty 50"),
        ("^NSEBANK", "Nifty Bank"),
        ("^BSESN", "Sensex"),
        ("^VIX", "India VIX"),
        
        # Commodities (International/MCX proxies via yfinance)
        ("GC=F", "Gold Futures"),
        ("SI=F", "Silver Futures"),
        ("CL=F", "Crude Oil"),
        ("HG=F", "Copper Futures"),
        
        # International
        ("AAPL", "Apple Inc."),
        ("BTC-USD", "Bitcoin"),
    ]
    
    for symbol, name in assets:
        test_asset(symbol, name)
