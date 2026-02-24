import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import time
from functools import lru_cache

class MarketDataService:
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
            "USDINR": "USDINR=X"
        }
        
        if symbol in KEYWORD_MAP:
            return KEYWORD_MAP[symbol]
        
        # Original input for logging
        original_symbol = symbol

        # Only append .NS if:
        # 1. No dots already present
        # 2. Not an index (doesn't start with ^)
        # 3. Purely alphanumeric
        if "." not in symbol and not symbol.startswith("^") and symbol.isalnum():
            symbol = f"{symbol}.NS"
            
        print(f"DEBUG: Symbol Mapping: {original_symbol} -> {symbol}")
        return symbol

    @staticmethod
    def get_ohlcv(symbol="RELIANCE", tf="1D", count=200, use_fast_info=True):
        """
        Fetches real OHLCV data using yfinance with in-memory caching.
        """
        symbol = MarketDataService.normalize_symbol(symbol)
        cache_key = f"{symbol}_{tf}_{count}_{use_fast_info}"
        
        # 1. Check Cache
        now = time.time()
        if cache_key in MarketDataService._ohlcv_cache:
            entry = MarketDataService._ohlcv_cache[cache_key]
            if (now - entry['timestamp']) < MarketDataService.CACHE_TTL:
                # print(f"DEBUG: Cache Hit for {cache_key}")
                return entry['df'].copy(), entry['currency']
            
        # Map TF to yfinance interval
        interval_map = {
            "5m": "5m",
            "15m": "15m",
            "1H": "60m",
            "2H": "60m",
            "4H": "60m",
            "1D": "1d",
            "1W": "1wk",
            "1M": "1mo",
            "75m": "15m" # Fetch 15m and resample
        }
        interval = interval_map.get(tf, "1d")
        
        # Calculate period based on count (approximate)
        # We fetch a bit more to ensure we have enough candles
        period = "1y"
        if tf == "5m": period = "7d"
        elif tf == "15m": period = "30d"
        elif tf == "75m": period = "30d"
        elif tf in ["1H", "2H", "4H"]: period = "180d"
        elif tf == "1D": period = "1y" 
        elif tf == "1W": period = "2y"
        elif tf == "1M": period = "5y"
        
        try:
            # NOTE:
            # Newer versions of yfinance expect their own curl_cffi-based session.
            # Passing a custom requests.Session now triggers:
            # "Yahoo API requires curl_cffi session not <class 'requests.sessions.Session'>"
            # so we let yfinance manage the session internally.
            #
            # --- SYNTHETIC SYMBOL HANDLING ---
            # Indian Crude is a synthetic proxy: Global * USDINR
            if symbol == "SYNTHETIC_CRUDE_INR":
                base_ticker = yf.Ticker("CL=F")
                fx_ticker = yf.Ticker("USDINR=X")
                
                df = base_ticker.history(period=period, interval=interval)
                
                # Get FX Rate safely
                try:
                    fx_fast = fx_ticker.fast_info
                    fx_rate = MarketDataService._pick_fast_info_value(fx_fast, 'lastPrice', 'last_price', 'regularMarketPrice') or 83.1
                except Exception:
                    fx_rate = 83.1
                
                if not df.empty:
                    # Multi-index or single index check
                    cols_to_mult = ['Open', 'High', 'Low', 'Close', 'open', 'high', 'low', 'close']
                    for col in cols_to_mult:
                        if col in df.columns:
                            df[col] = df[col] * fx_rate
                    
                    # Ensure CMP is updated in the last candle
                    try:
                        cmp_fast = base_ticker.fast_info
                        cmp_usd = MarketDataService._pick_fast_info_value(cmp_fast, 'lastPrice', 'last_price', 'regularMarketPrice')
                        if cmp_usd:
                            # Use iloc safely
                            for col_name in ['close', 'Close']:
                                if col_name in df.columns:
                                    df.iloc[-1, df.columns.get_loc(col_name)] = cmp_usd * fx_rate
                    except Exception:
                        pass
                    
                    return df, "INR"
            
            # Standard Fetch (let yfinance manage its own session)
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            # --- REAL-TIME ENHANCEMENT ---
            # Yahoo Finance history() is often delayed by 15-60 mins for NSE.
            # We use fast_info.last_price to get the actual current market price.
            if use_fast_info:
                try:
                    fast = ticker.fast_info
                    cmp = MarketDataService._pick_fast_info_value(
                        fast, 'lastPrice', 'last_price', 'regularMarketPrice'
                    )

                    if cmp:
                        cmp = float(cmp)

                        if df.empty:
                            return pd.DataFrame(), "INR"

                        last_idx = df.index[-1]
                        col_close = 'Close' if 'Close' in df.columns else 'close'
                        col_high = 'High' if 'High' in df.columns else 'high'
                        col_low = 'Low' if 'Low' in df.columns else 'low'
                        col_vol = 'Volume' if 'Volume' in df.columns else 'volume'

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
                                col_vol: 0
                            }
                            df.loc[new_idx] = new_row

                        df = df[~df.index.duplicated(keep="last")]

                except Exception:
                    pass
            
            if df.empty:
                # Try .BO if .NS failed (simple fallback logic)
                if symbol.endswith(".NS"):
                    fallback_symbol = symbol.replace(".NS", ".BO")
                    print(f"Data empty for {symbol}, trying {fallback_symbol}")
                    ticker = yf.Ticker(fallback_symbol)
                    df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"CRITICAL: No data returned from yfinance for {symbol} (Interval: {interval}, Period: {period})")
                return pd.DataFrame(), "INR"
                
            # Formatting
            df.columns = [c.lower() for c in df.columns]

            # Special Logic: Resampling
            resample_map = {
                "75m": "75min",
                "2H": "120min",
                "4H": "240min"
            }
            
            if tf in resample_map:
                resample_logic = {
                    'open': 'first',
                    'high': 'max',
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }
                offset = '15min' if tf == "75m" else '0min'
                df = df.resample(resample_map[tf], offset=offset).agg(resample_logic).dropna()
            
            # Slice to requested count
            df = df.tail(count)
            
            # Heuristic for currency: If it ends in .NS or .BO, it's INR. If it starts with ^NSE or ^CNX, it's INR.
            is_inr = symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.startswith("^NSE") or symbol.startswith("^CNX") or symbol.startswith("NIFTY")
            currency = "INR" if is_inr else "USD"
            
            # (Optional) Try fast_info for currency if needed, but heuristic is safer
            
            # 2. Update Cache
            MarketDataService._ohlcv_cache[cache_key] = {
                'df': df.copy(),
                'currency': currency,
                'timestamp': time.time()
            }
            
            return df, currency
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame(), "INR"
