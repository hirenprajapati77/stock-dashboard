import requests
import json

def test_ai_insights(symbol, tf):
    print(f"\n--- AI Insights for {symbol} ({tf}) ---")
    try:
        url = f"http://localhost:8000/api/v2/ai-insights?symbol={symbol}&tf={tf}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(json.dumps(data, indent=2))
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ai_insights("RELIANCE", "1D")
    test_ai_insights("TATASTEEL.NS", "1W")
