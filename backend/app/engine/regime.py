from __future__ import annotations

import pandas as pd


class MarketRegimeEngine:
    """Utility helpers for classifying market regime and confidence grades."""

    @staticmethod
    def detect_regime(df: pd.DataFrame) -> str:
        """
        Classify market regime using lightweight EMA slope/volatility heuristics.

        Returns one of:
        - STRONG_UPTREND
        - UPTREND
        - RANGE
        - WEAK_TREND
        - STRONG_DOWNTREND
        - UNKNOWN (insufficient data)
        """
        if df is None or df.empty:
            return "UNKNOWN"

        close_col = "close" if "close" in df.columns else "Close" if "Close" in df.columns else None
        if close_col is None:
            return "UNKNOWN"

        close = df[close_col].dropna()
        if len(close) < 30:
            return "UNKNOWN"

        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()

        ema_gap_pct = ((ema20.iloc[-1] - ema50.iloc[-1]) / ema50.iloc[-1]) * 100 if ema50.iloc[-1] else 0.0
        slope_lookback = min(10, len(ema20) - 1)
        ema20_slope = ema20.iloc[-1] - ema20.iloc[-1 - slope_lookback]

        recent_returns = close.pct_change().dropna().tail(20)
        vol = float(recent_returns.std() * 100) if not recent_returns.empty else 0.0

        if ema_gap_pct > 1.5 and ema20_slope > 0:
            return "STRONG_UPTREND"
        if ema_gap_pct > 0.5 and ema20_slope > 0:
            return "UPTREND"
        if ema_gap_pct < -1.5 and ema20_slope < 0:
            return "STRONG_DOWNTREND"
        if abs(ema_gap_pct) < 0.3 and vol < 1.2:
            return "RANGE"
        return "WEAK_TREND"

    @staticmethod
    def get_grade(confidence: float | int) -> str:
        """Map confidence score (0-100) to institutional grade."""
        score = max(0.0, min(float(confidence), 100.0))
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        return "D"
