from .models import ActionType
from typing import List

class TargetEngine:
    """Generates multi-layered profit targets."""
    
    @staticmethod
    def generate_targets(action: ActionType, entry: float, sl: float) -> List[float]:
        """
        T1 = 1.5R, T2 = 3R, T3 = 5R
        """
        risk = abs(entry - sl)
        
        if action == ActionType.BUY:
            return [
                round(entry + (risk * 1.5), 2),
                round(entry + (risk * 3.0), 2),
                round(entry + (risk * 5.0), 2)
            ]
        
        if action == ActionType.SELL:
            return [
                round(entry - (risk * 1.5), 2),
                round(entry - (risk * 3.0), 2),
                round(entry - (risk * 5.0), 2)
            ]
            
        return []
