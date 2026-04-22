from .models import TradeQuality
from typing import Tuple

class ScalingEngine:
    """
    Enables intelligent position scaling / pyramiding.
    """

    @staticmethod
    def evaluate(quality: TradeQuality, adx: float, targets: list) -> dict:
        """
        Determines if position scaling is allowed post Target1.
        """
        allowed = False
        add_level = None
        max_adds = 0

        # Only scale into HIGH quality trades with strong trend
        if quality == TradeQuality.HIGH and adx > 28 and len(targets) >= 2:
            allowed = True
            add_level = targets[0]  # Add at Target1 if momentum holds
            max_adds = 2

        return {
            "scaling_allowed": allowed,
            "add_position_level": add_level,
            "max_additions": max_adds
        }
