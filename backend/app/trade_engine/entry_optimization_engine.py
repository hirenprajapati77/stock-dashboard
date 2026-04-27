from .models import MarketContext, SetupType, SetupState, EntryType, EntryStatus
from typing import Tuple

class EntryOptimizationEngine:
    """
    Improves entry timing and classifies entry types.
    """
    
    @staticmethod
    def optimize(context: MarketContext, setup: SetupType, state: SetupState) -> Tuple[EntryType, str]:
        # 1. Detect Retest pattern
        if setup == SetupType.RETEST:
            return EntryType.RETEST_ENTRY, "Breakout confirmed; price pull-back successful."
            
        # 2. Momentum Entry
        if state == SetupState.TRIGGERED and context.volume_ratio > 1.8:
            return EntryType.MOMENTUM_ENTRY, "High-velocity momentum breakout detected."
            
        # 3. Early Entry
        if state == SetupState.READY:
            return EntryType.EARLY_ENTRY, "Anticipatory entry before breakout confirmation."
            
        return EntryType.NONE, "Waiting for optimization trigger."
