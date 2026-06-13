import pandas as pd
import numpy as np
from typing import Dict, Any

class VWAPEngine:
    @staticmethod
    def calculate_vwap(df: pd.DataFrame, timeframe: str = "15m") -> pd.Series:
        """
        Calculates VWAP for a given stock dataframe.
        For intraday timeframes (5m, 15m, 1H), it resets VWAP daily at the session start.
        For daily timeframes (1D, 1W), it calculates a rolling 20-period VWAP since there is no intraday session.
        """
        if df is None or df.empty:
            return pd.Series(dtype=float)
            
        df = df.copy()
        
        # Calculate Typical Price
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3.0
        df['pv'] = df['typical_price'] * df['volume']
        
        is_intraday = timeframe in ["5m", "15m", "1H"] or ("m" in str(timeframe) or "h" in str(timeframe).lower())
        
        # Ensure DatetimeIndex for groupings
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass
                
        if is_intraday and isinstance(df.index, pd.DatetimeIndex):
            # Session-resetting VWAP (group by date)
            df['date'] = df.index.date
            cum_pv = df.groupby('date')['pv'].cumsum()
            cum_vol = df.groupby('date')['volume'].cumsum()
            vwap = cum_pv / cum_vol.replace(0, np.nan)
            vwap = vwap.ffill().bfill()
        else:
            # Daily/Weekly rolling VWAP (e.g., 20-day rolling window)
            window = min(20, len(df))
            rolling_pv = df['pv'].rolling(window=window).sum()
            rolling_vol = df['volume'].rolling(window=window).sum()
            vwap = rolling_pv / rolling_vol.replace(0, np.nan)
            # Fallback for initial bars
            fallback = df['pv'].cumsum() / df['volume'].cumsum().replace(0, np.nan)
            vwap = vwap.fillna(fallback).ffill().bfill()
            
        return vwap.round(2)

    @staticmethod
    def evaluate_vwap_state(df: pd.DataFrame, vwap_series: pd.Series) -> Dict[str, Any]:
        """
        Determines the current relationship between the price and VWAP.
        Also identifies crossover signals (Bullish/Bearish breakouts).
        """
        if df is None or df.empty or vwap_series is None or vwap_series.empty:
            return {"position": "NEUTRAL", "crossover": "NONE", "bias": "NEUTRAL"}
            
        cmp = float(df['close'].iloc[-1])
        vwap_val = float(vwap_series.iloc[-1])
        
        prev_cmp = float(df['close'].iloc[-2]) if len(df) > 1 else cmp
        prev_vwap = float(vwap_series.iloc[-2]) if len(vwap_series) > 1 else vwap_val
        
        # Position logic
        if cmp > vwap_val:
            position = "ABOVE_VWAP"
            bias = "BULLISH"
        elif cmp < vwap_val:
            position = "BELOW_VWAP"
            bias = "BEARISH"
        else:
            position = "AT_VWAP"
            bias = "NEUTRAL"
            
        # Crossover logic
        crossover = "NONE"
        if prev_cmp <= prev_vwap and cmp > vwap_val:
            crossover = "BULLISH_CROSSOVER"
        elif prev_cmp >= prev_vwap and cmp < vwap_val:
            crossover = "BEARISH_CROSSOVER"
            
        return {
            "position": position,
            "vwap_price": vwap_val,
            "crossover": crossover,
            "bias": bias,
            "distance_pct": round(((cmp - vwap_val) / vwap_val) * 100, 2)
        }
