import requests
import json

def test_trade_engine():
    base_url = "http://localhost:8000/api/v1/generate-trade"
    symbols = ["TCS", "RELIANCE", "NIFTY50"]
    
    for symbol in symbols:
        print(f"\n--- Testing Symbol: {symbol} ---")
        try:
            response = requests.get(f"{base_url}?symbol={symbol}")
            if response.status_code == 200:
                data = response.json()
                print("Recommendation:")
                print(data['recommendation'])
                print("\nStructured JSON:")
                print(json.dumps(data['decision'], indent=2))
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_trade_engine()
