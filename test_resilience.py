import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

def run_endpoint(path, params=None):
    url = f"{BASE_URL}{path}"
    print(f"Testing {url}...")
    try:
        r = requests.get(url, params=params)
        data = r.json()
        status = data.get("status")
        source = data.get("source")
        print(f"  Status: {status}")
        print(f"  Source: {source}")
        if "data" in data:
            if isinstance(data["data"], list):
                print(f"  Count: {len(data['data'])}")
            else:
                print(f"  Data keys: {list(data['data'].keys())}")
        return data
    except Exception as e:
        print(f"  FAILED: {e}")
        return None

if __name__ == "__main__":
    print("--- Intelligence Endpoints ---")
    run_endpoint("/momentum-hits")
    run_endpoint("/sector-rotation")
    run_endpoint("/market-summary")
    run_endpoint("/early-setups")
    
    print("\n--- Dashboard Endpoint ---")
    run_endpoint("/dashboard", params={"symbol": "RELIANCE", "tf": "1D"})
