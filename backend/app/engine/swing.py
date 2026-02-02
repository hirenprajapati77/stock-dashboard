import pandas as pd
import numpy as np

class SwingEngine:
    @staticmethod
    def get_swings(df: pd.DataFrame, window: int = 2):
        """
        Detects Swing Highs and Swing Lows using an N-candle window.
        A high is a swing high if it's highest in window before and after.
        """
        highs = df['high'].values
        lows = df['low'].values
        
        swing_highs = []
        swing_lows = []
        
        for i in range(window, len(df) - window):
            # Check for Swing High
            is_high = True
            for j in range(1, window + 1):
                if highs[i] <= highs[i-j] or highs[i] <= highs[i+j]:
                    is_high = False
                    break
            if (is_high):
                swing_highs.append({
                    'index': int(i), 
                    'price': float(highs[i]), 
                    'time': str(df.index[i]),
                    'volume': int(df['volume'].iloc[i])
                })
                
            # Check for Swing Low
            is_low = True
            for j in range(1, window + 1):
                if lows[i] >= lows[i-j] or lows[i] >= lows[i+j]:
                    is_low = False
                    break
            if is_low:
                swing_lows.append({
                    'index': int(i), 
                    'price': float(lows[i]), 
                    'time': str(df.index[i]),
                    'volume': int(df['volume'].iloc[i])
                })
                
        return swing_highs, swing_lows
