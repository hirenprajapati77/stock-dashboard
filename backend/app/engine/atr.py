import pandas as pd
import numpy as np
from typing import Dict, Any

class ATREngine:
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculates the Average True Range (ATR) over a specified period (default: 14).
        Standard volatility measure.
        """
        if df is None or df.empty or len(df) < period:
            return pd.Series(dtype=float)
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate True Range (TR)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate ATR using Wilder's EMA smoothing method
        atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
        return atr.round(2)

    @staticmethod
    def evaluate_volatility(df: pd.DataFrame, atr_series: pd.Series) -> Dict[str, Any]:
        """
        Evaluates the current volatility regime of the stock.
        """
        if df is None or df.empty or atr_series is None or atr_series.empty:
            return {"volatility_state": "NORMAL", "atr_value": 0.0, "atr_pct": 0.0}
            
        cmp = float(df['close'].iloc[-1])
        atr_val = float(atr_series.iloc[-1])
        
        atr_pct = (atr_val / cmp) * 100.0
        
        # Calculate 20-period average of ATR to check if rising/falling
        avg_atr = atr_series.rolling(window=20).mean().iloc[-1]
        
        if atr_val > 1.3 * avg_atr:
            state = "HIGH"
        elif atr_val < 0.75 * avg_atr:
            state = "LOW"
        else:
            state = "NORMAL"
            
        return {
            "volatility_state": state,
            "atr_value": atr_val,
            "atr_pct": round(atr_pct, 2),
            "historical_mean": round(avg_atr, 2)
        }
