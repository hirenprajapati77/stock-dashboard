from typing import Dict, List, Optional, Literal
import time

Quadrant = Literal["LEADING", "WEAKENING", "LAGGING", "IMPROVING"]

class AICommentaryService:
    _commentary_cache: Dict[str, str] = {}

    @classmethod
    def generate_commentary(cls, context: Dict) -> str:
        symbol = context.get('symbol', 'Unknown')
        curr_q = context.get('currentQuadrant', 'UNKNOWN').capitalize()
        prev_q = context.get('previousQuadrant', 'UNKNOWN').capitalize()
        rs = context.get('RS', 1.0)
        rm = context.get('RM', 0.0)
        rs_trend = context.get('rsTrend', 'flat')
        rm_trend = context.get('rmTrend', 'flat')
        rank = context.get('rank')
        contributors = context.get('topContributors', [])
        
        # 1. Base Narrative based on Quadrant Shift
        if curr_q == "Leading" and prev_q in ["Improving", "Weakening"]:
            narrative = f"{symbol} has transitioned into the Leading quadrant, signaling a period of market-beating performance."
        elif curr_q == "Weakening" and prev_q == "Leading":
            narrative = f"{symbol} is now in the Weakening quadrant, suggesting that its internal momentum is starting to fade despite high relative strength."
        elif curr_q == "Lagging":
            narrative = f"{symbol} remains in the Lagging quadrant, reflecting both poor relative strength and negative momentum versus the benchmark."
        elif curr_q == "Improving":
            narrative = f"{symbol} is moving into the Improving quadrant, which often serves as an early signal of a potential recovery in relative performance."
        else:
            narrative = f"{symbol} is currently in the {curr_q} quadrant."

        # 2. Add Trend Analysis
        trend_msg = f" The relative strength is {rs_trend} ({rs:.2f})"
        if rm_trend == "accelerating":
            trend_msg += " with accelerating momentum."
        elif rm_trend == "decelerating":
            trend_msg += " but momentum is decelerating."
        else:
            trend_msg += "."

        # 3. Add Context (Rank & Contributors)
        context_msg = ""
        if rank and rank <= 3:
            context_msg = f" It currently ranks #{rank} in overall relative strength."
        
        contributor_msg = ""
        if contributors:
            contributor_msg = f" Leadership within the sector is primarily driven by {', '.join(contributors)}."

        # Combine
        full_text = f"{narrative}{trend_msg}{context_msg}{contributor_msg}"
        
        # Cache key
        cache_key = f"{symbol}_{curr_q}_{context.get('timeframe', 'Daily')}"
        cls._commentary_cache[cache_key] = full_text
        
        return full_text

    @classmethod
    def get_commentary(cls, symbol: str, quadrant: str, timeframe: str = "Daily") -> Optional[str]:
        cache_key = f"{symbol}_{quadrant}_{timeframe}"
        return cls._commentary_cache.get(cache_key)
