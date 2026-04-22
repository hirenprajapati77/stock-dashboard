from .models import MarketContext
from typing import Tuple

class MicrostructureEngine:
    """
    Analyzes price-volume interaction to detect real order flow.
    Signals: ABSORPTION, MOMENTUM, EXHAUSTION
    """

    @staticmethod
    def analyze(context: MarketContext) -> Tuple[str, str, float]:
        """
        Returns: (orderflow_signal, momentum_quality, confidence_adjustment)
        """
        price_move = abs(context.close - context.prev_close) / context.prev_close
        vol_ratio = context.volume_ratio

        # 1. Absorption: High volume, low price movement
        if vol_ratio > 1.8 and price_move < 0.004:
            return "ABSORPTION", "STRONG", +8.0   # Coiling before breakout

        # 2. Momentum Spike: Fast price move + volume expansion
        if vol_ratio > 1.5 and price_move > 0.008:
            return "MOMENTUM", "STRONG", +12.0

        # 3. Exhaustion: Price moves but volume drops
        if vol_ratio < 0.8 and price_move > 0.005:
            return "EXHAUSTION", "WEAK", -15.0

        # 4. Neutral/Dull
        return "NEUTRAL", "WEAK", -5.0
