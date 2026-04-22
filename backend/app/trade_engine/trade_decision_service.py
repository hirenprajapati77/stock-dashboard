from .models import MarketContext, TradeDecision, ActionType, SetupType
from .setup_detector import SetupDetector
from .trigger_engine import TriggerEngine
from .risk_engine import RiskEngine
from .target_engine import TargetEngine
from .option_selector import OptionSelector
from typing import List

class TradeDecisionService:
    """
    Orchestrator for the Trade Decision Engine.
    Coordinates all sub-engines to produce a single actionable decision.
    """
    
    @staticmethod
    def generate_trade(context: MarketContext) -> TradeDecision:
        reasons: List[str] = []
        
        # 1. Detect Setup
        setup, confidence = SetupDetector.detect(context)
        if setup == SetupType.NONE:
            return TradeDecision(
                symbol=context.symbol,
                action=ActionType.NO_TRADE,
                setup=SetupType.NONE,
                entry=0.0,
                stop_loss=0.0,
                targets=[],
                confidence=0.0,
                validity="EXPIRED",
                reason=["No clear setup detected in current price action"],
                risk_reward=0.0
            )
            
        reasons.append(f"Detected {setup.value} pattern")
        
        # 2. Determine Entry
        action, entry = TriggerEngine.calculate_entry(context, setup)
        if action == ActionType.NO_TRADE:
            return TradeDecision(
                symbol=context.symbol,
                action=ActionType.NO_TRADE,
                setup=setup,
                entry=0.0,
                stop_loss=0.0,
                targets=[],
                confidence=confidence,
                validity="EXPIRED",
                reason=["Failed to calculate a valid entry trigger"],
                risk_reward=0.0
            )

        # 3. Calculate Risk & SL
        sl = RiskEngine.calculate_sl(context, action, entry)
        
        # 4. Generate Targets
        targets = TargetEngine.generate_targets(action, entry, sl)
        
        # 5. Validate Risk/Reward
        is_valid, rr, rr_msg = RiskEngine.validate(entry, sl, targets[0])
        if not is_valid:
            return TradeDecision(
                symbol=context.symbol,
                action=ActionType.NO_TRADE,
                setup=setup,
                entry=entry,
                stop_loss=sl,
                targets=targets,
                confidence=confidence * 0.5, # Reduce confidence for bad RR
                validity="EXPIRED",
                reason=[rr_msg],
                risk_reward=rr
            )

        # 6. Select Option Strike
        strike = OptionSelector.select_strike(context.symbol, action, entry)
        
        # 7. Final Polish
        reasons.append(rr_msg)
        if context.adx > 25: reasons.append("Strong momentum confirmed via ADX")
        if context.oi_data: reasons.append("OI alignment confirmed")

        return TradeDecision(
            symbol=context.symbol,
            action=action,
            setup=setup,
            entry=entry,
            stop_loss=sl,
            targets=targets,
            confidence=confidence,
            validity="TODAY",
            reason=reasons,
            option_strike=strike,
            risk_reward=rr
        )
