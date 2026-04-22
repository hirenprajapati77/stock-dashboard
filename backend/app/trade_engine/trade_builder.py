from .models import TradeDecision, ActionType, SetupState

class TradeBuilder:
    """
    V4 Trade Formatter — Full Intelligence Output.
    """

    @staticmethod
    def format_output(decision: TradeDecision) -> str:
        symbol = decision.symbol
        state_label = f"({decision.setup.value} {decision.setup_state.value})"

        output = f"📈 {symbol} {state_label}\n\n"

        if decision.action != ActionType.NO_TRADE:
            verb = "BUY ABOVE" if decision.action.value == "BUY" else "SELL BELOW"
            output += f"{verb}: {decision.entry}\n"
            output += f"SL: {decision.stop_loss}\n"
            output += f"TARGET: {' / '.join(map(str, decision.targets))}\n\n"

        output += f"STATUS: {decision.state_message}\n"
        output += f"CONFIDENCE: {int(decision.confidence)}%\n"
        output += f"QUALITY: {decision.quality.value}\n"
        output += f"INTENT: {decision.intent.value}\n\n"
        output += f"ENTRY TYPE: {decision.entry_type.value}\n"
        output += f"EXIT: {decision.exit_strategy.exit_strategy} Strategy\n\n"
        output += f"MARKET: {decision.market_context.market_bias.capitalize()} ({decision.market_regime.regime.value})\n"
        output += f"CONFLUENCE: {int(decision.confluence_score)}/100\n"
        output += f"CAPITAL: {int(decision.allocation.capital_percent)}% allocation\n\n"
        output += f"📝 {decision.narrative}\n"

        if decision.warnings:
            output += "\n⚠️ WARNINGS:\n"
            for w in decision.warnings:
                output += f"- {w}\n"

        output += f"\n🎯 NEXT: {decision.next_action}"
        return output
