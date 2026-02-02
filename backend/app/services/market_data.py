import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from functools import lru_cache

class MarketDataService:
    @staticmethod
    @lru_cache(maxsize=32)
    def get_ohlcv(symbol="RELIANCE", tf="1D", count=200):
        """
        Fetches real OHLCV data using yfinance.
        Auto-appends .NS for NSE if no suffix is provided.
        """
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
            "INDIAVIX": "^VIX"
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
    @lru_cache(maxsize=32)
    def get_ohlcv(symbol="RELIANCE", tf="1D", count=200):
        """
        Fetches real OHLCV data using yfinance.
        """
        symbol = MarketDataService.normalize_symbol(symbol)
            
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
        if tf == "5m": period = "60d"
        elif tf == "15m": period = "60d"
        elif tf == "75m": period = "60d"
        elif tf in ["1H", "2H", "4H"]: period = "730d"
        elif tf == "1D": period = "1y" 
        elif tf == "1W": period = "2y"
        elif tf == "1M": period = "5y"
        
        try:
            # Fetch Data
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                # Try .BO if .NS failed (simple fallback logic)
                if symbol.endswith(".NS"):
                    fallback_symbol = symbol.replace(".NS", ".BO")
                    print(f"Data empty for {symbol}, trying {fallback_symbol}")
                    ticker = yf.Ticker(fallback_symbol)
                    df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"CRITICAL: No data returned from yfinance for {symbol} (Interval: {interval}, Period: {period})")
                return pd.DataFrame() # Return empty instead of dummy zero data
                
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
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            # Fallback to a tiny empty DF to prevent backend crash, or re-raise
            # For this dashboard, let's return a single dummy candle to avoid total UI crash
            return pd.DataFrame({
                'open': [0], 'high': [0], 'low': [0], 'close': [0], 'volume': [0]
            }, index=[datetime.now()])
