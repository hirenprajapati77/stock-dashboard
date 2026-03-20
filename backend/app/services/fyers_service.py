import os
import requests
import json
import time
import hashlib
import pandas as pd
from app.config import fyers_config

class FyersService:
    _access_token = None
    # Fyers API v3 Endpoints
    BASE_URL = "https://api-t1.fyers.in/api/v3"
    DATA_URL = "https://api-t1.fyers.in/data" 

    @classmethod
    def load_token(cls):
        if os.path.exists(fyers_config.token_file):
            try:
                with open(fyers_config.token_file, "r") as f:
                    cls._access_token = f.read().strip()
                return bool(cls._access_token)
            except Exception as e:
                print(f"Error loading Fyers token: {e}")
        return False

    @classmethod
    def save_token(cls, token):
        cls._access_token = token
        os.makedirs(os.path.dirname(fyers_config.token_file), exist_ok=True)
        with open(fyers_config.token_file, "w") as f:
            f.write(token)

    @classmethod
    def get_login_url(cls):
        # API v3 Auth URL - Ensure redirect_uri is URL-encoded
        import urllib.parse
        encoded_redirect = urllib.parse.quote(fyers_config.redirect_url, safe='')
        url = f"{cls.BASE_URL}/generate-authcode?client_id={fyers_config.app_id}&redirect_uri={encoded_redirect}&response_type=code&state=fyers_auth"
        return url

    @classmethod
    def generate_token(cls, auth_code):
        # Exchange auth_code for access_token in v3
        # appIdHash = sha256(client_id:secret_key)
        hash_input = f"{fyers_config.app_id}:{fyers_config.secret_id}"
        app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code
        }
        
        try:
            url = f"{cls.BASE_URL}/validate-authcode"
            res = requests.post(url, json=payload, timeout=10)
            response = res.json()
            
            if response.get("s") == "ok":
                token = response.get("access_token")
                cls.save_token(token)
                return True, "Login successful"
            return False, response.get("message", f"Login failed: {response}")
        except Exception as e:
            return False, str(e)

    @classmethod
    def get_ohlcv(cls, symbol, timeframe, range_from=None, range_to=None):
        if not cls._access_token:
            if not cls.load_token():
                return None, "Fyers not logged in"

        # Map timeframe (Fyers uses: 1, 5, 10, 15, 30, 60, D, W, M)
        tf_map = {
            "1m": "1", "5m": "5", "15m": "15", "60m": "60",
            "1D": "D", "1W": "W", "1M": "M"
        }
        fyers_tf = tf_map.get(timeframe, "D")

        # Default range if none provided (last 200 bars)
        if not range_from or not range_to:
            now = int(time.time())
            range_to = time.strftime("%Y-%m-%d", time.localtime(now))
            days = 300 if fyers_tf == "D" else 30
            range_from = time.strftime("%Y-%m-%d", time.localtime(now - (days * 86400)))

        params = {
            "symbol": f"NSE:{symbol}-EQ",
            "resolution": fyers_tf,
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }

        # Header format in v3: Bearer <app_id>:<access_token>
        headers = {
            "Authorization": f"{fyers_config.app_id}:{cls._access_token}"
        }

        try:
            url = f"{cls.DATA_URL}/history"
            res = requests.get(url, params=params, headers=headers, timeout=10)
            response = res.json()
            
            if response.get("s") == "ok":
                df = pd.DataFrame(response.get("candles"), columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                df.set_index("timestamp", inplace=True)
                return df, None
            return None, response.get("message", f"Fyers Data Error: {response}")
        except Exception as e:
            return None, f"Exception fetching Fyers data: {str(e)}"
