from .models import TradeQuality, Allocation

class AllocationEngine:
    """
    Decides capital allocation and trade priority.
    """
    
    @staticmethod
    def get_allocation(quality: TradeQuality, score: float) -> Allocation:
        # 1. Capital Allocation %
        capital_pct = 0.0
        priority = 3
        
        if quality == TradeQuality.HIGH:
            capital_pct = 35.0 # 30-40% range
            priority = 1
        elif quality == TradeQuality.MEDIUM:
            capital_pct = 15.0 # 10-20% range
            priority = 2
        else:
            capital_pct = 0.0 # Rejected in service anyway
            
        return Allocation(
            capital_percent=capital_pct,
            priority_rank=priority,
            max_positions_allowed=3
        )
