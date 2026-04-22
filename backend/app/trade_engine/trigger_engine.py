from .models import MarketContext, SetupType, ActionType
from typing import Tuple, Optional

class TriggerEngine:
    """Calculates entry prices based on detected setups."""
    
    @staticmethod
    def calculate_entry(context: MarketContext, setup: SetupType) -> Tuple[ActionType, float]:
        """
        Generates trigger price with buffer.
        Returns: (ActionType, EntryPrice)
        """
        price = context.price
        buffer = context.atr * 0.1 # 10% of ATR as buffer
        
        if setup == SetupType.BREAKOUT:
            # Entry above resistance
            res = min([r for r in context.resistances if r > price], default=price)
            return ActionType.BUY, round(res + buffer, 2)
            
        if setup == SetupType.BREAKDOWN:
            # Entry below support
            supp = max([s for s in context.supports if s < price], default=price)
            return ActionType.SELL, round(supp - buffer, 2)
            
        return ActionType.NO_TRADE, 0.0
