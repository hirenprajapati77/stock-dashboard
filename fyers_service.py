import os
import requests
import json
import time
import hashlib
from typing import Optional, Tuple, Dict, List

import pandas as pd
# Root version might need to import config differently or we can use environment directly
# But for consistency with the rest of the dashboard, we'll keep it similar.
try:
    from app.config import fyers_config
except ImportError:
    # Minimal config if called outside app context
    class MockConfig:
        app_id = os.environ.get("FYERS_APP_ID", "")
        secret_id = os.environ.get("FYERS_SECRET_ID", "")
        token_file = os.environ.get("FYERS_TOKEN_FILE", "fyers_token.txt")
        redirect_url = os.environ.get("FYERS_REDIRECT_URL", "")
        auth_proxy_url = os.environ.get("FYERS_AUTH_PROXY_URL", "").strip()
        def normalize_redirect_url(self, url): return url
    fyers_config = MockConfig()

class FyersService:
    _access_token = None
    _last_auth_debug = {}
    
    BASE_URL = "https://api-t1.fyers.in/api/v3"
    DATA_URL = "https://api.fyers.in/data" 
    AUTH_FALLBACK_URL = "https://api.fyers.in/api/v3"
    
    SYMBOL_MASTER_URLS = {
        "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
        "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
        "MCX_COM": "https://public.fyers.in/sym_details/MCX_COM.csv",
        "BSE_CM": "https://public.fyers.in/sym_details/BSE_CM.csv"
    }
    
    _symbols_cache = []
    _last_sync = 0.0

    @classmethod
    def load_token(cls):
        if os.path.exists(fyers_config.token_file):
            try:
                with open(fyers_config.token_file, "r") as f:
                    cls._access_token = f.read().strip()
                return bool(cls._access_token)
            except: pass
        return False

    @classmethod
    def save_token(cls, token):
        cls._access_token = token
        os.makedirs(os.path.dirname(fyers_config.token_file), exist_ok=True)
        with open(fyers_config.token_file, "w") as f: f.write(token)

    @classmethod
    def _normalize_redirect_uri(cls, uri: str) -> str:
        return fyers_config.normalize_redirect_url(uri)

    @classmethod
    def get_login_url(cls, redirect_url=None):
        resolved_redirect = cls._normalize_redirect_uri(redirect_url or fyers_config.redirect_url)
        params = {
            "client_id": fyers_config.app_id,
            "redirect_uri": resolved_redirect,
            "response_type": "code",
            "state": "fyers_auth"
        }
        query_string = "&".join([f"{k}={requests.utils.quote(v)}" for k, v in params.items()])
        return f"{cls.BASE_URL}/generate-authcode?{query_string}"

    @classmethod
    def generate_token(cls, auth_code: str, redirect_uri: Optional[str] = None) -> Tuple[bool, str]:
        if not auth_code: return False, "Missing auth code"
        resolved_redirect = cls._normalize_redirect_uri(redirect_uri or fyers_config.redirect_url)
        
        try:
            hash_input = f"{fyers_config.app_id}:{fyers_config.secret_id}"
            app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            payload = {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": auth_code, "redirect_uri": resolved_redirect}
            
            success = False
            response = {}
            raw_text = ""
            
            # Ordered attempts:
            attempts = []
            if fyers_config.auth_proxy_url:
                proxy_base = fyers_config.auth_proxy_url.rstrip('/')
                attempts.append({"url": f"{proxy_base}/api/v3/validate-authcode", "ct": "application/x-www-form-urlencoded", "label": "Proxy (Form)"})
                attempts.append({"url": f"{proxy_base}/api/v3/validate-authcode", "ct": "application/json",                   "label": "Proxy (JSON)"})
            
            attempts.extend([
                {"url": f"{cls.BASE_URL}/validate-authcode", "ct": "application/json", "label": "API-T1"},
                {"url": f"{cls.AUTH_FALLBACK_URL}/validate-authcode", "ct": "application/json", "label": "Fallback"}
            ])
            
            for attempt in attempts:
                try:
                    res = requests.post(attempt["url"], json=payload if attempt["ct"] == "application/json" else None, data=payload if attempt["ct"] != "application/json" else None, timeout=30)
                    raw_text = res.text
                    response = res.json()
                    if response.get("s") == "ok":
                        success = True; break
                except: pass
            
            if not success:
                # Final try without redirect
                payload.pop("redirect_uri", None)
                for url_base in [cls.BASE_URL, cls.AUTH_FALLBACK_URL]:
                    try:
                        res = requests.post(f"{url_base}/validate-authcode", json=payload, timeout=30)
                        if res.json().get("s") == "ok":
                            response = res.json(); success = True; break
                    except: pass

            if success:
                token = response.get("access_token") or (response.get("data") or {}).get("access_token")
                if token: cls.save_token(token); return True, "Login successful"
            
            return False, response.get("message", "Exchange failed")
        except Exception as e: return False, str(e)

    @classmethod
    def get_ohlcv(cls, symbol, timeframe, range_from=None, range_to=None, timeout=10):
        if not cls._access_token: cls.load_token()
        if not cls._access_token: return None, "No token"
        
        fyers_symbol = symbol if ":" in symbol else f"NSE:{symbol}-EQ"
        headers = {"Authorization": f"{fyers_config.app_id}:{cls._access_token}"}
        params = {"symbol": fyers_symbol, "resolution": "D", "date_format": "1", "range_from": "2024-01-01", "range_to": "2024-12-31", "cont_flag": "1"}
        
        try:
            url = f"{cls.DATA_URL}/history"
            if fyers_config.auth_proxy_url:
                proxy_base = fyers_config.auth_proxy_url.rstrip('/')
                url = f"{proxy_base}/data/history"
                
            res = requests.get(url, params=params, headers=headers, timeout=timeout)
            return pd.DataFrame(res.json().get("candles")), None
        except Exception as e: return None, str(e)
