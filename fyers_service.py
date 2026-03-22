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
    def get_login_url(cls, redirect_url=None):
        resolved_redirect = redirect_url or fyers_config.redirect_url
        try:
            from fyers_apiv3 import fyersModel

            session = fyersModel.SessionModel(
                client_id=fyers_config.app_id,
                redirect_uri=resolved_redirect,
                response_type="code",
                state="fyers_auth",
                secret_key=fyers_config.secret_id,
                grant_type="authorization_code",
            )
            return session.generate_authcode()
        except Exception:
            import urllib.parse
            encoded_redirect = urllib.parse.quote(resolved_redirect, safe='')
            url = f"{cls.BASE_URL}/generate-authcode?client_id={fyers_config.app_id}&redirect_uri={encoded_redirect}&response_type=code&state=fyers_auth"
            return url

    @classmethod
    def generate_token(cls, auth_code):
        try:
            return cls._generate_token_with_sdk(auth_code)
        except Exception:
            return cls._generate_token_with_http(auth_code)

    @classmethod
    def _generate_token_with_sdk(cls, auth_code):
        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=fyers_config.app_id,
            redirect_uri=fyers_config.redirect_url,
            response_type="code",
            state="fyers_auth",
            secret_key=fyers_config.secret_id,
            grant_type="authorization_code",
        )
        session.set_token(auth_code)
        response = session.generate_token()

        if isinstance(response, dict) and response.get("access_token"):
            cls.save_token(response["access_token"])
            return True, "Login successful"

        message = response.get("message") if isinstance(response, dict) else str(response)
        return False, cls._humanize_auth_error(message)

    @classmethod
    def _generate_token_with_http(cls, auth_code):
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
            res = requests.post(
                url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            raw_body = (res.text or "").strip()

            if not raw_body:
                return False, cls._humanize_auth_error(
                    f"FYERS token exchange returned an empty response (HTTP {res.status_code}). "
                    "Please verify FYERS app credentials and callback URL settings."
                )

            try:
                response = res.json()
            except ValueError:
                preview = raw_body[:200]
                return False, cls._humanize_auth_error(
                    f"Unexpected FYERS token response (HTTP {res.status_code}): {preview}"
                )
            
            if response.get("s") == "ok":
                token = response.get("access_token")
                cls.save_token(token)
                return True, "Login successful"
            return False, response.get("message", f"Login failed: {response}")
        except Exception as e:
            return False, cls._humanize_auth_error(str(e))

    @staticmethod
    def _humanize_auth_error(message):
        text = str(message or "").strip()
        normalized = " ".join(text.split())

        if "HTTP 403" in normalized:
            return (
                "FYERS rejected the callback (HTTP 403). "
                "Verify that FYERS_REDIRECT_URL exactly matches the redirect URL configured in your FYERS app."
            )
        if "empty response" in normalized.lower():
            return (
                "FYERS did not return a token response. "
                "Please verify the FYERS app credentials and callback URL configuration."
            )
        return normalized or "FYERS authentication failed. Please try again."

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
