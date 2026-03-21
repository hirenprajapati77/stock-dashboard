import requests

def test_search(q):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if 'quotes' in data:
                print(f"Found {len(data['quotes'])} quotes.")
                for item in data['quotes']:
                    print(f" - {item.get('symbol')} ({item.get('shortname')})")
        else:
            print(r.text)
    except Exception as e:
        print(f"Error: {e}")

test_search("TCS")
test_search("RELIANCE")
