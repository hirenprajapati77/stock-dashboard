import requests
import json

endpoints = [
    "/api/v1/momentum-hits?tf=1D",
    "/api/v1/sector-rotation?tf=Daily",
    "/api/v1/market-summary?tf=1D",
    "/api/v1/early-setups?tf=1D"
]

for ep in endpoints:
    try:
        r = requests.get(f"http://127.0.0.1:8000{ep}")
        print(f"Endpoint: {ep} - Status: {r.status_code}")
        data = r.json()
        if "data" in data:
            if isinstance(data["data"], list):
                print(f"  Data Length: {len(data['data'])}")
            elif isinstance(data["data"], dict):
                print(f"  Data Keys: {list(data['data'].keys())}")
        elif "momentumLeaders" in data: # Market summary shape
            print(f"  Summary Keys: {list(data.keys())}")
        else:
            print(f"  Keys: {list(data.keys())}")
    except Exception as e:
        print(f"  Error on {ep}: {e}")
