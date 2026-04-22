from .models import MarketContext, TradeDecision, ActionType, SetupType, SetupState, EntryStatus, TradeQuality, TradeState
from .setup_detector import SetupDetector
from .trigger_engine import TriggerEngine
from .risk_engine import RiskEngine
from .target_engine import TargetEngine
from .option_selector import OptionSelector
from .signal_ranker import SignalRanker
from .trade_lifecycle import TradeLifecycle
from typing import List

class TradeDecisionService:
    """
    Institution-grade Orchestrator for Decision + Execution.
    """
    
    @staticmethod
    def generate_trade(context: MarketContext) -> TradeDecision:
        reasons: List[str] = []
        warnings: List[str] = []
        
        # 1. State Machine Analysis
        setup, setup_state, base_conf, state_msg = SetupDetector.detect(context)
        reasons.append(state_msg)
        
        # 2. Trigger & Timing Intelligence
        action, entry, timing, trigger_msg = TriggerEngine.evaluate_trigger(context, setup, setup_state)
        if timing == EntryStatus.LATE:
            warnings.append("Late entry risk detected (>1% slippage)")
            
        # 3. Risk & SL
        sl = RiskEngine.calculate_sl(context, action, entry)
        
        # 4. Generate Targets
        targets = TargetEngine.generate_targets(action, entry, sl)
        
        # 5. Risk/Reward Validation
        rr = 0.0
        if action != ActionType.NO_TRADE:
            is_rr_valid, rr, rr_msg = RiskEngine.validate(entry, sl, targets[0])
            reasons.append(rr_msg)
            if not is_rr_valid:
                action = ActionType.NO_TRADE # Force NO_TRADE on bad RR
                warnings.append("Trade rejected: Poor Risk/Reward ratio.")

        # 6. Quality Scoring (Signal Ranker)
        quality, q_score, q_reasons = SignalRanker.rank(context, base_conf, rr)
        reasons.extend(q_reasons)
        
        if quality == TradeQuality.LOW:
            action = ActionType.NO_TRADE
            warnings.append("Low quality signal filtered out.")

        # 7. Option Strategy
        strike, strat = OptionSelector.select_strike(context.symbol, action, entry, context.adx, context.trend)
        
        # 8. Lifecycle Management
        lifecycle_state = TradeLifecycle.get_state(action, context.price, entry, sl, targets)
        
        # 9. Next Action Logic
        next_action = "Observe for breakout confirmation"
        if setup_state == SetupState.READY: next_action = f"Place GTT order at {entry}"
        if setup_state == SetupState.TRIGGERED and action != ActionType.NO_TRADE: next_action = "Execute Market Order (Ideal Entry)"
        if quality == TradeQuality.LOW: next_action = "Scan for better setups in other symbols"

        return TradeDecision(
            symbol=context.symbol,
            action=action,
            setup=setup,
            setup_state=setup_state,
            entry=entry,
            stop_loss=sl,
            targets=targets,
            confidence=base_conf * 100,
            quality=quality,
            quality_score=q_score,
            entry_status=timing,
            state=lifecycle_state,
            validity="SESSION",
            reason=reasons,
            warnings=warnings,
            next_action=next_action,
            option_strike=strike,
            option_strategy=strat,
            risk_reward=rr,
            state_message=state_msg if action != ActionType.NO_TRADE else trigger_msg
        )
