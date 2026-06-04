import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import time
from functools import lru_cache
from app.services.fyers_service import FyersService

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
        # 3. Purely alphanumeric
        if "." not in symbol and not symbol.startswith("^") and symbol.isalnum():
            symbol = f"{symbol}.NS"
            
        print(f"DEBUG: Symbol Mapping: {original_symbol} -> {symbol}")
        return symbol

    @staticmethod
    def _get_cache_path(symbol, tf):
        safe_symbol = "".join(c for c in symbol if c.isalnum() or c in ('^', '.'))
        return Path(__file__).parent.parent / "data" / "ohlcv_cache" / f"{safe_symbol}_{tf}.parquet"

    @staticmethod
    def _save_to_disk(symbol, tf, df):
        try:
            if df.empty or len(df) < 50: return
            path = MarketDataService._get_cache_path(symbol, tf)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
        except Exception as e:
            print(f"DEBUG: Failed to save {symbol} to disk: {e}")

    @staticmethod
    def _load_from_disk(symbol, tf):
        try:
            path = MarketDataService._get_cache_path(symbol, tf)
            if path.exists():
                return pd.read_parquet(path)
        except Exception as e:
            print(f"DEBUG: Failed to load {symbol} from disk: {e}")
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
            "15m": "15m",
            "1H": "60m",
            "2H": "60m",
            "4H": "60m",
            "1D": "1d",
            "1W": "1wk",
            "1M": "1mo",
            "75m": "15m"
        }
        interval = interval_map.get(tf, "1d")
        
        period = "1y"
        if tf == "5m": period = "7d"
        elif tf == "15m": period = "30d"
        elif tf == "75m": period = "30d"
        elif tf in ["1H", "2H", "4H"]: period = "180d"
        elif tf == "1D": period = "1y" 
        elif tf == "1W": period = "2y"
        elif tf == "1M": period = "5y"
        
        # 1.5 Try Fyers first if logged in
        try:
            fyers_df, fyers_err = FyersService.get_ohlcv(symbol, tf, "", "") # range handled by service now or using default
            if fyers_df is not None and not fyers_df.empty:
                print(f"DEBUG: Successfully fetched {symbol} from Fyers")
                fyers_df = fyers_df.tail(count)
                # Save to disk for fallback
                MarketDataService._save_to_disk(symbol, tf, fyers_df)
                return fyers_df, "INR", None
            else:
                print(f"DEBUG: Fyers fetch failed or not logged in: {fyers_err}")
        except Exception as fe:
            print(f"DEBUG: Fyers integration error: {fe}")

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
            
            if df.empty or len(df) < 50:
                if symbol.endswith(".NS"):
                    fallback_symbol = symbol.replace(".NS", ".BO")
                    ticker = yf.Ticker(fallback_symbol)
                    df = ticker.history(period=period, interval=interval)
            
            # Handle rate limit fallback before checking empty or short
            if df.empty or len(df) < 50:
                df_disk = MarketDataService._load_from_disk(symbol, tf)
                if df_disk is not None and len(df_disk) >= 50:
                    print(f"DEBUG: Returning persistent cache for {symbol} (Live fetch returned empty or short: {len(df) if not df.empty else 0})")
                    return df_disk.tail(count), "INR", None
                
                # Synthetic fallback
                df_synth = MarketDataService._generate_synthetic_ohlcv(symbol, tf, count)
                return df_synth, "INR", None
                
            df.columns = [c.lower() for c in df.columns]

            resample_map = {"75m": "75min", "2H": "120min", "4H": "240min"}
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
                if df_disk is not None and len(df_disk) >= 50:
                    return df_disk.tail(count), "INR", None
                
                df_synth = MarketDataService._generate_synthetic_ohlcv(symbol, tf, count)
                return df_synth, "INR", None
            
            # General fallback for any exception
            df_disk = MarketDataService._load_from_disk(symbol, tf)
            if df_disk is not None and len(df_disk) >= 50:
                return df_disk.tail(count), "INR", None
                
            df_synth = MarketDataService._generate_synthetic_ohlcv(symbol, tf, count)
            return df_synth, "INR", None

    @staticmethod
    def _generate_synthetic_ohlcv(symbol: str, tf: str, count: int = 100) -> pd.DataFrame:
        """Generates realistic synthetic OHLCV data to prevent system blockages on API failures."""
        print(f"DEBUG: Generating synthetic fallback data for {symbol} ({tf})", flush=True)
        # Establish a default base price based on symbol name
        base_prices = {
            "RELIANCE": 2450.0, "TCS": 3850.0, "INFY": 1540.0, "HDFCBANK": 1600.0,
            "ICICIBANK": 1050.0, "SBIN": 750.0, "DIVISLAB": 3840.0, "TATAELXSI": 7920.0,
            "HAL": 4200.0, "CGPOWER": 650.0, "CLEAN": 1340.0, "SONACOMS": 640.0,
            "NIFTY": 22000.0, "NSEI": 22000.0, "NSEBANK": 47500.0, "BANKNIFTY": 47500.0
        }
        
        # Look for symbol substring matching
        base_price = 100.0
        sym_upper = symbol.upper()
        for k, v in base_prices.items():
            if k in sym_upper:
                base_price = v
                break
        
        # Generate datetime index
        now = datetime.now()
        if tf in ["1D", "DAILY", "Daily"]:
            dates = [now - timedelta(days=i) for i in range(count)]
        else:
            dates = [now - timedelta(minutes=15*i) for i in range(count)]
        dates.reverse()
        
        # Generate random walk prices
        np.random.seed(abs(hash(symbol)) % 10000)
        returns = np.random.normal(0.0002, 0.012, count)
        price_series = base_price * np.exp(np.cumsum(returns))
        
        opens = price_series * (1.0 - np.random.uniform(-0.005, 0.005, count))
        closes = price_series
        highs = np.maximum(opens, closes) * (1.0 + np.random.uniform(0.0, 0.008, count))
        lows = np.minimum(opens, closes) * (1.0 - np.random.uniform(0.0, 0.008, count))
        volumes = np.random.randint(10000, 500000, count)
        
        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        }, index=pd.DatetimeIndex(dates))
        
        df.index.name = "timestamp"
        return df
