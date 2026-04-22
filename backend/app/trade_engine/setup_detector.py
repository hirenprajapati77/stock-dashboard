from .models import MarketContext, SetupType, SetupState
from typing import Tuple

class SetupDetector:
    """
    Institution-grade Setup Detector using a State Machine.
    States: FORMING, READY, TRIGGERED, INVALID
    """
    
    @staticmethod
    def detect(context: MarketContext) -> Tuple[SetupType, SetupState, float, str]:
        """
        Analyzes price action vs S/R levels with state transitions.
        Returns: (SetupType, SetupState, BaseConfidence, Message)
        """
        price = context.price
        atr = context.atr
        adx = context.adx
        
        # 1. Find nearest key levels
        nearest_res = min([r for r in context.resistances if r > price], default=None)
        nearest_supp = max([s for s in context.supports if s < price], default=None)
        
        # 2. Check for BREAKOUT (Bullish)
        if nearest_res:
            dist_res = (nearest_res - price) / price
            
            # TRIGGERED: Price closed above resistance
            if context.close > nearest_res:
                return SetupType.BREAKOUT, SetupState.TRIGGERED, 0.90, "Price broke and closed above resistance."
            
            # READY: Price near resistance + Strong Momentum
            if dist_res < 0.008 and adx > 25 and context.trend == "BULLISH":
                return SetupType.BREAKOUT, SetupState.READY, 0.80, "Price near resistance with strong momentum."
                
            # FORMING: Price near resistance but low momentum or trend mismatch
            if dist_res < 0.015:
                return SetupType.BREAKOUT, SetupState.FORMING, 0.50, "Price approaching resistance; momentum building."

        # 3. Check for BREAKDOWN (Bearish)
        if nearest_supp:
            dist_supp = (price - nearest_supp) / price
            
            # TRIGGERED: Price closed below support
            if context.close < nearest_supp:
                return SetupType.BREAKDOWN, SetupState.TRIGGERED, 0.90, "Price broke and closed below support."
                
            # READY: Price near support + Strong Momentum
            if dist_supp < 0.008 and adx > 25 and context.trend == "BEARISH":
                return SetupType.BREAKDOWN, SetupState.READY, 0.80, "Price near support with strong bearish momentum."
                
            # FORMING: Price near support
            if dist_supp < 0.015:
                return SetupType.BREAKDOWN, SetupState.FORMING, 0.50, "Price approaching support floor."

        # 4. Check for RETEST
        # Logic: Setup was triggered recently, and price is now back at the level
        if nearest_res and abs(price - nearest_res) / nearest_res < 0.003:
             if context.trend == "BULLISH":
                 return SetupType.RETEST, SetupState.READY, 0.85, "Successful retest of broken resistance (now support)."

        # 5. INVALID: Structure broken or too much volatility
        if atr > (price * 0.05): # Excess volatility
            return SetupType.NONE, SetupState.INVALID, 0.0, "Volatility too high for reliable structure."

        return SetupType.NONE, SetupState.INVALID, 0.0, "No actionable setup detected."
