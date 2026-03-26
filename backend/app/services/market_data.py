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
    def get_ohlcv(symbol="RELIANCE", tf="1D", count=200, use_fast_info=True):
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
            # If symbol has a colon, it's already a Fyers-style symbol
            fyers_sym = symbol if ":" in symbol else f"NSE:{symbol.replace('.NS', '').replace('.BO', '')}-EQ"
            
            print(f"DEBUG: Trying Fyers for {fyers_sym} (Timeout: 3s)")
            fyers_df, fyers_err = FyersService.get_ohlcv(fyers_sym, tf, timeout=3)
            
            if fyers_df is not None and not fyers_df.empty:
                print(f"DEBUG: Successfully fetched {symbol} from Fyers")
                fyers_df = fyers_df.tail(count)
                MarketDataService._save_to_disk(symbol, tf, fyers_df)
                return fyers_df, "INR", None
            elif fyers_err == "Fyers request timed out":
                print(f"DEBUG: Fyers timed out for {symbol}, falling back to Yahoo")
            elif "not logged in" not in str(fyers_err).lower():
                print(f"DEBUG: Fyers fetch failed for {symbol}: {fyers_err}. Falling back to Yahoo.")
                
        except Exception as fe:
            print(f"DEBUG: Fyers integration error: {fe}. Falling back to Yahoo.")

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
