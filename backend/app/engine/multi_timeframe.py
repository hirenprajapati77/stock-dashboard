# backend/app/engine/multi_timeframe.py
import pandas as pd
from typing import Dict, Any

class MultiTimeframeEngine:
    @staticmethod
    def get_trend_bias(df: pd.DataFrame) -> int:
        """
        Returns trend direction:
        1 = Bullish (Price > EMA20 > EMA50)
        -1 = Bearish (Price < EMA20 < EMA50)
        0 = Neutral / Consolidation
        """
        if df is None or len(df) < 50:
            return 0
            
        # Standardize columns to capitalized
        df = df.copy()
        df.columns = [c.capitalize() for c in df.columns]

        close = float(df['Close'].iloc[-1])
        # Calculate Exponential Moving Averages
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        if close > ema20 > ema50:
            return 1
        elif close < ema20 < ema50:
            return -1
        return 0

    @staticmethod
    def evaluate_mtf_alignment(
        df_daily: pd.DataFrame,
        df_weekly: pd.DataFrame,
        df_monthly: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Enforces Golden Rule 16: Multi-Timeframe Alignment.
        Categorizes trend coherence:
        - 3/3 Bullish -> ELITE SETUP
        - 2/3 Bullish -> GOOD SETUP
        - 1/3 or less -> WATCHLIST only (Buy signals rejected)
        """
        d_bias = MultiTimeframeEngine.get_trend_bias(df_daily)
        w_bias = MultiTimeframeEngine.get_trend_bias(df_weekly)
        m_bias = MultiTimeframeEngine.get_trend_bias(df_monthly)
        
        # Calculate positive alignment
        bullish_count = sum([1 for b in [d_bias, w_bias, m_bias] if b == 1])
        
        if bullish_count == 3:
            status = "ELITE SETUP"
            alignment = "3/3 Bullish (Daily + Weekly + Monthly)"
            passed = True
        elif bullish_count == 2:
            status = "GOOD SETUP"
            alignment = "2/3 Bullish (Trend established)"
            passed = True
        else:
            status = "WATCHLIST"
            alignment = f"Weak alignment ({bullish_count}/3 Bullish). Breakout rejected."
            passed = False
            
        return {
            "status": status,
            "alignment": alignment,
            "bullish_count": bullish_count,
            "passed": passed
        }
