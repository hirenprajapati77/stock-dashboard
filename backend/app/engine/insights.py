import pandas as pd
import numpy as np

class InsightEngine:
    @staticmethod
    def get_ema_bias(df: pd.DataFrame, period: int = 50):
        if len(df) < period:
            return "Neutral"
        
        ema = df['close'].ewm(span=period, adjust=False).mean()
        curr_price = df['close'].iloc[-1]
        curr_ema = ema.iloc[-1]
        
        if curr_price > curr_ema * 1.002:
            return "Bullish"
        elif curr_price < curr_ema * 0.998:
            return "Caution"
        else:
            return "Neutral"

    @staticmethod
    def is_inside_candle(df: pd.DataFrame):
        if len(df) < 2:
            return False
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        return bool(curr['high'] < prev['high'] and curr['low'] > prev['low'])

    @staticmethod
    def detect_retest(df: pd.DataFrame, levels: list, threshold_pct: float = 0.5):
        """
        Detects if the current candle is retesting a level.
        """
        if not levels or len(df) < 1:
            return False
            
        curr_low = df['low'].iloc[-1]
        curr_high = df['high'].iloc[-1]
        
        for level in levels:
            price = level['price']
            # Simple retest: current low or high is within threshold of a level
            margin = price * (threshold_pct / 100)
            if abs(curr_low - price) <= margin or abs(curr_high - price) <= margin:
                return True
        return False

    @staticmethod
    def detect_hammer(df: pd.DataFrame):
        """
        Detects a Hammer/Pin Bar pattern.
        """
        if len(df) < 1: return False
        
        curr = df.iloc[-1]
        body = abs(curr['close'] - curr['open'])
        lower_wick = min(curr['open'], curr['close']) - curr['low']
        upper_wick = curr['high'] - max(curr['open'], curr['close'])
        
        # Hammer criteria: Lower wick >= 2x body, upper wick <= 0.1x total range
        total_range = curr['high'] - curr['low']
        if total_range == 0: return False
        
        return bool(lower_wick >= (2 * body) and upper_wick <= (0.1 * total_range))

    @staticmethod
    def detect_engulfing(df: pd.DataFrame):
        """
        Detects Bullish or Bearish Engulfing patterns.
        Returns: "Bullish", "Bearish", or None
        """
        if len(df) < 2: return None
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        curr_open, curr_close = curr['open'], curr['close']
        prev_open, prev_close = prev['open'], prev['close']
        
        # Bullish Engulfing
        if curr_close > curr_open and prev_close < prev_open:
            if curr_close > prev_open and curr_open < prev_close:
                return "Bullish"
        
        # Bearish Engulfing
        if curr_close < curr_open and prev_close > prev_open:
            if curr_close < prev_open and curr_open > prev_close:
                return "Bearish"
                
        return None
    @staticmethod
    def get_adx(df: pd.DataFrame, period: int = 14):
        """
        Calculates ADX (Average Directional Index) for trend strength.
        """
        if len(df) < period * 2:
            return 0.0
            
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = low.diff()
        
        plus_dm[plus_dm < 0] = 0
        plus_dm[plus_dm < minus_dm.abs()] = 0
        
        minus_dm = minus_dm.abs()
        minus_dm[minus_dm < 0] = 0
        minus_dm[minus_dm < plus_dm] = 0
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean() # Simplification of Wilder's
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0.0

    @staticmethod
    def get_structure_bias(df: pd.DataFrame):
        """
        Detects Higher High / Higher Low structure.
        Returns: "BULLISH", "BEARISH", or "NEUTRAL"
        """
        if len(df) < 20:
            return "NEUTRAL"
            
        # Very simple pivot detection
        highs = df['high'].values
        lows = df['low'].values
        
        # Last 3 "peaks" and "troughs" in a simple rolling window
        peaks = []
        troughs = []
        
        for i in range(2, len(df) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                peaks.append(highs[i])
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                troughs.append(lows[i])
        
        if len(peaks) >= 2 and len(troughs) >= 2:
            last_p = peaks[-1]
            prev_p = peaks[-2]
            last_t = troughs[-1]
            prev_t = troughs[-2]
            
            if last_p > prev_p and last_t > prev_t:
                return "BULLISH"
            elif last_p < prev_p and last_t < prev_t:
                return "BEARISH"
                
        return "NEUTRAL"

    @staticmethod
    def get_volume_ratio(df: pd.DataFrame, period: int = 20):
        """
        Calculates the ratio of current volume vs its 20-day average.
        If current volume is 0 (after-hours), uses last active candle.
        """
        if len(df) < 5:
            return 1.0
            
        # Handle after-hours (latest volume 0)
        idx = -1
        while idx > -len(df) and df['volume'].iloc[idx] == 0:
            idx -= 1
            
        avg_vol = df['volume'].rolling(window=period, min_periods=5).mean().iloc[idx]
        curr_vol = df['volume'].iloc[idx]
        
        if avg_vol > 0:
            return float(round(curr_vol / avg_vol, 2))
        return 1.0
