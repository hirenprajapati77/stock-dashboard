from .models import MarketContext, ActionType, ExitStrategy

class ExitEngine:
    """
    Dynamic Exit Strategy Engine.
    """
    
    @staticmethod
    def get_strategy(action: ActionType, adx: float, atr: float, price: float) -> ExitStrategy:
        strategy = "STATIC"
        dynamic = False
        early_exit = False
        
        # 1. Trailing if momentum is strong
        if adx > 30:
            strategy = "TRAILING"
            dynamic = True
            
        # 2. Tighten if volatility is high
        if atr > (price * 0.05):
            strategy = "AGGRESSIVE"
            dynamic = True
            early_exit = True
            
        return ExitStrategy(
            exit_strategy=strategy,
            dynamic_targets=dynamic,
            early_exit_signal=early_exit
        )
