from .models import TradeState, ActionType, MarketContext

class TradeLifecycle:
    """
    Manages the lifecycle of a trade from WAITING to CLOSED.
    """
    
    @staticmethod
    def get_state(action: ActionType, price: float, entry: float, sl: float, targets: list) -> TradeState:
        """
        Determines current trade state based on price vs levels.
        """
        if action == ActionType.NO_TRADE:
            return TradeState.CLOSED
            
        if action == ActionType.BUY:
            if price <= sl: return TradeState.SL_HIT
            if price >= targets[1]: return TradeState.TARGET2_HIT
            if price >= targets[0]: return TradeState.TARGET1_HIT
            if price >= entry: return TradeState.RUNNING
            return TradeState.WAITING
            
        if action == ActionType.SELL:
            if price >= sl: return TradeState.SL_HIT
            if price <= targets[1]: return TradeState.TARGET2_HIT
            if price <= targets[0]: return TradeState.TARGET1_HIT
            if price <= entry: return TradeState.RUNNING
            return TradeState.WAITING
            
        return TradeState.WAITING
