from .models import TradeDecision, ActionType

class TradeBuilder:
    """
    V5 Trade Formatter — Full Execution Edge Output.
    """

    @staticmethod
    def format_output(decision: TradeDecision) -> str:
        symbol = decision.symbol
        grade = decision.meta_score.trade_grade
        state_label = f"({decision.setup.value} {decision.setup_state.value})"

        output = f"📈 {symbol} {state_label}\n\n"

        if decision.action != ActionType.NO_TRADE:
            verb = "BUY ABOVE" if decision.action.value == "BUY" else "SELL BELOW"
            output += f"{verb}: {decision.entry}\n"
            output += f"SL: {decision.stop_loss}\n"
            output += f"TARGET: {' / '.join(map(str, decision.targets))}\n\n"

        output += f"CONFIDENCE: {decision.confidence}% | META SCORE: {decision.meta_score.meta_score} ({grade})\n"
        output += f"ENTRY: {decision.entry_type.value} | EXIT: {decision.exit_strategy.exit_strategy}\n\n"

        output += f"MARKET: {decision.market_context.market_bias.capitalize()} ({decision.market_regime.regime.value})\n"
        if decision.liquidity.nearest_liquidity_target:
            output += f"LIQUIDITY TARGET: {decision.liquidity.nearest_liquidity_target}\n"
        output += f"ORDERFLOW: {decision.microstructure.orderflow_signal} ({decision.microstructure.momentum_quality})\n\n"

        output += f"CAPITAL: {int(decision.allocation.capital_percent)}% | SESSION: {decision.session}\n"
        output += f"RISK STATUS: {decision.drawdown_status.status}\n"
        if decision.scaling.scaling_allowed:
            output += f"SCALING: Add at {decision.scaling.add_position_level} (max {decision.scaling.max_additions}x)\n"

        output += f"\n📝 {decision.narrative}\n"

        if decision.warnings:
            output += "\n⚠️ WARNINGS:\n"
            for w in decision.warnings:
                output += f"  - {w}\n"

        output += f"\n🎯 NEXT: {decision.next_action}"
        return output
