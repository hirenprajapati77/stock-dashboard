from .models import (
    MarketContext, TradeDecision, ActionType, SetupType, SetupState, EntryStatus,
    TradeQuality, TradeState, EntryType, ExitStrategy
)
from .market_context_engine import MarketContextEngine
from .market_regime_engine import MarketRegimeEngine
from .setup_detector import SetupDetector
from .confluence_engine import ConfluenceEngine
from .trigger_engine import TriggerEngine
from .entry_optimization_engine import EntryOptimizationEngine
from .risk_engine import RiskEngine
from .target_engine import TargetEngine
from .exit_engine import ExitEngine
from .option_selector import OptionSelector
from .signal_ranker import SignalRanker
from .allocation_engine import AllocationEngine
from .intent_engine import IntentEngine
from .noise_filter import NoiseFilter
from .performance_engine import PerformanceEngine
from .risk_environment_engine import RiskEnvironmentEngine
from .narrative_engine import NarrativeEngine
from .trade_lifecycle import TradeLifecycle
from typing import List


class TradeDecisionService:
    """
    V4 ALPHA Orchestrator: Adaptive Trading Intelligence Engine.

    Pipeline:
    Market Context → Market Regime → Setup Detection → Confluence Engine
    → Trigger Engine → Entry Optimization → Risk Engine → Target Engine
    → Exit Engine → Option Selector → Signal Ranker → Allocation Engine
    → Intent Engine → Risk Environment Filter → Narrative Engine → Trade Builder
    """

    @staticmethod
    def generate_trade(context: MarketContext, timeframe: str = "15m") -> TradeDecision:
        reasons: List[str] = []
        warnings: List[str] = []

        # ── 1. MARKET CONTEXT ──────────────────────────────────────────────
        m_context = MarketContextEngine.analyze(context)
        reasons.append(f"Market Bias: {m_context.market_bias} | Strength: {m_context.strength}")

        # ── 2. MARKET REGIME ───────────────────────────────────────────────
        m_regime = MarketRegimeEngine.detect(context)
        reasons.append(f"Regime: {m_regime.regime.value} (confidence {int(m_regime.confidence)}%)")

        # ── 3. RISK ENVIRONMENT FILTER ─────────────────────────────────────
        risk_level, risk_action, alloc_mult = RiskEnvironmentEngine.assess(context)
        if risk_level == "CRITICAL":
            warnings.append("CRITICAL volatility detected. Exposure heavily reduced.")
        elif risk_level == "HIGH":
            warnings.append("High volatility: trade with caution and reduced size.")

        # ── 4. SETUP STATE MACHINE ─────────────────────────────────────────
        setup, setup_state, base_conf, state_msg = SetupDetector.detect(context)
        reasons.append(state_msg)

        # ── 5. CONFLUENCE ENGINE ───────────────────────────────────────────
        confluence_score, conf_boost = ConfluenceEngine.calculate(context, m_context)
        if confluence_score < 40:
            warnings.append(f"Low confluence ({int(confluence_score)}/100). Trade quality reduced.")

        # ── 6. TRIGGER & TIMING ────────────────────────────────────────────
        action, entry, timing, trigger_msg = TriggerEngine.evaluate_trigger(context, setup, setup_state)
        if timing == EntryStatus.LATE:
            warnings.append("Late entry risk detected (>1% slippage from trigger).")

        # ── 7. ENTRY OPTIMIZATION ──────────────────────────────────────────
        entry_type, entry_msg = EntryOptimizationEngine.optimize(context, setup, setup_state)
        reasons.append(entry_msg)

        # ── 8. RISK ENGINE ─────────────────────────────────────────────────
        sl = RiskEngine.calculate_sl(context, action, entry)

        # ── 9. TARGET ENGINE ───────────────────────────────────────────────
        targets = TargetEngine.generate_targets(action, entry, sl)

        # ── 10. RISK/REWARD VALIDATION ─────────────────────────────────────
        rr = 0.0
        if action != ActionType.NO_TRADE:
            is_rr_valid, rr, rr_msg = RiskEngine.validate(entry, sl, targets[0])
            reasons.append(rr_msg)
            if not is_rr_valid:
                action = ActionType.NO_TRADE
                warnings.append("Trade rejected: Poor Risk/Reward ratio.")

        # ── 11. EXIT INTELLIGENCE ──────────────────────────────────────────
        exit_strat = ExitEngine.get_strategy(action, context.adx, context.atr, context.price)

        # ── 12. SIGNAL RANKER ──────────────────────────────────────────────
        adj_conf = base_conf + ((m_context.confidence_adjustment + conf_boost) / 100)
        # Regime-based adjustment
        if m_regime.impact.get("boost_breakout") and setup == SetupType.BREAKOUT:
            adj_conf += 0.08
        quality, q_score, q_reasons = SignalRanker.rank(context, adj_conf, rr)
        reasons.extend(q_reasons)

        # ── 13. ALLOCATION ENGINE ──────────────────────────────────────────
        allocation = AllocationEngine.get_allocation(quality, q_score)
        # Apply environment multiplier
        allocation.capital_percent = round(allocation.capital_percent * alloc_mult, 1)

        # ── 14. INTENT ENGINE ──────────────────────────────────────────────
        intent = IntentEngine.determine(timeframe, m_context.volatility)

        # ── 15. PERFORMANCE ENGINE ─────────────────────────────────────────
        perf = PerformanceEngine.get_stats(setup)

        # ── 16. NOISE FILTER ───────────────────────────────────────────────
        if action != ActionType.NO_TRADE:
            if NoiseFilter.should_suppress(quality, q_score):
                action = ActionType.NO_TRADE
                warnings.append("Noise Filter: Signal suppressed to prevent overtrading.")
            else:
                NoiseFilter.record_signal()

        # ── 17. OPTION SELECTOR ────────────────────────────────────────────
        strike, strat = OptionSelector.select_strike(context.symbol, action, entry, context.adx, context.trend)

        # ── 18. LIFECYCLE STATE ────────────────────────────────────────────
        lifecycle_state = TradeLifecycle.get_state(action, context.price, entry, sl, targets)

        # ── 19. NARRATIVE ENGINE ───────────────────────────────────────────
        narrative = NarrativeEngine.generate(context, m_context, m_regime, setup, confluence_score)

        # ── 20. NEXT ACTION ────────────────────────────────────────────────
        next_action = "Observe for setup confirmation"
        if setup_state == SetupState.READY:
            next_action = f"Place GTT order at {entry}"
        if setup_state == SetupState.TRIGGERED and action != ActionType.NO_TRADE:
            next_action = "Execute Market Order — Ideal Entry Window"
        if quality == TradeQuality.LOW:
            next_action = "Skip — wait for better confluence in other symbols"

        return TradeDecision(
            symbol=context.symbol,
            action=action,
            setup=setup,
            setup_state=setup_state,
            entry=entry,
            stop_loss=sl,
            targets=targets,
            confidence=max(0, min(100, adj_conf * 100)),
            quality=quality,
            quality_score=q_score,
            entry_status=timing,
            entry_type=entry_type,
            state=lifecycle_state,
            intent=intent,
            allocation=allocation,
            market_context=m_context,
            market_regime=m_regime,
            confluence_score=confluence_score,
            exit_strategy=exit_strat,
            narrative=narrative,
            historical_performance=perf,
            validity="SESSION",
            reason=reasons,
            warnings=warnings,
            next_action=next_action,
            option_strike=strike,
            option_strategy=strat,
            risk_reward=rr,
            state_message=state_msg if action != ActionType.NO_TRADE else trigger_msg
        )
