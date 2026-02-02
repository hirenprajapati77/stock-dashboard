import requests
import json

print("Testing Screener API Endpoint...")
try:
    response = requests.get("http://localhost:8000/api/v1/screener")
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"\nScreener Results:")
        print(f"Status: {data.get('status')}")
        print(f"Total Matches: {data.get('count')}")
        print(f"\nMatched Stocks:")
        for match in data.get('matches', [])[:10]:  # Show first 10
            print(f"  - {match.get('symbol'):15} {match.get('name')[:40]:40} CMP: ₹{match.get('cmp')}")
            print(f"    Sales Growth: {match.get('sales_growth')}, PEG: {match.get('peg')}, D/E: {match.get('debt_equity')}")
    else:
        print(response.text)
except Exception as e:
    print(f"Error: {e}")
