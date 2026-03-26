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
        # Use a hardcoded fallback if redirect_url is suspicious or empty
        final_redirect = redirect_url
        if not final_redirect or "onrender.com" not in final_redirect:
            final_redirect = "https://stock-dashboard-9nvy.onrender.com/api/v1/fyers/callback"
            
        params = {
            "client_id": fyers_config.app_id,
            "redirect_uri": final_redirect,
            "response_type": "code",
            "state": "fyers_auth"
        }
        # Use api-t1 for login page as it seems more stable for this account
        login_base = "https://api-t1.fyers.in/api/v3"
        from urllib.parse import urlencode
        return f"{login_base}/generate-authcode?{urlencode(params)}"

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
            
            # Fyers V3 can be extremely specific about the appIdHash salt and the field names.
            # Variant 1: Hash with full App ID (e.g. XAST...-100)
            hash_full = hashlib.sha256(f"{raw_app_id}:{fyers_config.secret_id}".encode()).hexdigest()
            # Variant 2: Hash with prefix only (e.g. XAST...)
            app_id_prefix = raw_app_id.split('-')[0]
            hash_prefix = hashlib.sha256(f"{app_id_prefix}:{fyers_config.secret_id}".encode()).hexdigest()

            # Define variations to try. We prioritize Proxy since Render is blocked.
            attempts = []
            p_url = fyers_config.auth_proxy_url.rstrip('/') if fyers_config.auth_proxy_url else None
            
            if p_url:
                # 1. Proxy (V3-Form) - The most standard V3 approach
                p_v3 = {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code, "appId": raw_app_id, "redirect_uri": resolved_redirect}
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/x-www-form-urlencoded", "label": "Proxy (V3-Form)", "payload": p_v3})
                
                # 2. Proxy (V3-Form-ClientID) - Some V3 docs use client_id instead of appId
                p_cli_f = {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code, "client_id": raw_app_id, "redirect_uri": resolved_redirect}
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/x-www-form-urlencoded", "label": "Proxy (V3-Form-CID)", "payload": p_cli_f})

                # 3. Proxy (V3-Form-ShortID) - Removing -100 suffix
                short_id = raw_app_id.split('-')[0] if '-' in raw_app_id else raw_app_id
                p_short = {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code, "appId": short_id, "redirect_uri": resolved_redirect}
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/x-www-form-urlencoded", "label": "Proxy (V3-Form-SID)", "payload": p_short})

                # 4. Proxy (V3-JSON) - Fallback to JSON
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/json", "label": "Proxy (V3-JSON)", "payload": p_v3})
            else:
                cls._set_auth_debug("proxy_missing", "FYERS_AUTH_PROXY_URL not set.", "")

            # Production & API-T1 fallback variants (Direct skip proxy if proxy fails)
            prod_base = cls.AUTH_FALLBACK_URL.rstrip('/')
            
            attempts.extend([
                {"url": f"{prod_base}/validate-authcode",  "ct": "application/json", "label": "Prod (JSON)", "payload": {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code, "appId": raw_app_id, "redirect_uri": resolved_redirect}},
                {"url": f"{prod_base}/validate-authcode",  "ct": "application/x-www-form-urlencoded", "label": "Prod (Form)", "payload": {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code, "appId": raw_app_id, "redirect_uri": resolved_redirect}},
            ])

            # Track errors from ALL variations for the last_auth_debug
            all_errors: List[str] = []
            
            for att in attempts:
                url = att["url"]
                ct = att["ct"]
                lbl = att["label"]
                current_payload = att["payload"]
                
                # HEADERS: High-emulation to match browser/postman exactly
                clean_headers = {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": ct,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                    "X-Fyers-AppId": raw_app_id,
                    "x-target-host": "api.fyers.in" if "workers.dev" in url else None
                }
                # Remove None headers
                clean_headers = {k: v for k, v in clean_headers.items() if v is not None}

                try:
                    p_log = {k: (v[:5] + "..." if k in ["appIdHash", "code"] and isinstance(v, str) and len(v) > 10 else v) for k, v in current_payload.items()}
                    print(f"FYERS AUTH DEBUG [{lbl}]: Target={url} | CT={ct} | Payload={p_log}", flush=True)

                    if ct == "application/json":
                        # Use data=json.dumps to have full control over the payload string
                        res = requests.post(url, data=json.dumps(current_payload), headers=clean_headers, timeout=12)
                    else:
                        res = requests.post(url, data=current_payload, headers=clean_headers, timeout=12)
                    
                    print(f"FYERS AUTH DEBUG [{lbl}]: URL={url} Status={res.status_code} Resp={res.text[:500]}", flush=True)
                    
                    if res.status_code == 200:
                        try:
                            resp_data = res.json()
                            if resp_data.get("s") == "ok":
                                token = resp_data.get("access_token")
                                if token:
                                    cls._access_token = token
                                    cls.save_token(token)
                                    cls._set_auth_debug("success", "Login successful!", f"Variant: {lbl}")
                                    return True, "Login Successful"
                            
                            all_errors.append(f"{lbl}: {resp_data.get('message', 'Unknown Error')}")
                        except:
                            all_errors.append(f"{lbl}: Invalid JSON response")
                    else:
                        # Non-200 responses
                        msg = res.text[:100]
                        try:
                            msg = res.json().get("message", msg)
                        except: pass
                        all_errors.append(f"{lbl}: {msg}")

                except Exception as e:
                    all_errors.append(f"{lbl} Exception: {str(e)}")
                    print(f"FYERS AUTH EXCEPTION [{lbl}]: {str(e)}", flush=True)
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
