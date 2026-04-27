from .models import MarketContext
from typing import Tuple

class RiskEnvironmentEngine:
    """
    Detects hostile market conditions and suppresses weak trades.
    """
    
    @staticmethod
    def assess(context: MarketContext) -> Tuple[str, str, float]:
        """
        Returns: (risk_level, action, allocation_multiplier)
        """
        atr = context.atr
        price = context.price
        
        # 1. Extreme Volatility (Crisis)
        if atr > (price * 0.05):
            return "CRITICAL", "REDUCE_EXPOSURE", 0.25
            
        # 2. High Volatility
        if atr > (price * 0.03):
            return "HIGH", "CAUTION", 0.5
            
        # 3. Low Volatility (No trades possible)
        if atr < (price * 0.003):
            return "LOW", "WAIT_FOR_RANGE_BREAK", 0.75
            
        return "NORMAL", "PROCEED", 1.0
