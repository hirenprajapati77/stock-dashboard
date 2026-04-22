from .models import ActionType
from typing import Optional, Tuple

class OptionSelector:
    """
    Advanced Option Selection based on Momentum Strength.
    Strategies: MOMENTUM (OTM), SAFE (ATM), AGGRESSIVE (ITM for delta)
    """
    
    @staticmethod
    def select_strategy(action: ActionType, adx: float, trend: str) -> Tuple[str, int]:
        """
        Determines strike offset based on momentum.
        Strong momentum (ADX > 35) -> OTM (+1 offset)
        Moderate -> ATM (0)
        Weak -> ITM (-1)
        """
        if adx > 35: return "MOMENTUM", 1
        if adx > 25: return "SAFE", 0
        return "AGGRESSIVE", -1

    @staticmethod
    def select_strike(symbol: str, action: ActionType, price: float, adx: float, trend: str) -> Tuple[Optional[str], str]:
        """
        Calculates optimal strike with momentum bias.
        """
        if action == ActionType.NO_TRADE:
            return None, "NONE"
            
        strat, offset = OptionSelector.select_strategy(action, adx, trend)
        
        # Increment logic
        increment = 50 if "NIFTY" in symbol else 10
        if price > 10000: increment = 100
        
        atm_strike = round(price / increment) * increment
        
        # Apply offset (Bullish: +offset for OTM, Bearish: -offset for OTM)
        if action == ActionType.BUY:
            final_strike = atm_strike + (offset * increment)
            return f"{symbol} {int(final_strike)} CE", strat
        elif action == ActionType.SELL:
            final_strike = atm_strike - (offset * increment)
            return f"{symbol} {int(final_strike)} PE", strat
            
        return None, "NONE"
