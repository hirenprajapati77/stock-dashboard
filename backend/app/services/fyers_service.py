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
