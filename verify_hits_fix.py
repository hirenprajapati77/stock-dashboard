
import requests
import json
import time

def test_hits():
    base_url = "http://localhost:8000/api/v1/momentum-hits"
    try:
        # We need the backend running for this. 
        # Actually, I can just import the class and test it directly to be sure.
        from backend.app.services.screener_service import ScreenerService
        print("Testing ScreenerService.get_screener_data() directly...")
        
        # We'll use a 1D timeframe
        data = ScreenerService.get_screener_data(timeframe="1D")
        
        print(f"Total hits returned: {len(data)}")
        if len(data) > 0:
            first_hit = data[0]
            print(f"First hit: {first_hit['symbol']} at {first_hit['price']}")
            print(f"Session info: {first_hit['session']}")
            print(f"Technical info: {first_hit['technical']}")
            
            # Check if session quality is BEST (which I set for CLOSED)
            if first_hit['session']['quality'] == "BEST":
                print("SUCCESS: Session quality is BEST (Post-market visible)")
            else:
                print(f"WARNING: Session quality is {first_hit['session']['quality']}")
        else:
            print("No hits found. This might be normal if scanning a limited set or if criteria not met.")

    except Exception as e:
        print(f"Error during test: {e}")

if __name__ == "__main__":
    test_hits()
