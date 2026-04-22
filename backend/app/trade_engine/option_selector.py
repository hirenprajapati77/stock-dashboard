from .models import ActionType
from typing import Optional

class OptionSelector:
    """Selects the best Option Strike (ATM/ITM)."""
    
    @staticmethod
    def select_strike(symbol: str, action: ActionType, price: float) -> Optional[str]:
        """
        Chooses ATM strike based on standard increments.
        """
        if action == ActionType.NO_TRADE:
            return None
            
        # Example increment logic (Nifty=50, Stocks=10 or 5 depends on price)
        increment = 50 if "NIFTY" in symbol else 10
        if price > 10000: increment = 100
        
        atm_strike = round(price / increment) * increment
        
        if action == ActionType.BUY:
            return f"{symbol} {int(atm_strike)} CE"
        elif action == ActionType.SELL:
            return f"{symbol} {int(atm_strike)} PE"
            
        return None
