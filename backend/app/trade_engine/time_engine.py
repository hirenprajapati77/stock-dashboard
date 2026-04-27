from datetime import datetime
from typing import Tuple

class TimeEngine:
    """
    Adapts signal behavior based on IST trading session window.
    Sessions: OPENING (9:15-10:30) | MID (10:30-13:30) | CLOSING (13:30-15:30)
    """

    @staticmethod
    def get_session() -> Tuple[str, float]:
        """
        Returns: (session_name, confidence_adjustment)
        """
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        total_minutes = hour * 60 + minute

        # Opening session: 9:15 - 10:30 (high volatility, momentum trades favoured)
        if 555 <= total_minutes < 630:
            return "OPENING", +5.0

        # Mid session: 10:30 - 13:30 (low quality, reduce confidence)
        if 630 <= total_minutes < 810:
            return "MID", -5.0

        # Closing session: 13:30 - 15:30 (trend continuation possible)
        if 810 <= total_minutes <= 930:
            return "CLOSING", +3.0

        # Outside market hours
        return "AFTER_HOURS", -10.0
