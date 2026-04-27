from typing import Tuple

class DrawdownEngine:
    """
    Capital protection via drawdown tracking.
    Tracks consecutive losses and halts trading when threshold is breached.
    """

    # Session state (In-memory; replace with DB for persistence)
    _consecutive_losses: int = 0
    _total_drawdown_pct: float = 0.0
    MAX_CONSECUTIVE_LOSSES = 3
    MAX_DRAWDOWN_PCT = 6.0  # Halt at 6% portfolio drawdown

    @staticmethod
    def assess() -> Tuple[str, str, float]:
        """
        Returns: (drawdown_status, action, allocation_multiplier)
        """
        losses = DrawdownEngine._consecutive_losses
        drawdown = DrawdownEngine._total_drawdown_pct

        if drawdown >= DrawdownEngine.MAX_DRAWDOWN_PCT:
            return "STOP", "HALT", 0.0

        if losses >= DrawdownEngine.MAX_CONSECUTIVE_LOSSES:
            return "WARNING", "REDUCE", 0.5

        return "SAFE", "CONTINUE", 1.0

    @staticmethod
    def record_loss(loss_pct: float = 1.0):
        DrawdownEngine._consecutive_losses += 1
        DrawdownEngine._total_drawdown_pct += loss_pct

    @staticmethod
    def record_win():
        DrawdownEngine._consecutive_losses = 0  # Reset streak on a win

    @staticmethod
    def reset_session():
        DrawdownEngine._consecutive_losses = 0
        DrawdownEngine._total_drawdown_pct = 0.0
