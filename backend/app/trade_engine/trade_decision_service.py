from .models import MarketContext, TradeDecision, ActionType, SetupType, SetupState, EntryStatus, TradeQuality, TradeState
from .market_context_engine import MarketContextEngine
from .setup_detector import SetupDetector
from .trigger_engine import TriggerEngine
from .risk_engine import RiskEngine
from .target_engine import TargetEngine
from .option_selector import OptionSelector
from .signal_ranker import SignalRanker
from .allocation_engine import AllocationEngine
from .intent_engine import IntentEngine
from .noise_filter import NoiseFilter
from .performance_engine import PerformanceEngine
from .trade_lifecycle import TradeLifecycle
from typing import List, Optional

class TradeDecisionService:
    """
    V3 Orchestrator: FULL TRADING INTELLIGENCE SYSTEM.
    Market Context -> Setup Detection -> Trigger -> Risk -> Targets -> Option Selector -> Signal Ranker -> Allocation -> Intent -> Noise Filter
    """
    
    @staticmethod
    def generate_trade(context: MarketContext, timeframe: str = "15m") -> TradeDecision:
        reasons: List[str] = []
        warnings: List[str] = []
        
        # 1. Market Context Engine
        m_context = MarketContextEngine.analyze(context)
        reasons.append(f"Market Bias: {m_context.market_bias}")
        
        # 2. State Machine Analysis
        setup, setup_state, base_conf, state_msg = SetupDetector.detect(context)
        
        # 3. Trigger & Timing Intelligence
        action, entry, timing, trigger_msg = TriggerEngine.evaluate_trigger(context, setup, setup_state)
        
        # 4. Risk & SL
        sl = RiskEngine.calculate_sl(context, action, entry)
        
        # 5. Generate Targets
        targets = TargetEngine.generate_targets(action, entry, sl)
        
        # 6. Risk/Reward Validation
        rr = 0.0
        if action != ActionType.NO_TRADE:
            is_rr_valid, rr, rr_msg = RiskEngine.validate(entry, sl, targets[0])
            if not is_rr_valid:
                action = ActionType.NO_TRADE
                warnings.append("Trade rejected: Poor Risk/Reward ratio.")

        # 7. Signal Ranker (Adjusted by Market Context)
        adjusted_conf = base_conf + (m_context.confidence_adjustment / 100)
        quality, q_score, q_reasons = SignalRanker.rank(context, adjusted_conf, rr)
        reasons.extend(q_reasons)
        
        # 8. Allocation Engine
        allocation = AllocationEngine.get_allocation(quality, q_score)
        
        # 9. Intent Engine
        intent = IntentEngine.determine(timeframe, m_context.volatility)
        
        # 10. Performance Insights
        perf = PerformanceEngine.get_stats(setup)
        
        # 11. Noise Filter (Overtrading Control)
        if action != ActionType.NO_TRADE:
            if NoiseFilter.should_suppress(quality, q_score):
                action = ActionType.NO_TRADE
                warnings.append("Noise Filter: Signal suppressed to prevent overtrading.")
            else:
                NoiseFilter.record_signal()

        # 12. Option Strategy
        strike, strat = OptionSelector.select_strike(context.symbol, action, entry, context.adx, context.trend)
        
        # 13. Lifecycle Management
        lifecycle_state = TradeLifecycle.get_state(action, context.price, entry, sl, targets)
        
        # Next Action Guide
        next_action = "Observe for breakout confirmation"
        if setup_state == SetupState.READY: next_action = f"Place GTT order at {entry}"
        if setup_state == SetupState.TRIGGERED and action != ActionType.NO_TRADE: next_action = "Execute Market Order (Ideal Entry)"

        return TradeDecision(
            symbol=context.symbol,
            action=action,
            setup=setup,
            setup_state=setup_state,
            entry=entry,
            stop_loss=sl,
            targets=targets,
            confidence=max(0, min(100, adjusted_conf * 100)),
            quality=quality,
            quality_score=q_score,
            entry_status=timing,
            state=lifecycle_state,
            intent=intent,
            allocation=allocation,
            market_context=m_context,
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
