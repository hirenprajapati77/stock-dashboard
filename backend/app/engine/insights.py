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
