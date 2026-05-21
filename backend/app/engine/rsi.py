import pandas as pd
import numpy as np
from typing import Dict, Any

class RSIEngine:
    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculates the standard 14-period Relative Strength Index (RSI).
        Uses Wilder's smoothing technique.
        """
        if df is None or df.empty or len(df) < period:
            return pd.Series(np.nan, index=df.index if df is not None else [])
            
        close = df['close']
        delta = close.diff()
        
        gain = (delta.where(delta > 0, 0)).copy()
        loss = (-delta.where(delta < 0, 0)).copy()
        
        # Wilder's smoothing (SMA of gain/loss initially, then exponential-like smoothing)
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        # We need to apply Wilder's smoothing logic to remaining bars
        # Wilders EMA formula: Wilder_EMA_today = (Wilder_EMA_yesterday * (n-1) + today_val) / n
        avg_gain_vals = avg_gain.values.copy()
        avg_loss_vals = avg_loss.values.copy()
        gain_vals = gain.values
        loss_vals = loss.values
        
        for i in range(period, len(df)):
            avg_gain_vals[i] = (avg_gain_vals[i - 1] * (period - 1) + gain_vals[i]) / period
            avg_loss_vals[i] = (avg_loss_vals[i - 1] * (period - 1) + loss_vals[i]) / period
            
        avg_gain = pd.Series(avg_gain_vals, index=df.index)
        avg_loss = pd.Series(avg_loss_vals, index=df.index)
        
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        # Fill any NaNs with 50.0 (neutral) to prevent issues
        rsi = rsi.fillna(50.0)
        
        return rsi.round(2)

    @staticmethod
    def evaluate_rsi_state(rsi_series: pd.Series) -> Dict[str, Any]:
        """
        Evaluates the current state of RSI (Overbought/Oversold/Neutral) and the trend direction.
        """
        if rsi_series is None or rsi_series.empty:
            return {"rsi": 50.0, "state": "NEUTRAL", "trend": "NEUTRAL", "bias": "NEUTRAL"}
            
        rsi_val = float(rsi_series.iloc[-1])
        prev_rsi_val = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else rsi_val
        
        # State logic
        if rsi_val >= 70.0:
            state = "OVERBOUGHT"
            bias = "BEARISH_DIVERGENCE_RISK"
        elif rsi_val <= 30.0:
            state = "OVERSOLD"
            bias = "BULLISH_REVERSAL_RISK"
        else:
            state = "NEUTRAL"
            if rsi_val >= 50.0:
                bias = "BULLISH"
            else:
                bias = "BEARISH"
                
        # Trend logic
        rsi_diff = rsi_val - prev_rsi_val
        if rsi_diff > 1.5:
            trend = "RISING"
        elif rsi_diff < -1.5:
            trend = "FALLING"
        else:
            trend = "FLAT"
            
        return {
            "rsi": round(rsi_val, 2),
            "state": state,
            "trend": trend,
            "bias": bias,
            "is_extreme": rsi_val >= 70.0 or rsi_val <= 30.0
        }
