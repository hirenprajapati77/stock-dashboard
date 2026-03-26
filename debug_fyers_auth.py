import os
import requests
import hashlib
import json

def test_fyers_auth():
    app_id = os.environ.get("FYERS_APP_ID", "XAST342P8T-100")
    secret_id = os.environ.get("FYERS_SECRET_ID", "Q5G3DG890Y")
    auth_code = "DUMMY_CODE" 
    redirect_uri = "https://stock-dashboard-9nvy.onrender.com/api/v1/fyers/callback"

    hash_input = f"{app_id}:{secret_id}"
    app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    
    payload = {
        "grant_type": "authorization_code",
        "appIdHash": app_id_hash,
        "code": auth_code,
        "redirect_uri": redirect_uri
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    urls = [
        "https://api-t1.fyers.in/api/v3/validate-authcode",
        "https://api.fyers.in/api/v3/validate-authcode"
    ]
    
    best_error = None
    
    for url in urls:
        print(f"\nTesting URL: {url}")
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            resp = res.json()
            msg = resp.get("message", "No message")
            print(f"Status Code: {res.status_code}")
            print(f"Message: {msg}")
            
            if not best_error or "Invalid Request" in best_error:
                if "Invalid Request" not in msg:
                    best_error = msg
                    print(f"-> Set best_error to: {best_error}")
                elif not best_error:
                    best_error = msg
                    print(f"-> Set initial best_error to: {best_error}")
        except Exception as e:
            print(f"Error: {e}")
            
    print(f"\nFinal prioritized error: {best_error}")


if __name__ == "__main__":
    test_fyers_auth()
