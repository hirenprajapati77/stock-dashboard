from .models import MarketContext, SetupType
from typing import Tuple

class SetupDetector:
    """Detects market setups like breakouts, breakdowns, and range-bound behavior."""
    
    @staticmethod
    def detect(context: MarketContext) -> Tuple[SetupType, float]:
        """
        Analyzes price action vs S/R levels.
        Returns: (SetupType, Confidence)
        """
        price = context.price
        nearest_res = min([r for r in context.resistances if r > price], default=None)
        nearest_supp = max([s for s in context.supports if s < price], default=None)
        
        # 1. Breakout Check (Price within 0.5% of resistance with high trend)
        if nearest_res:
            dist_res = (nearest_res - price) / price
            if dist_res < 0.005 and context.trend == "BULLISH" and context.adx > 20:
                return SetupType.BREAKOUT, 0.85
            
        # 2. Breakdown Check (Price within 0.5% of support)
        if nearest_supp:
            dist_supp = (price - nearest_supp) / price
            if dist_supp < 0.005 and context.trend == "BEARISH" and context.adx > 20:
                return SetupType.BREAKDOWN, 0.85
            
        # 3. Range Bound Check (Price bouncing between S/R)
        if nearest_res and nearest_supp:
            range_pct = (nearest_res - nearest_supp) / nearest_supp
            if range_pct < 0.03: # Tight range
                return SetupType.RANGE_BOUND, 0.60
                
        return SetupType.NONE, 0.0
