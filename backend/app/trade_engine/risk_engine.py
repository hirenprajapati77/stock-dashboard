from .models import MarketContext, ActionType
from typing import Tuple, List

class RiskEngine:
    """Calculates Stop Loss and validates Risk/Reward."""
    
    @staticmethod
    def calculate_sl(context: MarketContext, action: ActionType, entry: float) -> float:
        """
        Calculates SL using swing levels or ATR.
        """
        if action == ActionType.BUY:
            # Nearest support or 1.5 * ATR
            nearest_supp = max([s for s in context.supports if s < entry], default=entry - (context.atr * 1.5))
            sl = min(nearest_supp, entry - (context.atr * 1.0))
            return round(sl, 2)
        
        if action == ActionType.SELL:
            # Nearest resistance or 1.5 * ATR
            nearest_res = min([r for r in context.resistances if r > entry], default=entry + (context.atr * 1.5))
            sl = max(nearest_res, entry + (context.atr * 1.0))
            return round(sl, 2)
            
        return 0.0

    @staticmethod
    def validate(entry: float, sl: float, target1: float) -> Tuple[bool, float, str]:
        """
        Ensures RR >= 1.5
        """
        risk = abs(entry - sl)
        reward = abs(target1 - entry)
        
        if risk == 0: return False, 0, "Zero risk detected"
        
        rr = reward / risk
        if rr < 1.5:
            return False, round(rr, 2), f"Poor Risk/Reward ratio: {rr:.2f} < 1.5"
            
        return True, round(rr, 2), "Valid Risk/Reward"
