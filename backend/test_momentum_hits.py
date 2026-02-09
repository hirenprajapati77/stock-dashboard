import requests
import json

def test_momentum_hits():
    url = "http://127.0.0.1:8000/api/v1/momentum-hits"
    print(f"Testing {url}...")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {data['count']} hits.")
            if data['count'] > 0:
                print("First few hits:")
                for hit in data['data'][:5]:
                    print(f"- {hit['symbol']} ({hit['sector']}): Consecutive: {hit['consecutive']}, Change: {hit['change']}%, VolRatio: {hit['volRatio']}")
            else:
                print("No hits found (Market might be quiet or data delayed).")
        else:
            print(f"Failed with status code: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error connecting to server: {e}")

if __name__ == "__main__":
    test_momentum_hits()
