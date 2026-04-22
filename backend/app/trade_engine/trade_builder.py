from .models import TradeDecision, ActionType, SetupType
from typing import List

class TradeBuilder:
    """Formats the Trade Decision into human-readable and structured outputs."""
    
    @staticmethod
    def format_output(decision: TradeDecision) -> str:
        """
        Generates the requested 📈 SYMBOL format.
        """
        if decision.action == ActionType.NO_TRADE:
            return f"❌ {decision.symbol}: NO TRADE\nREASON: {', '.join(decision.reason)}"
            
        action_text = "BUY ABOVE" if decision.action == ActionType.BUY else "SELL BELOW"
        targets_text = " / ".join([str(t) for t in decision.targets])
        
        output = f"📈 {decision.symbol} ({action_text})\n"
        output += f"ENTRY: {decision.entry}\n"
        output += f"SL: {decision.stop_loss}\n"
        output += f"TARGET: {targets_text}\n"
        output += f"CONFIDENCE: {int(decision.confidence * 100)}%\n"
        output += f"STRIKE: {decision.option_strike or 'N/A'}"
        
        return output
