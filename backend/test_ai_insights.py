import requests
import json

print("Testing AI Insights API Endpoint...")
try:
    response = requests.get("http://localhost:8000/api/v2/ai-insights", params={"symbol": "RELIANCE", "tf": "1D"})
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"\nAI Insights for RELIANCE:")
        print(json.dumps(data, indent=2))
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
