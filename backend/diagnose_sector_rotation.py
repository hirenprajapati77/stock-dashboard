import requests
import json

def diagnose():
    url = "http://localhost:8000/api/v1/sector-rotation?tf=1D"
    print(f"Fetching from {url}...")
    try:
        r = requests.get(url)
        print(f"Status: {r.status_code}")
        data = r.json()
        print("Response structure:")
        print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()}, indent=2))
        
        if data.get('status') == 'success':
            sector_data = data.get('data', {})
            print(f"\nSectors found: {list(sector_data.keys())}")
            if not sector_data:
                print("WARNING: 'data' object is empty!")
            else:
                first_key = list(sector_data.keys())[0]
                print(f"First sector ({first_key}) structure:")
                print(json.dumps(sector_data[first_key], indent=2))
        else:
            print(f"API Error: {data.get('message')}")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    diagnose()
