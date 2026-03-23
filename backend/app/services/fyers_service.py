import os
import requests
import json
import time
import hashlib
from typing import Optional, Tuple

import pandas as pd
from app.config import fyers_config

class FyersService:
    _access_token = None
    _last_auth_debug = {}
    BASE_URL = "https://api-t1.fyers.in/api/v3"
    DATA_URL = "https://api-t1.fyers.in/data" 
    
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
    def _normalize_redirect_uri(cls, uri: str) -> str:
        return fyers_config.normalize_redirect_url(uri)

    @classmethod
    def get_login_url(cls, redirect_url=None):
        resolved_redirect = cls._normalize_redirect_uri(redirect_url or fyers_config.redirect_url)
        return cls._build_auth_url(resolved_redirect)

    @classmethod
    def _build_auth_url(cls, redirect_url):
        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=fyers_config.app_id,
            redirect_uri=redirect_url,
            response_type="code",
            state="fyers_auth",
        )
        return session.generate_authcode()

    @classmethod
    def generate_token(cls, auth_code: str, redirect_uri: Optional[str] = None) -> Tuple[bool, str]:
        """Generates access token from authorization code using the Fyers SDK."""
        if not auth_code:
            return False, "Missing authorization code."
        
        resolved_redirect = cls._normalize_redirect_uri(redirect_uri or fyers_config.redirect_url)
        
        try:
            from fyers_apiv3 import fyersModel
            
            # Use SDK's SessionModel for token exchange
            session = fyersModel.SessionModel(
                client_id=fyers_config.app_id,
                secret_key=fyers_config.secret_id,
                redirect_uri=resolved_redirect,
                response_type="code",
                grant_type="authorization_code"
            )
            
            session.set_token(auth_code)
            response = session.generate_access_token()
            
            # Log exchange attempt for debugging
            cls._set_auth_debug("sdk", f"Token exchange attempted with {resolved_redirect}", str(response)[:300])
            
            if response.get("s") == "ok":
                token = response.get("access_token")
                if token:
                    try:
                        cls.save_token(token)
                        return True, "Login successful"
                    except OSError as e:
                        return False, f"Could not save token: {e}"
                return False, "Login successful but no token received."
            
            message = response.get("message", f"Fyers error: {response}")
            return False, cls._humanize_auth_error(message)
            
        except Exception as e:
            msg = f"Exception during token exchange: {str(e)}"
            cls._set_auth_debug("sdk_exception", msg, str(e))
            return False, cls._humanize_auth_error(msg)

    @staticmethod
    def _humanize_auth_error(message):
        text = str(message or "").strip()
        normalized = " ".join(text.split())

        if "HTTP 403" in normalized or " 403" in normalized:
            return (
                "FYERS rejected the token exchange (HTTP 403). "
                "Ensure FYERS_REDIRECT_URL matches EXACTLY in your Render settings AND Fyers API dashboard. "
                "Even a missing or extra trailing slash will cause this error."
            )
        return normalized or "FYERS authentication failed. Please try again."

    @classmethod
    def get_last_auth_debug(cls):
        return dict(cls._last_auth_debug)

    @classmethod
    def _set_auth_debug(cls, source, message, detail=None):
        cls._last_auth_debug = {
            "source": source,
            "message": str(message or ""),
            "detail": str(detail or "")[:300],
        }

    @classmethod
    def get_ohlcv(cls, symbol, timeframe, range_from=None, range_to=None):
        if not cls._access_token:
            if not cls.load_token():
                return None, "Fyers not logged in"

        # Map timeframe (Fyers uses: 1, 5, 10, 15, 30, 60, 120, 240, D, W, M)
        tf_map = {
            "1m": "1", "5m": "5", "10m": "10", "15m": "15", 
            "30m": "30", "60m": "60", "1H": "60", 
            "2H": "120", "4H": "240",
            "1D": "D", "1W": "W", "1M": "M"
        }
        fyers_tf = tf_map.get(timeframe, "D")

        # Default range if none provided (last 200 bars)
        if not range_from or not range_to:
            now = int(time.time())
            range_to = time.strftime("%Y-%m-%d", time.localtime(now))
            days = 300 if fyers_tf == "D" else 30
            range_from = time.strftime("%Y-%m-%d", time.localtime(now - (days * 86400)))

        # Handle symbol formatting
        if ":" not in symbol:
            # Default to NSE Equity if no exchange prefix
            fyers_symbol = f"NSE:{symbol}-EQ"
        else:
            fyers_symbol = symbol

        params = {
            "symbol": fyers_symbol,
            "resolution": fyers_tf,
            "date_format": "1",
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }

        # Header format in v3: <app_id>:<access_token>
        # Note: Bearer prefix is NOT used in v3 for these endpoints
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
    @classmethod
    def update_symbol_master(cls, force=False):
        """Downloads and caches symbol masters from Fyers."""
        symbols_file = os.path.join(os.path.dirname(fyers_config.token_file), "fyers_symbols.json")
        
        # Check if sync is needed (e.g., once a day)
        now = time.time()
        if not force and os.path.exists(symbols_file):
            file_time = os.path.getmtime(symbols_file)
            if now - file_time < 86400: # 24 hours
                if not cls._symbols_cache:
                    try:
                        with open(symbols_file, "r") as f:
                            cls._symbols_cache = json.load(f)
                        cls._last_sync = file_time
                    except: pass
                if cls._symbols_cache:
                    return True, "Loaded from cache"

        all_symbols = []
        for key, url in cls.SYMBOL_MASTER_URLS.items():
            try:
                print(f"Syncing Fyers master: {key}...")
                res = requests.get(url, timeout=30)
                if res.status_code == 200:
                    lines = res.text.splitlines()
                    for line in lines:
                        parts = line.split(',')
                        if len(parts) > 13:
                            ticker = parts[9]
                            name = parts[1]
                            short_name = parts[13]
                            exch = ticker.split(':')[0] if ':' in ticker else key.split('_')[0]
                            
                            all_symbols.append({
                                "s": ticker,
                                "n": name.strip('"'),
                                "sn": short_name.strip('"'),
                                "e": exch
                            })
            except Exception as e:
                print(f"Error syncing {key}: {e}")
        
        if all_symbols:
            cls._symbols_cache = all_symbols
            cls._last_sync = now
            try:
                with open(symbols_file, "w") as f:
                    json.dump(all_symbols, f)
            except: pass
            return True, f"Synced {len(all_symbols)} symbols"
        return False, "Failed to sync any symbols"

    @classmethod
    def search_symbols(cls, query):
        """Searches symbols by ticker, name or short name."""
        if not cls._symbols_cache:
            cls.update_symbol_master()
            
        query = query.upper()
        results = []
        
        # Priority 1: Exact Ticker match
        for s in cls._symbols_cache:
            if query == s['sn'] or query == s['s'].split(':')[-1].split('-')[0]:
                results.append(s)
                if len(results) >= 15: break
        
        # Priority 2: Starts with query
        if len(results) < 15:
            for s in cls._symbols_cache:
                if s not in results:
                    if s['sn'].startswith(query) or any(p.startswith(query) for p in s['n'].split()):
                        results.append(s)
                        if len(results) >= 15: break
                        
        # Priority 3: Contains query
        if len(results) < 15:
            for s in cls._symbols_cache:
                if s not in results:
                    if query in s['s'] or query in s['n']:
                        results.append(s)
                        if len(results) >= 15: break
                        
        # Format for frontend
        formatted = []
        for r in results:
            formatted.append({
                "symbol": r['s'],
                "shortname": f"{r['n']} ({r['e']})",
                "exchange": r['e']
            })
        return formatted
