from .models import MarketContext, SetupType, SetupState, ActionType, EntryStatus
from typing import Tuple

class TriggerEngine:
    """
    Advanced Trigger Engine with Entry Timing and Breakout Confirmation.
    """
    
    @staticmethod
    def evaluate_trigger(context: MarketContext, setup: SetupType, state: SetupState) -> Tuple[ActionType, float, EntryStatus, str]:
        """
        Determines entry price, timing status, and action.
        """
        price = context.price
        atr = context.atr
        # Dynamic buffer based on 15% of ATR
        buffer = round(atr * 0.15, 2)
        
        if setup == SetupType.BREAKOUT:
            res = min([r for r in context.resistances if r > context.prev_close], default=price)
            trigger_price = round(res + buffer, 2)
            
            # 1. Action & Entry Status
            if state == SetupState.TRIGGERED:
                # How far are we from trigger?
                slippage = (price - trigger_price) / trigger_price
                if slippage > 0.01: # 1% away from trigger is too late
                    return ActionType.BUY, trigger_price, EntryStatus.LATE, "Price moved >1% from breakout point."
                return ActionType.BUY, trigger_price, EntryStatus.IDEAL, "Breakout confirmed; entry within ideal range."
                
            if state == SetupState.READY:
                return ActionType.BUY, trigger_price, EntryStatus.EARLY, f"Waiting for breakout above {trigger_price}."
                
        if setup == SetupType.BREAKDOWN:
            supp = max([s for s in context.supports if s < context.prev_close], default=price)
            trigger_price = round(supp - buffer, 2)
            
            if state == SetupState.TRIGGERED:
                slippage = (trigger_price - price) / trigger_price
                if slippage > 0.01:
                    return ActionType.SELL, trigger_price, EntryStatus.LATE, "Price moved >1% from breakdown point."
                return ActionType.SELL, trigger_price, EntryStatus.IDEAL, "Breakdown confirmed; entry within ideal range."
                
            if state == SetupState.READY:
                return ActionType.SELL, trigger_price, EntryStatus.EARLY, f"Waiting for breakdown below {trigger_price}."

        return ActionType.NO_TRADE, 0.0, EntryStatus.NONE, "Waiting for setup confirmation."
