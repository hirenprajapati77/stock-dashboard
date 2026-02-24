import requests

base_url = "http://localhost:8000/api/v1/dashboard"
params = {
    "symbol": "RELIANCE",
    "tf": "1D",
    "strategy": "SWING"
}

try:
    r = requests.get(base_url, params=params)
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print("Response Text (First 1000 chars):")
        print(r.text[:1000])
    else:
        print("Success! JSON returned.")
except Exception as e:
    print(f"Error: {e}")
