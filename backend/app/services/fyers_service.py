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
    DATA_URL = "https://api-t1.fyers.in/data" 
    # Fallback endpoint for token exchange (api-t1 is often the required endpoint for V3)
    AUTH_FALLBACK_URL = "https://api-t1.fyers.in/api/v3"
    
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
                print(f"[Fyers] Loaded token from {fyers_config.token_file} (Length: {len(cls._access_token) if cls._access_token else 0})", flush=True)
                return bool(cls._access_token)
            except Exception as e:
                print(f"[Fyers] Error loading token: {e}", flush=True)
        else:
            print(f"[Fyers] Token file NOT found at: {fyers_config.token_file}", flush=True)
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
        # Use provided redirect URL directly; fyers_config handles the defaults
        final_redirect = redirect_url
        if not final_redirect:
            # Last resort fallback if config is somehow empty
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
            
            # Derive Origin and Referer from the redirect_uri to be environment-agnostic
            try:
                from urllib.parse import urlparse
                parsed_uri = urlparse(resolved_redirect)
                origin = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
            except:
                origin = "https://stock-dashboard-9nvy.onrender.com"

            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Origin": origin,
                "Referer": f"{origin}/"
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
                # According to official Fyers V3 docs, only 3 fields are required.
                # Sending extra fields (appId, redirect_uri) causes 'invalid entry'.
                
                # Variant 1: Full appId hash (most common)
                p_min = {"grant_type": "authorization_code", "appIdHash": hash_full, "code": auth_code}
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/json", "label": "Proxy (V3-Minimal)", "payload": p_min})
                
                # Variant 2: Prefix-only hash (appId without -100 suffix)
                p_prefix = {"grant_type": "authorization_code", "appIdHash": hash_prefix, "code": auth_code}
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/json", "label": "Proxy (V3-PrefixHash)", "payload": p_prefix})

                # Variant 3: Form-encoded minimal (some older V3 clients)
                attempts.append({"url": f"{p_url}/api/v3/validate-authcode", "ct": "application/x-www-form-urlencoded", "label": "Proxy (V3-Form-Min)", "payload": p_min})
            else:
                cls._set_auth_debug("proxy_missing", "FYERS_AUTH_PROXY_URL not set.", "")

            # Production fallback (Direct - only if proxy missing or all proxy attempts consumed code)
            prod_base = cls.AUTH_FALLBACK_URL.rstrip('/')
            attempts.extend([
                {
                    "url": f"{prod_base}/validate-authcode", 
                    "ct": "application/json", 
                    "label": "Prod (V3-Full-JSON)", 
                    "payload": {
                        "grant_type": "authorization_code", 
                        "appIdHash": hash_full, 
                        "code": auth_code,
                        "appId": raw_app_id,
                        "redirect_uri": resolved_redirect
                    }
                },
                {
                    "url": f"{prod_base}/validate-authcode", 
                    "ct": "application/x-www-form-urlencoded", 
                    "label": "Prod (V3-Full-Form)", 
                    "payload": {
                        "grant_type": "authorization_code", 
                        "appIdHash": hash_full, 
                        "code": auth_code,
                        "appId": raw_app_id,
                        "redirect_uri": resolved_redirect
                    }
                },
            ])

            # Track errors from ALL variations for the last_auth_debug
            all_errors: List[str] = []
            code_is_consumed = False
            
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
                    "x-target-host": "api-t1.fyers.in" if "workers.dev" in url else None
                }
                # Remove None headers
                clean_headers = {k: v for k, v in clean_headers.items() if v is not None}

                try:
                    p_log = {k: (v[:5] + "..." if k in ["appIdHash", "code"] and isinstance(v, str) and len(v) > 10 else v) for k, v in current_payload.items()}
                    print(f"FYERS AUTH DEBUG [{lbl}]: Target={url} | CT={ct} | Payload={p_log}", flush=True)

                    if ct == "application/json":
                        # Use data=json.dumps to have full control over the payload string
                        res = requests.post(url, data=json.dumps(current_payload), headers=clean_headers, timeout=15)
                    else:
                        res = requests.post(url, data=current_payload, headers=clean_headers, timeout=15)
                    
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
                
                # Auth codes are SINGLE-USE. Stop retrying if the code has been consumed.
                # 'invalid entry' means the auth_code was accepted by the API but rejected
                # (wrong hash or already used). No point trying further variants.
                last_err = all_errors[-1].lower() if all_errors else ""
                if any(kw in last_err for kw in ["invalid entry", "invalid auth", "code has expired", "already used"]):
                    print(f"FYERS AUTH: Auth code consumed or invalid. Stopping retries.", flush=True)
                    code_is_consumed = True
                    break


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
            # Increase lookback to ensure technical signals have enough context
            if fyers_tf in ["1", "5", "10", "15"]:
                days = 60 # 60 days for lower intraday
            elif fyers_tf in ["30", "60", "120", "240"]:
                days = 180 # 180 days for hourly
            else:
                days = 730 # 2 years for Daily and above
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
                headers["x-target-host"] = "api-t1.fyers.in"
                print(f"Fetching Fyers data via proxy: {url}")
            
            res = requests.get(url, params=params, headers=headers, timeout=timeout)
            if res.status_code == 401:
                cls._access_token = None  # Clear stale token
                return None, "Fyers Token Expired (401) — Please reconnect"
            
            if res.status_code == 403:
                return None, "Fyers Permission Error (403): Additional scope required (Quotes/Market Data)"

            response = res.json()
            if response.get("s") == "ok":
                df = pd.DataFrame(response.get("candles"), columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
                df.set_index("timestamp", inplace=True)
                return df, None
            err_msg = response.get("message", f"Fyers Data Error: {response}")
            
            # If the response explicitly mentions permission or token, clear it
            if "permission" in str(err_msg).lower() or "token" in str(err_msg).lower():
                 if "invalid" in str(err_msg).lower():
                     cls._access_token = None

            print(f"DEBUG: [Fyers] Data API response (HTTP {res.status_code}): {response}", flush=True)
            return None, err_msg

        except requests.exceptions.Timeout:
            return None, "Fyers request timed out"
        except Exception as e:
            return None, f"Exception fetching Fyers data: {str(e)}"

    @classmethod
    def update_symbol_master(cls, force=False):
        """
        Syncs symbol metadata from Fyers.
        Now uses proxy and increased robustness for unreliable environments.
        """
        # Ensure we have a persistent data directory
        data_dir = os.path.dirname(fyers_config.token_file)
        os.makedirs(data_dir, exist_ok=True)
        symbols_file = os.path.join(data_dir, "fyers_symbols.json")
        
        now = time.time()
        # 1. Use memory cache if available and not forced
        if not force and cls._symbols_cache:
            return True, f"Using memory cache ({len(cls._symbols_cache)} symbols)"

        # 2. Try loading from disk if not expired (86400s = 24h)
        if not force and os.path.exists(symbols_file):
            file_time = os.path.getmtime(symbols_file)
            if now - file_time < 86400:
                try:
                    with open(symbols_file, "r") as f:
                        cls._symbols_cache = json.load(f)
                    if cls._symbols_cache:
                        return True, f"Loaded {len(cls._symbols_cache)} symbols from disk"
                except Exception as e:
                    print(f"Error loading symbols from disk: {e}")

        # 3. Synchronize from Fyers (Sequential to avoid memory spikes on small servers)
        print("[Fyers] Starting symbol master synchronization...", flush=True)
        all_symbols = []
        p_url = fyers_config.auth_proxy_url.rstrip('/') if fyers_config.auth_proxy_url else None
        
        for key, url in cls.SYMBOL_MASTER_URLS.items():
            try:
                target_url = url
                headers = {}
                
                # Use proxy for public CSVs too if available (avoids IP blocks)
                if p_url:
                    # public.fyers.in doesn't need auth, but needs IP bypass
                    target_host = url.split('//')[1].split('/')[0]
                    target_url = f"{p_url}{url.replace('https://' + target_host, '')}"
                    headers = {"x-target-host": target_host}
                
                print(f"[Fyers] Fetching {key} master via {target_url[:50]}...", flush=True)
                res = requests.get(target_url, headers=headers, timeout=45)
                
                if res.status_code == 200:
                    lines = res.text.splitlines()
                    count = 0
                    for line in lines:
                        # Format is extremely specific (CSV)
                        # Ticker is usually column 10 (index 9), Name is 2, ShortName is 14
                        parts = line.split(',')
                        if len(parts) > 13:
                            ticker = parts[9].strip('"')
                            name = parts[1].strip('"')
                            short_name = parts[13].strip('"')
                            
                            # Determine exchange if not in ticker (e.g. "NSE:RELIANCE-EQ")
                            exch = ticker.split(':')[0] if ':' in ticker else key.split('_')[0]
                            all_symbols.append({"s": ticker, "n": name, "sn": short_name, "e": exch})
                            count += 1
                    print(f"[Fyers] Parsed {count} symbols from {key}", flush=True)
                else:
                    print(f"[Fyers] Failed to fetch {key}: Status {res.status_code}", flush=True)
            except Exception as e:
                print(f"[Fyers] Error fetching {key}: {e}", flush=True)
        
        if all_symbols:
            # Atomic update
            cls._symbols_cache = all_symbols
            cls._last_sync = now
            try:
                with open(symbols_file, "w") as f:
                    json.dump(all_symbols, f)
                return True, f"Synced {len(all_symbols)} symbols"
            except Exception as e:
                print(f"Error saving symbols to disk: {e}")
                return True, f"Synced {len(all_symbols)} (Memory only)"
                
        return False, "Failed to sync any symbol master files"

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
