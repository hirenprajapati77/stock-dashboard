from .models import MarketContext, MarketRegime, MarketRegimeType
from typing import Dict

class MarketRegimeEngine:
    """
    Detects market regimes: TRENDING, MEAN_REVERT, VOLATILE, BREAKOUT_PHASE.
    """
    
    @staticmethod
    def detect(context: MarketContext) -> MarketRegime:
        adx = context.adx
        atr = context.atr
        price = context.price
        
        regime = MarketRegimeType.MEAN_REVERT
        confidence = 60.0
        impact = {"boost_breakout": False, "avoid_mean_reversion": False}
        
        # 1. Trending Regime
        if adx > 25 and context.trend != "SIDEWAYS":
            regime = MarketRegimeType.TRENDING
            confidence = min(100, adx * 2)
            impact["avoid_mean_reversion"] = True
            
        # 2. Volatile Regime
        elif atr > (price * 0.04):
            regime = MarketRegimeType.VOLATILE
            confidence = 80
            
        # 3. Breakout Phase (Compression)
        elif adx < 20 and atr < (price * 0.015):
            regime = MarketRegimeType.BREAKOUT_PHASE
            confidence = 70
            impact["boost_breakout"] = True
            
        return MarketRegime(
            regime=regime,
            confidence=confidence,
            impact=impact
        )
