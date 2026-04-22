from .models import (
    MarketContext, TradeDecision, ActionType, SetupType, SetupState, EntryStatus,
    TradeQuality, TradeState, EntryType, Microstructure, Liquidity, Scaling,
    DrawdownStatus, MetaScore
)
from .market_context_engine import MarketContextEngine
from .market_regime_engine import MarketRegimeEngine
from .microstructure_engine import MicrostructureEngine
from .liquidity_engine import LiquidityEngine
from .setup_detector import SetupDetector
from .false_breakout_engine import FalseBreakoutEngine
from .confluence_engine import ConfluenceEngine
from .trigger_engine import TriggerEngine
from .entry_optimization_engine import EntryOptimizationEngine
from .risk_engine import RiskEngine
from .target_engine import TargetEngine
from .exit_engine import ExitEngine
from .time_engine import TimeEngine
from .meta_score_engine import MetaScoreEngine
from .allocation_engine import AllocationEngine
from .drawdown_engine import DrawdownEngine
from .scaling_engine import ScalingEngine
from .intent_engine import IntentEngine
from .noise_filter import NoiseFilter
from .performance_engine import PerformanceEngine
from .risk_environment_engine import RiskEnvironmentEngine
from .narrative_engine import NarrativeEngine
from .option_selector import OptionSelector
from .signal_ranker import SignalRanker
from .trade_lifecycle import TradeLifecycle
from typing import List


class TradeDecisionService:
    """
    V5 EXECUTION EDGE ENGINE — 22-Step Adaptive Intelligence Pipeline.

    Market Context → Market Regime → Risk Environment
    → Microstructure → Liquidity → Setup Detection → False Breakout Filter
    → Confluence → Trigger → Entry Optimization → Risk → Targets → Exit
    → Time Engine → Meta Score → Allocation → Drawdown → Scaling
    → Intent → Performance → Noise Filter → Narrative → Trade Builder
    """

    @staticmethod
    def generate_trade(context: MarketContext, timeframe: str = "15m") -> TradeDecision:
        reasons: List[str] = []
        warnings: List[str] = []

        # ── 1. MARKET CONTEXT ──────────────────────────────────────────────
        m_context = MarketContextEngine.analyze(context)
        reasons.append(f"Market: {m_context.market_bias} | Vol: {m_context.volatility} | Strength: {m_context.strength}")

        # ── 2. MARKET REGIME ───────────────────────────────────────────────
        m_regime = MarketRegimeEngine.detect(context)
        reasons.append(f"Regime: {m_regime.regime.value} ({int(m_regime.confidence)}% confidence)")

        # ── 3. RISK ENVIRONMENT ────────────────────────────────────────────
        risk_level, risk_action, env_mult = RiskEnvironmentEngine.assess(context)
        if risk_level in ("HIGH", "CRITICAL"):
            warnings.append(f"Risk environment {risk_level}: {risk_action}")

        # ── 4. MICROSTRUCTURE (Order Flow) ─────────────────────────────────
        micro_signal, micro_quality, micro_adj = MicrostructureEngine.analyze(context)
        micro_model = Microstructure(
            orderflow_signal=micro_signal,
            momentum_quality=micro_quality,
            confidence_adjustment=micro_adj
        )
        reasons.append(f"Orderflow: {micro_signal} ({micro_quality})")
        if micro_signal == "EXHAUSTION":
            warnings.append("Exhaustion detected — consider skipping or reducing size.")

        # ── 5. LIQUIDITY ENGINE ────────────────────────────────────────────
        action_hint = "BUY" if m_context.market_bias == "BULLISH" else "SELL"
        liq_target, liq_strength, liq_dist = LiquidityEngine.find_target(context, action_hint)
        liq_model = Liquidity(
            nearest_liquidity_target=liq_target,
            liquidity_strength=liq_strength,
            distance_to_liquidity=liq_dist
        )
        if liq_target:
            reasons.append(f"Liquidity target: {liq_target} ({liq_strength}, {liq_dist:.1f}% away)")

        # ── 6. SETUP STATE MACHINE ─────────────────────────────────────────
        setup, setup_state, base_conf, state_msg = SetupDetector.detect(context)
        reasons.append(state_msg)

        # ── 7. FALSE BREAKOUT FILTER ───────────────────────────────────────
        is_fake, fake_penalty = FalseBreakoutEngine.check(context, setup)
        if is_fake:
            warnings.append("False breakout detected — volume/candle structure rejected.")
            base_conf = max(0.0, base_conf + (fake_penalty / 100))

        # ── 8. CONFLUENCE ENGINE ───────────────────────────────────────────
        confluence_score, conf_boost = ConfluenceEngine.calculate(context, m_context)
        if confluence_score < 40:
            warnings.append(f"Low confluence ({int(confluence_score)}/100) — signal quality weak.")

        # ── 9. TRIGGER ENGINE ──────────────────────────────────────────────
        action, entry, timing, trigger_msg = TriggerEngine.evaluate_trigger(context, setup, setup_state)
        if timing == EntryStatus.LATE:
            warnings.append("Late entry detected — slippage risk > 1%.")

        # ── 10. ENTRY OPTIMIZATION ─────────────────────────────────────────
        entry_type, entry_msg = EntryOptimizationEngine.optimize(context, setup, setup_state)
        reasons.append(entry_msg)

        # ── 11. RISK ENGINE ────────────────────────────────────────────────
        sl = RiskEngine.calculate_sl(context, action, entry)

        # ── 12. TARGET ENGINE ──────────────────────────────────────────────
        targets = TargetEngine.generate_targets(action, entry, sl)

        # ── 13. RR VALIDATION ──────────────────────────────────────────────
        rr = 0.0
        if action != ActionType.NO_TRADE:
            is_rr_valid, rr, rr_msg = RiskEngine.validate(entry, sl, targets[0])
            reasons.append(rr_msg)
            if not is_rr_valid:
                action = ActionType.NO_TRADE
                warnings.append("Rejected: R/R below threshold.")

        # ── 14. EXIT ENGINE ────────────────────────────────────────────────
        exit_strat = ExitEngine.get_strategy(action, context.adx, context.atr, context.price)

        # ── 15. TIME ENGINE ────────────────────────────────────────────────
        session, time_adj = TimeEngine.get_session()
        reasons.append(f"Session: {session}")

        # ── 16. SIGNAL RANKER ──────────────────────────────────────────────
        adj_conf = base_conf
        adj_conf += (m_context.confidence_adjustment + conf_boost + micro_adj) / 100
        adj_conf += time_adj / 100
        if m_regime.impact.get("boost_breakout") and setup == SetupType.BREAKOUT:
            adj_conf += 0.08
        quality, q_score, q_reasons = SignalRanker.rank(context, adj_conf, rr)
        reasons.extend(q_reasons)

        # ── 17. META SCORE ─────────────────────────────────────────────────
        perf = PerformanceEngine.get_stats(setup)
        meta_val, grade, decision = MetaScoreEngine.compute(
            confluence_score=confluence_score,
            regime_confidence=m_regime.confidence,
            micro_conf_adj=micro_adj,
            liquidity_strength=liq_strength,
            perf_win_rate=perf.setup_win_rate,
            risk_level=risk_level,
            drawdown_status=DrawdownEngine.assess()[0],
            time_adj=time_adj
        )
        meta_model = MetaScore(meta_score=meta_val, trade_grade=grade, final_decision=decision)

        if decision == "REJECT":
            action = ActionType.NO_TRADE
            warnings.append(f"Meta Score Engine: Trade REJECTED (Grade {grade}, Score {meta_val})")

        # ── 18. ALLOCATION + DRAWDOWN ──────────────────────────────────────
        allocation = AllocationEngine.get_allocation(quality, q_score)
        dd_status, dd_action, dd_mult = DrawdownEngine.assess()
        allocation.capital_percent = round(allocation.capital_percent * env_mult * dd_mult, 1)
        dd_model = DrawdownStatus(status=dd_status, action=dd_action)
        if dd_status == "STOP":
            action = ActionType.NO_TRADE
            warnings.append("Drawdown limit reached — trading HALTED for session protection.")

        # ── 19. SCALING ────────────────────────────────────────────────────
        scaling_data = ScalingEngine.evaluate(quality, context.adx, targets)
        scaling_model = Scaling(**scaling_data)

        # ── 20. INTENT + NOISE FILTER ──────────────────────────────────────
        intent = IntentEngine.determine(timeframe, m_context.volatility)
        if action != ActionType.NO_TRADE:
            if NoiseFilter.should_suppress(quality, q_score):
                action = ActionType.NO_TRADE
                warnings.append("Noise Filter: Suppressed to prevent overtrading.")
            else:
                NoiseFilter.record_signal()

        # ── 21. OPTION SELECTOR ────────────────────────────────────────────
        strike, strat = OptionSelector.select_strike(context.symbol, action, entry, context.adx, context.trend)

        # ── 22. LIFECYCLE + NARRATIVE ──────────────────────────────────────
        lifecycle_state = TradeLifecycle.get_state(action, context.price, entry, sl, targets)
        narrative = NarrativeEngine.generate(context, m_context, m_regime, setup, confluence_score)

        # Next Action Guide
        next_action = "Observe — waiting for setup confirmation"
        if setup_state == SetupState.READY and action != ActionType.NO_TRADE:
            next_action = f"Place GTT order at {entry} | SL {sl}"
        if setup_state == SetupState.TRIGGERED and action != ActionType.NO_TRADE:
            next_action = "Execute now — ideal entry window open"
        if decision == "REJECT" or quality == TradeQuality.LOW:
            next_action = "Skip — scan for better setups"

        return TradeDecision(
            symbol=context.symbol,
            action=action,
            setup=setup,
            setup_state=setup_state,
            entry=entry,
            stop_loss=sl,
            targets=targets,
            confidence=round(max(0, min(100, adj_conf * 100)), 1),
            quality=quality,
            quality_score=round(q_score, 1),
            entry_status=timing,
            entry_type=entry_type,
            state=lifecycle_state,
            intent=intent,
            allocation=allocation,
            market_context=m_context,
            market_regime=m_regime,
            microstructure=micro_model,
            liquidity=liq_model,
            confluence_score=round(confluence_score, 1),
            exit_strategy=exit_strat,
            meta_score=meta_model,
            scaling=scaling_model,
            drawdown_status=dd_model,
            narrative=narrative,
            historical_performance=perf,
            validity="SESSION",
            reason=reasons,
            warnings=warnings,
            next_action=next_action,
            option_strike=strike,
            option_strategy=strat,
            risk_reward=round(rr, 2),
            state_message=state_msg if action != ActionType.NO_TRADE else trigger_msg,
            session=session
        )
