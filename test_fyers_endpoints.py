import requests

url1 = "https://api.fyers.in/data/history"
url2 = "https://api-t1.fyers.in/data/history"
res1 = requests.get(url1)
print(f"URL1 returns: {res1.status_code} {res1.text}")
res2 = requests.get(url2)
print(f"URL2 returns: {res2.status_code} {res2.text}")
