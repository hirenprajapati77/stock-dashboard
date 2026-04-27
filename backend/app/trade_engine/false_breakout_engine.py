from .models import MarketContext, SetupType
from typing import Tuple

class FalseBreakoutEngine:
    """
    Eliminates fake breakouts before they generate signals.
    """

    @staticmethod
    def check(context: MarketContext, setup: SetupType) -> Tuple[bool, float]:
        """
        Returns: (is_fake_breakout, confidence_penalty)
        """
        if setup not in (SetupType.BREAKOUT, SetupType.BREAKDOWN):
            return False, 0.0

        price = context.price
        high = context.high
        low = context.low
        close = context.close
        vol = context.volume_ratio

        # 1. Volume check — breakout without volume = fake
        if vol < 1.1:
            return True, -25.0

        # 2. Wick check — if close is far inside candle range it's a wick rejection
        candle_range = high - low
        if candle_range > 0:
            if setup == SetupType.BREAKOUT:
                # Close should be in upper 40% of candle
                close_position = (close - low) / candle_range
                if close_position < 0.6:
                    return True, -20.0
            else:
                # BREAKDOWN: close should be in lower 40%
                close_position = (close - low) / candle_range
                if close_position > 0.4:
                    return True, -20.0

        return False, 0.0
