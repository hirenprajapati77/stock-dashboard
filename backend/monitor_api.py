import requests
import time
from datetime import datetime

def monitor_api(symbol="BTC-USD", tf="1D", iterations=5):
    print(f"Monitoring {symbol} ({tf})...")
    url = f"http://localhost:8000/api/v1/dashboard?symbol={symbol}&tf={tf}"
    
    for i in range(iterations):
        now = datetime.now().strftime("%H:%M:%S")
        try:
            r = requests.get(url)
            data = r.json()
            cmp = data['meta']['cmp']
            ohlcv_last_close = data['ohlcv'][-1]['close']
            
            status = "CHANGED" if cmp != last_cmp and last_cmp is not None else "NEW" if last_cmp is None else "SAME"
            print(f"[{now}] Iter {i+1}: CMP={cmp}, Chart={ohlcv_last_close} - {status}")
            last_cmp = cmp
        except Exception as e:
            print(f"[{now}] Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    monitor_api()
