from .models import MarketContext
from typing import Tuple, Optional

class LiquidityEngine:
    """
    Identifies liquidity zones (swing highs/lows) for target validation.
    """

    @staticmethod
    def find_target(context: MarketContext, action: str) -> Tuple[Optional[float], str, float]:
        """
        Returns: (nearest_liquidity_target, liquidity_strength, distance_pct)
        """
        price = context.price
        candidates = []

        # 1. Resistances are liquidity targets for BUY trades
        if action == "BUY":
            candidates = [r for r in context.resistances if r > price]
        else:
            candidates = [s for s in context.supports if s < price]

        if not candidates:
            return None, "LOW", 0.0

        target = min(candidates, key=lambda x: abs(x - price))
        distance_pct = abs(target - price) / price * 100

        # 2. Strength based on how many levels cluster near target
        cluster_count = sum(1 for c in candidates if abs(c - target) / target < 0.01)
        strength = "HIGH" if cluster_count >= 2 else "MEDIUM" if cluster_count == 1 else "LOW"

        return target, strength, round(distance_pct, 2)
