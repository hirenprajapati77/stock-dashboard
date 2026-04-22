from .models import MarketContext, MarketCondition
from typing import Tuple, Dict

class ConfluenceEngine:
    """
    Combines multiple signals into a unified confluence score (0-100).
    """
    
    @staticmethod
    def calculate(context: MarketContext, m_condition: MarketCondition) -> Tuple[float, float]:
        score = 0.0
        
        # 1. Trend Alignment (20 pts)
        if context.trend == m_condition.market_bias: score += 20
        elif context.trend != "SIDEWAYS": score += 10
        
        # 2. Volume Expansion (20 pts)
        if context.volume_ratio > 2.0: score += 20
        elif context.volume_ratio > 1.2: score += 10
        
        # 3. Momentum Strength (20 pts)
        if context.adx > 30: score += 20
        elif context.adx > 20: score += 10
        
        # 4. Level Strength (20 pts)
        # Based on supports/resistances count
        if (len(context.supports) + len(context.resistances)) > 10: score += 20
        elif (len(context.supports) + len(context.resistances)) > 5: score += 10
        
        # 5. MTF Alignment (20 pts)
        if context.higher_tf_trend == context.trend: score += 20
        
        # Boost confidence if score is high
        boost = 0.0
        if score > 80: boost = 10.0
        elif score < 40: boost = -15.0
        
        return score, boost
