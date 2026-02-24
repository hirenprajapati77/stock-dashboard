import requests
import json

base_url = "http://localhost:8003/api/v1/dashboard"
params = {
    "symbol": "RELIANCE",
    "tf": "1D",
    "strategy": "DEMAND_SUPPLY"
}

try:
    r = requests.get(base_url, params=params)
    print(f"Status: {r.status_code}")
    data = r.json()
    print(f"Meta Strategy: {data['meta']['strategy']}")
    print(f"Signal Reason: {data['summary']['trade_signal_reason']}")
    print(f"Strategy Data Keys: {list(data['strategy'].keys())}")
    if 'additionalMetrics' in data['strategy']:
        print(f"Additional Metrics: {data['strategy']['additionalMetrics']}")
except Exception as e:
    print(f"Error: {e}")
