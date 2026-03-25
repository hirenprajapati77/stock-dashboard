import os
import requests
import json
import time
import hashlib
from typing import Optional, Tuple, Dict, List

import pandas as pd
from app.config import fyers_config

class FyersService:
    _access_token = None
    _last_auth_debug = {}
    
    # Primary BASE_URL (api-t1) is preferred for login page in some accounts
    BASE_URL = "https://api-t1.fyers.in/api/v3"
    # Production data endpoint
    DATA_URL = "https://api.fyers.in/data" 
    # Fallback endpoint for token exchange
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
        """Builds the Fyers authorization URL manually to avoid SDK dependencies."""
        params = {
            "client_id": fyers_config.app_id,
            "redirect_uri": redirect_url,
            "response_type": "code",
            "state": "fyers_auth"
        }
        # Use api-t1 for login page as it seems more stable for this account
        login_base = "https://api-t1.fyers.in/api/v3"
        query_string = "&".join([f"{k}={requests.utils.quote(v)}" for k, v in params.items()])
        return f"{login_base}/generate-authcode?{query_string}"

    @classmethod
    def generate_token(cls, auth_code: str, redirect_uri: Optional[str] = None) -> Tuple[bool, str]:
        """Generates access token from authorization code using manual exchange with dual-endpoint fallback."""
        if not auth_code:
            return False, "Missing authorization code."
        
        resolved_redirect = cls._normalize_redirect_uri(redirect_uri or fyers_config.redirect_url)
        
        try:
            raw_app_id = fyers_config.app_id  # e.g. XAST342P8T-100
            hash_input = f"{raw_app_id}:{fyers_config.secret_id}"
            app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
            
            base_payload = {
                "grant_type": "authorization_code",
                "appId": raw_app_id,
                "appIdHash": app_id_hash,
                "code": auth_code,
                "redirect_uri": resolved_redirect,
            }
            
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Origin": "https://stock-dashboard-9nvy.onrender.com",
                "Referer": "https://stock-dashboard-9nvy.onrender.com/"
            }
            
            # Define variations to try: trailing slashes, official endpoints, different content types, and minimal payloads.
            # Fyers V3 is extremely sensitive to extra fields like 'appId' if 'appIdHash' is present.
            attempts = []
            
            # Diagnostic: check if proxy is even configured
            if fyers_config.auth_proxy_url:
                p_base = fyers_config.auth_proxy_url.rstrip('/')
                cls._set_auth_debug("proxy_detected", f"Proxy active: {p_base}", "")
                # Proxy attempts
                attempts.append({"url": f"{p_base}/api/v3/validate-authcode",  "ct": "application/x-www-form-urlencoded", "label": "Proxy (Form)"})
                attempts.append({"url": f"{p_base}/api/v3/validate-authcode",  "ct": "application/json",                   "label": "Proxy (JSON)"})
            else:
                cls._set_auth_debug("proxy_missing", "FYERS_AUTH_PROXY_URL not set in env.", "Render IPs will likely be blocked.")

            # Prepare alternate payloads
            minimal_payload = {
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash,
                "code": auth_code
            }
            
            # Prepare standard endpoints
            p_base = cls.AUTH_FALLBACK_URL.rstrip('/')
            t1_base = cls.BASE_URL.rstrip('/')

            attempts.extend([
                # Production Standard & Minimal
                {"url": f"{p_base}/validate-authcode",  "ct": "application/x-www-form-urlencoded", "label": "Prod (Form)"},
                {"url": f"{p_base}/validate-authcode/", "ct": "application/x-www-form-urlencoded", "label": "Prod (Form, Slash)"},
                {"url": f"{p_base}/validate-authcode",  "ct": "application/json",                  "label": "Prod (JSON)"},
                {"url": f"{p_base}/validate-authcode",  "ct": "application/json",                  "label": "Prod (Min)", "payload": minimal_payload},
                
                # API-T1 (Standard & Minimal)
                {"url": f"{t1_base}/validate-authcode",  "ct": "application/x-www-form-urlencoded", "label": "T1 (Form)"},
                {"url": f"{t1_base}/validate-authcode",  "ct": "application/json",                  "label": "T1 (Min)", "payload": minimal_payload},
                {"url": f"{t1_base}/validate-authcode/", "ct": "application/json",                  "label": "T1 (Slash)"},
            ])

            # Headers: Remove Origin/Referer for server-to-server calls.
            clean_headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            
            # Track errors from ALL variations for the last_auth_debug
            all_errors: List[str] = []
            
            for att in attempts:
                url = att["url"]
                ct = att["ct"]
                lbl = att["label"]
                # Use specific payload if provided, otherwise base_payload
                current_payload = att.get("payload", base_payload)
                
                cls._set_auth_debug(f"trying_{lbl}", f"Attempting {url}", f"CT: {ct}")

                resp = {} # Initialize as dict for safety
                try:
                    h = {**clean_headers, "Content-Type": ct}
                    if ct == "application/json":
                        res = requests.post(url, json=base_payload, headers=h, timeout=15)
                    else:
                        res = requests.post(url, data=base_payload, headers=h, timeout=15)
                    
                    try:
                        resp = res.json()
                        is_json = True
                    except:
                        is_json = False
                        resp = {"message": res.text[:200] if res.text else f"Status {res.status_code}"}
                    
                    if is_json and resp.get("s") == "ok":
                        token = resp.get("access_token") or (resp.get("data") or {}).get("access_token")
                        if token:
                            cls._access_token = token
                            cls.save_token(token)
                            cls._set_auth_debug("success", f"Token via {lbl}", f"URL: {url}")
                            return True, "Token generated successfully"
                    
                    err_msg = resp.get("message") or resp.get("error_description") or f"HTTP {getattr(res, 'status_code', 'unknown')}"
                    all_errors.append(f"{lbl}: {err_msg}")
                    
                except Exception as e:
                    all_errors.append(f"{lbl} Exception: {str(e)}")
                    continue

            # If ALL failed, provide the most descriptive summary
            # IMPORTANT: Prioritize Proxy errors in the message if they were tried and failed.
            proxy_errs = [e for e in all_errors if "Proxy" in e]
            if proxy_errs:
                best_summary = " | ".join(proxy_errs)
            else:
                # Last 3 attempts usually most relevant (Production fallbacks)
                best_summary = " | ".join(all_errors[-3:] if len(all_errors) >= 3 else all_errors)
            
            cls._set_auth_debug("failed_all", "All auth variants failed.", best_summary)
            human_msg = cls._humanize_auth_error(best_summary or "Unknown authentication failure")
            return False, human_msg


            
        except Exception as e:
            msg = f"Exception during manual token exchange: {str(e)}"
            cls._set_auth_debug("manual_exception", msg, str(e))
            return False, cls._humanize_auth_error(msg)

    @staticmethod
    def _humanize_auth_error(message):
        text = str(message or "").strip()
        normalized = " ".join(text.split())
        if "403" in normalized or "Invalid Request" in normalized:
            return f"{normalized}. TIP: Ensure your Redirect URI is EXACTLY matched in Fyers Dashboard (including http/https and trailing slashes)."
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
    def get_ohlcv(cls, symbol, timeframe, range_from=None, range_to=None, timeout=10):
        if not cls._access_token:
            if not cls.load_token():
                return None, "Fyers not logged in"

        tf_map = {
            "1m": "1", "5m": "5", "10m": "10", "15m": "15", 
            "30m": "30", "60m": "60", "1H": "60", 
            "2H": "120", "4H": "240",
            "1D": "D", "1W": "W", "1M": "M"
        }
        fyers_tf = tf_map.get(timeframe, "D")

        if not range_from or not range_to:
            now = int(time.time())
            range_to = time.strftime("%Y-%m-%d", time.localtime(now))
            days = 300 if fyers_tf == "D" else 30
            range_from = time.strftime("%Y-%m-%d", time.localtime(now - (days * 86400)))

        fyers_symbol = symbol if ":" in symbol else f"NSE:{symbol}-EQ"
        params = {
            "symbol": fyers_symbol, "resolution": fyers_tf, "date_format": "1",
            "range_from": range_from, "range_to": range_to, "cont_flag": "1"
        }
        headers = {"Authorization": f"{fyers_config.app_id}:{cls._access_token}"}

        try:
            url = f"{cls.DATA_URL}/history"
            
            # Use proxy if configured to bypass IP blocks
            if fyers_config.auth_proxy_url:
                # The proxy script prepends the path to https://api.fyers.in
                # Since DATA_URL is already https://api.fyers.in/data, we can just replace the base
                proxy_base = fyers_config.auth_proxy_url.rstrip('/')
                url = f"{proxy_base}/data/history"
                print(f"Fetching Fyers data via proxy: {url}")
            
            res = requests.get(url, params=params, headers=headers, timeout=timeout)
            if res.status_code == 401:
                return None, "Fyers Token Expired (401)"
            response = res.json()
            if response.get("s") == "ok":
                df = pd.DataFrame(response.get("candles"), columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                df.set_index("timestamp", inplace=True)
                return df, None
            return None, response.get("message", f"Fyers Data Error: {response}")
        except requests.exceptions.Timeout:
            return None, "Fyers request timed out"
        except Exception as e:
            return None, f"Exception fetching Fyers data: {str(e)}"

    @classmethod
    def update_symbol_master(cls, force=False):
        symbols_file = os.path.join(os.path.dirname(fyers_config.token_file), "fyers_symbols.json")
        now = time.time()
        if not force and os.path.exists(symbols_file):
            file_time = os.path.getmtime(symbols_file)
            if now - file_time < 86400:
                if not cls._symbols_cache:
                    try:
                        with open(symbols_file, "r") as f:
                            cls._symbols_cache = json.load(f)
                    except: pass
                if cls._symbols_cache: return True, "Loaded from cache"

        all_symbols = []
        for key, url in cls.SYMBOL_MASTER_URLS.items():
            try:
                # Use proxy if configured
                target_url = url
                if fyers_config.auth_proxy_url:
                    # Generic proxy handles api.fyers.in. Public symbols are on public.fyers.in.
                    # We might need to handle public.fyers.in too if it's blocked.
                    # For now, let's leave it as is or add public support to proxy if needed.
                    pass 
                res = requests.get(target_url, timeout=30)
                if res.status_code == 200:
                    lines = res.text.splitlines()
                    for line in lines:
                        parts = line.split(',')
                        if len(parts) > 13:
                            ticker, name, short_name = parts[9], parts[1], parts[13]
                            exch = ticker.split(':')[0] if ':' in ticker else key.split('_')[0]
                            all_symbols.append({"s": ticker, "n": name.strip('"'), "sn": short_name.strip('"'), "e": exch})
            except: pass
        
        if all_symbols:
            cls._symbols_cache = all_symbols
            cls._last_sync = now
            try:
                with open(symbols_file, "w") as f: json.dump(all_symbols, f)
            except: pass
            return True, f"Synced {len(all_symbols)} symbols"
        return False, "Failed to sync any symbols"

    @classmethod
    def search_symbols(cls, query):
        if not cls._symbols_cache: cls.update_symbol_master()
        query = query.upper()
        results = []
        for s in cls._symbols_cache:
            if query == s['sn'] or query == s['s'].split(':')[-1].split('-')[0]:
                results.append(s)
                if len(results) >= 15: break
        if len(results) < 15:
            for s in cls._symbols_cache:
                if s not in results:
                    if s['sn'].startswith(query) or any(p.startswith(query) for p in s['n'].split()):
                        results.append(s)
                        if len(results) >= 15: break
        formatted = [{"symbol": r['s'], "shortname": f"{r['n']} ({r['e']})", "exchange": r['e']} for r in results]
        return formatted
