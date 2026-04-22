from .models import TradeDecision, ActionType, SetupState, TradeQuality
from typing import List

class TradeBuilder:
    """
    Institution-grade Trade Formatter (JSON + Human Readable).
    """
    
    @staticmethod
    def format_output(decision: TradeDecision) -> str:
        """
        Generates the requested 📈 SYMBOL format with State and Quality.
        """
        symbol = decision.symbol
        state_label = f"({decision.setup.value} {decision.setup_state.value})"
        
        # Header
        output = f"📈 {symbol} {state_label}\n\n"
        
        if decision.action != ActionType.NO_TRADE:
            action_verb = "BUY ABOVE" if decision.action == ActionType.BUY else "SELL BELOW"
            output += f"{action_verb}: {decision.entry}\n"
            output += f"SL: {decision.stop_loss}\n"
            output += f"TARGET: {' / '.join(map(str, decision.targets))}\n\n"
        
        # Status & Quality
        output += f"STATUS: {decision.state_message}\n"
        output += f"CONFIDENCE: {int(decision.confidence)}%\n"
        output += f"QUALITY: {decision.quality.value} (Score: {int(decision.quality_score)})\n"
        output += f"NEXT ACTION: {decision.next_action}\n"
        
        if decision.warnings:
            output += f"\n⚠️ WARNINGS:\n"
            for w in decision.warnings:
                output += f"- {w}\n"
                
        return output
