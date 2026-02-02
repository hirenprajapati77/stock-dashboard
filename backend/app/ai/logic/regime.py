import numpy as np

class RegimeClassifier:
    def analyze(self, features: dict):
        """
        Classifies market as TRENDING, RANGING, or HIGH_VOLATILITY using ADX and RSI.
        """
        ema_dist = features.get('dist_from_ema', 0.0)
        atr_expansion = features.get('atr_expansion', 1.0)
        adx = features.get('adx', 20.0)
        rsi = features.get('rsi', 50.0)
        
        # 1. High Volatility Check
        if atr_expansion > 2.5:
            return {
                "market_regime": "HIGH_VOLATILITY",
                "reason": f"ATR expansion ({atr_expansion}x) is extreme. High risk of whipsaws."
            }
            
        # 2. Trend Exhaustion Check (RSI)
        if rsi > 70 or rsi < 30:
            state = "OVERBOUGHT" if rsi > 70 else "OVERSOLD"
            return {
                "market_regime": f"TREND_EXHAUSTION_{state}",
                "reason": f"RSI is {rsi} ({state}). Trend may be overextended despite EMA distance."
            }

        # 3. Trend Strength Check (ADX)
        if adx > 25:
            direction = "UP" if ema_dist > 0 else "DOWN"
            return {
                "market_regime": f"TRENDING_{direction}",
                "reason": f"ADX is {adx} (Strong Trend). Price is {abs(ema_dist)}% from EMA."
            }
            
        # 4. Sideways / Ranging
        return {
            "market_regime": "RANGING",
            "reason": f"ADX is {adx} (Weak Trend). Price is hovering near equilibrium."
        }
