import requests
import json

try:
    response = requests.get("http://localhost:8000/api/v1/dashboard", params={"symbol": "RELIANCE", "tf": "1D"})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2))
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
