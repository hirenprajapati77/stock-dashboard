import json
import urllib.request
import time

def test_endpoint():
    # Adding mock token logic or testing if it requires login
    urls = {
        "FIBONACCI": "http://127.0.0.1:8000/api/v1/dashboard?symbol=NIFTY50&tf=15m&strategy=FIBONACCI",
        "DEMAND_SUPPLY": "http://127.0.0.1:8000/api/v1/dashboard?symbol=NIFTY50&tf=15m&strategy=DEMAND_SUPPLY",
        "SWING": "http://127.0.0.1:8000/api/v1/dashboard?symbol=NIFTY50&tf=15m&strategy=SWING"
    }

    # Simulate fake access token for dependencies=[Depends(login_required)]
    token = "dev_token_if_needed"
    
    for strategy, url in urls.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                levels = data.get("levels", {})
                print(f"\n{strategy} LEVELS:")
                print(json.dumps(levels, indent=2))
        except Exception as e:
            print(f"Error fetching {strategy}: {e}")

if __name__ == "__main__":
    test_endpoint()
