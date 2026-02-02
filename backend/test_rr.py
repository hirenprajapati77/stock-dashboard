import requests
import json

def test_rr(symbol):
    print(f"\n--- Testing R:R for {symbol} ---")
    try:
        response = requests.get("http://localhost:8000/api/v1/dashboard", params={"symbol": symbol, "tf": "1D"})
        if response.status_code == 200:
            data = response.json()
            rr = data.get('summary', {}).get('risk_reward')
            print(f"Risk Reward: {rr}")
            print(f"CMP: {data['meta']['cmp']}")
            print(f"SL: {data['summary']['stop_loss']}")
            print(f"Target: {data['summary']['nearest_resistance']}")
        else:
            print(f"Failed: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_rr("RELIANCE")
    test_rr("TCS.NS")
