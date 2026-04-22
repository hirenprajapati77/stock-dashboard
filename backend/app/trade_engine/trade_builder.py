from .models import TradeDecision, ActionType, SetupState, TradeQuality
from typing import List

class TradeBuilder:
    """
    V3 Trade Formatter for Human-Readable Intelligence.
    """
    
    @staticmethod
    def format_output(decision: TradeDecision) -> str:
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
        output += f"QUALITY: {decision.quality.value}\n"
        output += f"INTENT: {decision.intent.value}\n\n"
        
        # Capital & Market
        output += f"CAPITAL: {int(decision.allocation.capital_percent)}% allocation\n"
        output += f"MARKET: {decision.market_context.market_bias.capitalize()}\n"
        
        if decision.warnings:
            output += f"\n⚠️ WARNINGS:\n"
            for w in decision.warnings:
                output += f"- {w}\n"
                
        return output
