import requests
import json

def test_search(query):
    print(f"\n--- Searching for '{query}' ---")
    try:
        response = requests.get(f"http://localhost:8000/api/v1/search?q={query}")
        if response.status_code == 200:
            results = response.json()
            print(f"Found {len(results)} results.")
            for item in results[:3]:
                print(f" - {item.get('symbol')} ({item.get('shortname')}) [{item.get('exchange')}]")
        else:
            print(f"Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_search("TATA")
    test_search("RELIANCE")
    test_search("AAPL")
