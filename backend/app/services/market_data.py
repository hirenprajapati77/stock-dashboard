import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import time
from functools import lru_cache
from app.services.fyers_service import FyersService

import requests
import json as json_lib # Avoid conflict with possible local json var

class MarketDataService:
    # Removed custom session as it conflicts with newer yfinance/curl_cffi requirements on Render

    # Simple in-memory cache to mitigate Yahoo Finance rate limits
    _ohlcv_cache = {}
    CACHE_TTL = 300 # 5 minutes

    @staticmethod
    def _pick_fast_info_value(fast_info, *keys):
        for key in keys:
            value = fast_info.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def normalize_symbol(symbol):
        symbol = symbol.upper().strip().replace(" ", "")

        # 0. Keyword Mapping (Natural Language Support)
        KEYWORD_MAP = {
            "NIFTY50": "^NSEI",
            "NIFTY": "^NSEI",
            "NIFTYBANK": "^NSEBANK",
            "BANKNIFTY": "^NSEBANK",
            "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
            "MIDCAP": "^NSEMDCP50",
            "SENSEX": "^BSESN",
            "VIX": "^VIX",
            "INDIAVIX": "^VIX",
            "GOLD_IN": "GOLDBEES.NS",
            "SILVER_IN": "SILVERBEES.NS",
            "CRUDE_IN": "SYNTHETIC_CRUDE_INR",
            "MCX_STOCK": "MCX.NS",
            "GOLD": "GC=F",
            "SILVER": "SI=F",
            "CRUDE": "CL=F",
            "NIFTYIT": "^CNXIT",
            "OIL_INDIA": "OIL.NS",
            "NIFTYPHARMA": "^CNXPHARMA",
            "NIFTYAUTO": "^CNXAUTO",
            "NIFTYMETAL": "^CNXMETAL",
            "USDINR": "USDINR=X",
            "HUL": "HINDUNILVR.NS"
        }
        
        if symbol in KEYWORD_MAP:
            return KEYWORD_MAP[symbol]
        
        # Original input for logging
        original_symbol = symbol

        # Only append .NS if:
        # 1. No dots already present
        # 2. Not an index (doesn't start with ^)
        # 3. Purely alphanumeric (or hyphen if it doesn't have a colon)
        # 4. No colon (Fyers style)
        if "." not in symbol and ":" not in symbol and not symbol.startswith("^") and symbol.replace("-", "").isalnum():
            symbol = f"{symbol}.NS"
            
        print(f"DEBUG: Symbol Mapping: {original_symbol} -> {symbol}")
        return symbol

    @staticmethod
    def _get_cache_path(symbol, tf):
        safe_symbol = "".join(c for c in symbol if c.isalnum() or c in ('^', '.'))
        return Path(__file__).parent.parent / "data" / "ohlcv_cache" / f"{safe_symbol}_{tf}.csv"

    @staticmethod
    def _save_to_disk(symbol, tf, df):
        try:
            if df.empty: return
            path = MarketDataService._get_cache_path(symbol, tf)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Use CSV for maximum compatibility and zero dependencies
            df.to_csv(path, index=True)
        except Exception as e:
            print(f"DEBUG: Failed to save {symbol} to disk: {e}")

    @staticmethod
    def _fetch_via_proxy(url, max_retries=2, timeout=15):
        """Fetches a URL via the Cloudflare Worker proxy with retries."""
        try:
            from app.config import fyers_config
            p_url = fyers_config.auth_proxy_url
            if not p_url: 
                return None
            
            p_url = p_url.rstrip('/')
            target_host = url.split('//')[1].split('/')[0]
            proxy_url = f"{p_url}{url.replace('https://' + target_host, '')}"
            
            headers = {
                "x-target-host": target_host,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            }

            for attempt in range(max_retries + 1):
                try:
                    res = requests.get(proxy_url, headers=headers, timeout=timeout)
                    if res.status_code == 200:
                        return res
                    elif res.status_code == 401:
                        print(f"DEBUG: Proxy Crumb Error (401) for {target_host} (Attempt {attempt+1})")
                    else:
                        print(f"DEBUG: Proxy Error {res.status_code} for {target_host}: {res.text[:100]}")
                except requests.exceptions.Timeout:
                    print(f"DEBUG: Proxy Timeout ({timeout}s) for {target_host} (Attempt {attempt+1})")
                except Exception as e:
                    print(f"DEBUG: Proxy Exception: {e} (Attempt {attempt+1})")
                
                if attempt < max_retries:
                    time.sleep(1) # Small delay before retry
        except Exception as e:
            print(f"DEBUG: Proxy Setup Exception: {e}")
        return None

    @staticmethod
    def _load_from_disk(symbol, tf):
        try:
            path = MarketDataService._get_cache_path(symbol, tf)
            if path.exists():
                df = pd.read_csv(path)
                if not df.empty and 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                elif not df.empty and df.columns[0] == 'Unnamed: 0':
                    # Sometimes pandas saves index as Unnamed: 0
                    df.rename(columns={'Unnamed: 0': 'timestamp'}, inplace=True)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                return df
        except Exception as e:
            print(f"DEBUG: Failed to load {symbol} from disk: {e}")
        return None

    @staticmethod
    def get_yahoo_stats_via_proxy(symbol):
        """
        Fetches comprehensive results from Yahoo Finance quoteSummary via proxy.
        Returns a dict containing 'info' and 'quarterly_financials' mimicking yfinance structures.
        """
        symbol = MarketDataService.normalize_symbol(symbol)
        modules = "defaultKeyStatistics,financialData,assetProfile,incomeStatementHistoryQuarterly,balanceSheetHistoryQuarterly"
        
        # Attempt query2 first (often bypasses crumb requirement)
        url_q2 = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules={modules}"
        res = MarketDataService._fetch_via_proxy(url_q2)
        
        if not res:
            # Fallback to query1 if query2 fails completely or times out
            url_q1 = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules={modules}"
            res = MarketDataService._fetch_via_proxy(url_q1)

        if not res:
            return None
            
        try:
            data = res.json()
            result = data.get('quoteSummary', {}).get('result', [{}])[0]
            if not result: 
                print(f"DEBUG: No quoteSummary.result found for {symbol}")
                return None
            
            # 1. Build 'info' equivalent
            fin = result.get('financialData', {})
            stats = result.get('defaultKeyStatistics', {})
            profile = result.get('assetProfile', {})
            
            if not fin:
                print(f"DEBUG: Missing financialData for {symbol}")
            if not stats:
                print(f"DEBUG: Missing defaultKeyStatistics for {symbol}")
            
            print(f"DEBUG: Data segments for {symbol}: fin={len(fin)}, stats={len(stats)}, profile={len(profile)}")
            
            def get_yval(d, key):
                return d.get(key, {}).get('raw')

            info = {
                'longName': symbol, 
                'currentPrice': get_yval(fin, 'currentPrice') or 0,
                'debtToEquity': get_yval(fin, 'debtToEquity'),
                'pegRatio': get_yval(stats, 'pegRatio'),
                'revenueQuarterlyGrowth': get_yval(fin, 'revenueGrowth'),
                'marketCap': get_yval(stats, 'marketCap'),
                'trailingPE': get_yval(stats, 'trailingPE'),
                'forwardPE': get_yval(stats, 'forwardPE'),
                'bookValue': get_yval(stats, 'bookValue'),
                'priceToBook': get_yval(stats, 'priceToBook'),
                'dividendYield': get_yval(stats, 'dividendYield'),
                'profitMargins': get_yval(fin, 'profitMargins'),
                'returnOnEquity': get_yval(fin, 'returnOnEquity'),
                'fiftyTwoWeekHigh': get_yval(stats, 'fiftyTwoWeekHigh'),
                'fiftyTwoWeekLow': get_yval(stats, 'fiftyTwoWeekLow'),
                'sector': profile.get('sector', '—'),
                'industry': profile.get('industry', '—'),
                'website': profile.get('website', ''),
                'returnOnCapitalEmployed': None 
            }
            
            # 2. Build 'quarterly_financials' equivalent (DataFrame-like dict)
            # We need: Total Revenue, Net Income, Basic EPS
            income_history = result.get('incomeStatementHistoryQuarterly', {}).get('incomeStatementHistory', [])
            print(f"DEBUG: Income History for {symbol}: {len(income_history)} quarters")
            
            q_data = {
                'Total Revenue': {},
                'Net Income': {},
                'Basic EPS': {},
                'Diluted EPS': {}
            }
            
            for i, entry in enumerate(income_history):
                # Try multiple date formats
                date_obj = entry.get('endDate', {})
                date = date_obj.get('fmt') or str(date_obj.get('raw', f'Q{i}'))
                
                q_data['Total Revenue'][date] = entry.get('totalRevenue', {}).get('raw', 0)
                q_data['Net Income'][date] = entry.get('netIncome', {}).get('raw', 0)
                
                # Yahoo Finance v10 keys for EPS
                basic_eps = entry.get('basicEps', {}).get('raw')
                if basic_eps is None:
                    # Fallback to manual calc if basicEps is missing
                    net_inc = entry.get('netIncomeApplicableToCommonShares', {}).get('raw', 0)
                    shares = entry.get('basicAverageShares', {}).get('raw')
                    basic_eps = (net_inc / shares) if shares and shares > 0 else 0
                
                q_data['Basic EPS'][date] = basic_eps
                q_data['Diluted EPS'][date] = entry.get('dilutedEps', {}).get('raw') or basic_eps

            # Convert to DataFrame to match yfinance output
            qf_df = pd.DataFrame(q_data).transpose()
            
            return {
                'info': info,
                'quarterly_financials': qf_df
            }
        except Exception as e:
            print(f"DEBUG: Proxy stats parsing failed for {symbol}: {e}")
            return None

    @staticmethod
    def get_ohlcv(symbol="NIFTY50", tf="1D", count=200, use_fast_info=True):
        """
        Fetches real OHLCV data using yfinance with in-memory and on-disk caching.
        Returns (df, currency, error_message)
        """
        symbol = MarketDataService.normalize_symbol(symbol)
        cache_key = f"{symbol}_{tf}_{count}_{use_fast_info}"
        
        # 1. Check Memory Cache
        now = time.time()
        if cache_key in MarketDataService._ohlcv_cache:
            entry = MarketDataService._ohlcv_cache[cache_key]
            if (now - entry['timestamp']) < MarketDataService.CACHE_TTL:
                return entry['df'].copy(), entry['currency'], None
            
        # Map TF to yfinance interval
        interval_map = {
            "5m": "5m",
            "10m": "5m",
            "15m": "15m",
            "30m": "30m",
            "45m": "15m",
            "1H": "60m",
            "2H": "60m",
            "3H": "60m",
            "4H": "60m",
            "1D": "1d",
            "1W": "1wk",
            "1M": "1mo",
            "75m": "15m"
        }
        interval = interval_map.get(tf, "1d")
        
        period = "1y"
        if tf == "5m": period = "7d"
        elif tf == "10m": period = "7d"
        elif tf == "15m": period = "30d"
        elif tf in ["30m", "45m", "75m"]: period = "60d"
        elif tf in ["1H", "2H", "3H", "4H"]: period = "180d"
        elif tf == "1D": period = "1y" 
        elif tf == "1W": period = "2y"
        elif tf == "1M": period = "5y"
        
        # 1.5 Try Fyers first if logged in
        try:
            # Map Yahoo/internal symbols to Fyers-specific symbol formats
            fyers_sym = symbol
            if ":" not in symbol:
                # 1. Index Symbol Mapping
                INDEX_MAP = {
                    "^NSEI": "NSE:NIFTY50-INDEX",
                    "^NSEBANK": "NSE:NIFTYBANK-INDEX",
                    "^CNXIT": "NSE:NIFTYIT-INDEX",
                    "^CNXPHARMA": "NSE:NIFTYPHARMA-INDEX",
                    "^CNXFMCG": "NSE:NIFTYFMCG-INDEX",
                    "^CNXAUTO": "NSE:NIFTYAUTO-INDEX",
                    "^CNXENERGY": "NSE:NIFTYENERGY-INDEX",
                    "^CNXMETAL": "NSE:NIFTYMETAL-INDEX",
                    "^CNXREALTY": "NSE:NIFTYREALTY-INDEX",
                    "^CNXPSUBANK": "NSE:NIFTYPSUBANK-INDEX",
                    "^CNXMDCP50": "NSE:NIFTYMIDCAP50-INDEX",
                    "^BSESN": "BSE:SENSEX-INDEX"
                }
                
                if symbol in INDEX_MAP:
                    fyers_sym = INDEX_MAP[symbol]
                else:
                    # 2. Standard Stock Mapping
                    fyers_sym = f"NSE:{symbol.replace('.NS', '').replace('.BO', '')}-EQ"
            
            # Fast timeout - Fyers responds instantly if logged in, no point waiting 8s when offline
            print(f"DEBUG: [MarketData] Requesting {fyers_sym} from Fyers (Timeout: 2s)...", flush=True)
            fyers_df, fyers_err = FyersService.get_ohlcv(fyers_sym, tf, timeout=2)
            
            if fyers_df is not None and not fyers_df.empty:
                print(f"DEBUG: [MarketData] SUCCESS: Fetched {symbol} from Fyers. Rows: {len(fyers_df)}", flush=True)
                fyers_df = fyers_df.tail(count)
                MarketDataService._save_to_disk(symbol, tf, fyers_df)
                return fyers_df, "INR", None
            
            # Handle Fyers failures
            if fyers_err == "Fyers request timed out":
                print(f"WARNING: [MarketData] Fyers timed out for {symbol} after 8s. Falling back to Yahoo.", flush=True)
            elif "not logged in" in str(fyers_err).lower():
                print(f"DEBUG: [MarketData] Fyers not logged in. Using Yahoo fallback for {symbol}.", flush=True)
            else:
                print(f"DEBUG: [MarketData] FYERS FAILED for {fyers_sym}: {fyers_err}. Falling back to Yahoo...", flush=True)
                
        except Exception as fe:
            print(f"DEBUG: [MarketData] Fyers integration exception: {fe}. Falling back to Yahoo.", flush=True)

        try:
            # --- SYNTHETIC SYMBOL HANDLING ---
            if symbol == "SYNTHETIC_CRUDE_INR":
                base_ticker = yf.Ticker("CL=F")
                fx_ticker = yf.Ticker("USDINR=X")
                
                df = base_ticker.history(period=period, interval=interval)
                
                try:
                    fx_fast = fx_ticker.fast_info
                    fx_rate = MarketDataService._pick_fast_info_value(fx_fast, 'lastPrice', 'last_price', 'regularMarketPrice') or 83.1
                except Exception:
                    fx_rate = 83.1
                
                if not df.empty:
                    cols_to_mult = ['Open', 'High', 'Low', 'Close', 'open', 'high', 'low', 'close']
                    for col in cols_to_mult:
                        if col in df.columns:
                            df[col] = df[col] * fx_rate
                    
                    try:
                        cmp_fast = base_ticker.fast_info
                        cmp_usd = MarketDataService._pick_fast_info_value(cmp_fast, 'lastPrice', 'last_price', 'regularMarketPrice')
                        if cmp_usd:
                            for col_name in ['close', 'Close']:
                                if col_name in df.columns:
                                    df.iloc[-1, df.columns.get_loc(col_name)] = float(cmp_usd) * float(fx_rate)
                    except Exception:
                        pass
                    
                    # Disk persistence for synthetic
                    MarketDataService._save_to_disk(symbol, tf, df)
                    return df, "INR", None
            
            # Standard Fetch
            print(f"DEBUG: Yahoo Finance Fetching Symbol: {symbol}")
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            # 401 / Invalid Crumb Bypass via Proxy
            if df.empty:
                print(f"DEBUG: Yahoo Direct failed for {symbol}, trying Proxy...")
                y_range = period
                y_interval = interval
                
                # Try query2 first (often bypasses crumb), then query1
                res = None
                for q_host in ["query2.finance.yahoo.com", "query1.finance.yahoo.com"]:
                    y_url = f"https://{q_host}/v8/finance/chart/{symbol}?range={y_range}&interval={y_interval}"
                    res = MarketDataService._fetch_via_proxy(y_url, max_retries=1, timeout=10)
                    if res:
                        break
                if res:
                    data = res.json()
                    result = data.get('chart', {}).get('result', [{}])[0]
                    if result:
                        ts = result.get('timestamp', [])
                        indicators = result.get('indicators', {}).get('quote', [{}])[0]
                        o, h, l, c, v = indicators.get('open', []), indicators.get('high', []), indicators.get('low', []), indicators.get('close', []), indicators.get('volume', [])
                        
                        if ts and o:
                            df = pd.DataFrame({
                                'Open': o, 'High': h, 'Low': l, 'Close': c, 'Volume': v
                            }, index=pd.to_datetime(ts, unit='s'))
                            # Drop NaNs which Yahoo often sends for current partial bars
                            df = df.dropna()
                            print(f"DEBUG: Proxy Yahoo Success for {symbol}")
            
            if use_fast_info:
                try:
                    fast = ticker.fast_info
                    cmp = MarketDataService._pick_fast_info_value(
                        fast, 'lastPrice', 'last_price', 'regularMarketPrice'
                    )

                    if cmp:
                        cmp = float(cmp)
                        if not df.empty:
                            last_idx = df.index[-1]
                            col_close = 'Close' if 'Close' in df.columns else 'close'
                            col_high = 'High' if 'High' in df.columns else 'high'
                            col_low = 'Low' if 'Low' in df.columns else 'low'

                            is_today = last_idx.date() == pd.Timestamp.now().date()
                            if is_today:
                                df.at[last_idx, col_close] = cmp
                                df.at[last_idx, col_high] = max(df.at[last_idx, col_high], cmp)
                                df.at[last_idx, col_low] = min(df.at[last_idx, col_low], cmp)
                            else:
                                new_idx = pd.Timestamp.now().floor("min")
                                new_row = {
                                    col_close: cmp,
                                    col_high: cmp,
                                    col_low: cmp,
                                    'open': df.iloc[-1][col_close],
                                    'volume': 0
                                }
                                df.loc[new_idx] = new_row
                            df = df[~df.index.duplicated(keep="last")]
                except Exception:
                    pass
            
            if df.empty:
                if symbol.endswith(".NS"):
                    fallback_symbol = symbol.replace(".NS", ".BO")
                    ticker = yf.Ticker(fallback_symbol)
                    df = ticker.history(period=period, interval=interval)
            
            # Handle rate limit fallback before checking empty
            if df.empty:
                df_disk = MarketDataService._load_from_disk(symbol, tf)
                if df_disk is not None and not df_disk.empty:
                    print(f"DEBUG: Returning persistent cache for {symbol}")
                    return df_disk.tail(count), "INR", None # Pretend it's success to unblock UI
                
                return pd.DataFrame(), "INR", f"No data found for {symbol}. (Possible Yahoo Finance Rate Limit - please wait 2-5 minutes)"
                
            df.columns = [c.lower() for c in df.columns]

            resample_map = {
                "10m": "10min",
                "45m": "45min", 
                "75m": "75min", 
                "2H": "120min", 
                "3H": "180min", 
                "4H": "240min"
            }
            if tf in resample_map:
                resample_logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
                offset = '15min' if tf == "75m" else '0min'
                df = df.resample(resample_map[tf], offset=offset).agg(resample_logic).dropna()
            
            df = df.tail(count)
            is_inr = symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.startswith("^NSE") or symbol.startswith("^CNX") or symbol.startswith("NIFTY")
            currency = "INR" if is_inr else "USD"
            
            # 2. Update Memory Cache
            MarketDataService._ohlcv_cache[cache_key] = {
                'df': df.copy(),
                'currency': currency,
                'timestamp': time.time()
            }
            # 3. Save to Disk Persistence
            MarketDataService._save_to_disk(symbol, tf, df)
            
            return df, currency, None
            
        except Exception as e:
            err_msg = str(e)
            if "Too Many Requests" in err_msg or "Rate limited" in err_msg:
                df_disk = MarketDataService._load_from_disk(symbol, tf)
                if df_disk is not None and not df_disk.empty:
                    return df_disk.tail(count), "INR", None
                return pd.DataFrame(), "INR", "Yahoo Finance Rate Limit exceeded. Please wait 2-5 minutes."
            
            # General fallback for any exception
            df_disk = MarketDataService._load_from_disk(symbol, tf)
            if df_disk is not None and not df_disk.empty:
                return df_disk.tail(count), "INR", None
                
            return pd.DataFrame(), "INR", f"Data Error: {err_msg}"
