import time
import requests
import statistics

BASE_URL = "http://localhost:8000/api/v1"
COOKIE = {"sr_pro_session": "authenticated_admin"}

def test_endpoint(name, path):
    print(f"\nTesting {name} ({path})...")
    timings = []
    
    for i in range(5):
        t0 = time.time()
        try:
            resp = requests.get(f"{BASE_URL}{path}", cookies=COOKIE)
            dur = (time.time() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                count = data.get("count", 0)
                status = data.get("status")
                print(f"  Req {i+1}: {dur:.2f}ms | Count: {count} | Status: {status}")
                timings.append(dur)
            elif resp.status_code == 202:
                print(f"  Req {i+1}: Warming up...")
            else:
                print(f"  Req {i+1}: Error {resp.status_code}")
        except Exception as e:
            print(f"  Req {i+1}: Failed - {e}")
        
    if timings:
        print(f"  Avg: {statistics.mean(timings):.2f}ms | Min: {min(timings):.2f}ms")

if __name__ == "__main__":
    print("Wait for server to be up...")
    test_endpoint("Intelligence", "/intelligence")
    test_endpoint("Momentum Hits", "/momentum-hits?tf=1D")
