from .models import MarketContext, TradeDecision, TradeQuality, ActionType
from typing import Tuple, List

class SignalRanker:
    """
    Ranks signals based on Quality (HIGH, MEDIUM, LOW) and Score (0-100).
    """
    
    @staticmethod
    def rank(context: MarketContext, base_confidence: float, rr: float) -> Tuple[TradeQuality, float, List[str]]:
        """
        Computes final quality score using MTF, Volume, and Trend.
        """
        score = base_confidence * 100
        reasons = []
        
        # 1. Volume Expansion (Critical for institution grade)
        if context.volume_ratio > 2.0:
            score += 15
            reasons.append(f"Exceptional volume expansion ({context.volume_ratio:.1f}x)")
        elif context.volume_ratio > 1.5:
            score += 10
            reasons.append("Healthy volume participation")
        else:
            score -= 10 # Penalty for weak volume
            
        # 2. MTF Alignment
        if context.higher_tf_trend == context.trend:
            score += 15
            reasons.append(f"MTF Trend Alignment confirmed ({context.trend})")
        elif context.higher_tf_trend != "NEUTRAL":
            score -= 10
            
        # 3. Risk Reward Bonus
        if rr > 3.0:
            score += 10
            reasons.append("Excellent Risk/Reward potential (> 3R)")
            
        # 4. Final Normalization
        final_score = max(0, min(100, score))
        
        # 5. Quality Mapping
        if final_score >= 80:
            quality = TradeQuality.HIGH
        elif final_score >= 50:
            quality = TradeQuality.MEDIUM
        else:
            quality = TradeQuality.LOW
            
        return quality, final_score, reasons
