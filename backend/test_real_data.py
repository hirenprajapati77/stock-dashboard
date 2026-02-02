import requests
import json

symbols = ["RELIANCE", "TCS.NS", "500325.BO"]

for sym in symbols:
    print(f"\n--- Testing {sym} ---")
    try:
        response = requests.get("http://localhost:8000/api/v1/dashboard", params={"symbol": sym, "tf": "1D"})
        if response.status_code == 200:
            data = response.json()
            meta = data.get('meta', {})
            ohlcv = data.get('ohlcv', [])
            print(f"Success! Symbol: {meta.get('symbol')}")
            print(f"Price: {meta.get('cmp')}")
            print(f"Candles: {len(ohlcv)}")
            if ohlcv:
                print(f"Last Candle: {ohlcv[-1]}")
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")
