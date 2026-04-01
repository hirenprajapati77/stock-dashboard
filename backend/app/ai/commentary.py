from typing import Dict, List, Optional, Literal
import time

Quadrant = Literal["LEADING", "WEAKENING", "LAGGING", "IMPROVING"]

class AICommentaryService:
    _commentary_cache: Dict[str, str] = {}

    @classmethod
    def generate_commentary(cls, context: Dict) -> str:
        entity_type = context.get('entityType', 'stock')
        symbol = context.get('symbol', 'Unknown')
        curr_q = context.get('currentQuadrant', 'UNKNOWN').upper()
        rs = context.get('RS', 1.0)
        rm = context.get('RM', 0.0)
        rs_trend = context.get('rsTrend', 'flat')
        rm_trend = context.get('rmTrend', 'flat')
        setup_type = context.get('setupType', 'MOMENTUM_HIT')
        quality_score = context.get('qualityScore', 50)
        
        # 1. Determine "Mode" (Phase of Trend)
        mode = "STEADY"
        if rs > 1.05 and rm > 0.02:
            mode = "CLIMAX"
        elif rs > 1.0 and rm > 0:
            mode = "STEADY"
        elif rs < 1.0 and rm > 0:
            mode = "EARLY"
        elif rs < 1.0 and rm < 0:
            mode = "LAGGING"

        # 2. Base Narrative logic
        if entity_type == "sector":
            if curr_q == "LEADING":
                narrative = f"{symbol} is the dominant market theme, showing significant outperformance."
            elif curr_q == "IMPROVING":
                narrative = f"{symbol} is emerging as a potential leader, showing early relative strength signs."
            elif curr_q == "WEAKENING":
                narrative = f"{symbol} leadership is cooling off; momentum is starting to fade."
            else:
                narrative = f"{symbol} continues to underperform the broader market."
        else:
            if mode == "CLIMAX":
                narrative = f"{symbol} is in a high-velocity extension phase."
            elif mode == "EARLY":
                narrative = f"{symbol} is showing an early-stage trend reversal/improvement."
            else:
                narrative = f"{symbol} is maintaining a steady uptrend relative to its sector."

        # 3. Setup Specific Insights
        setup_msg = ""
        if setup_type == "BREAKOUT":
            setup_msg = " Confirmed price breakout with high technical alignment."
        elif setup_type == "RSI_PULLBACK":
            setup_msg = " Low-risk entry opportunity following a healthy pullback."
        elif setup_type == "VOLUME_SURGE":
            setup_msg = " Unusual institutional accumulation detected via volume spike."

        # 4. Actionable Guidance (The "So What?")
        guidance = ""
        if mode == "CLIMAX":
            guidance = " Avoid chasing at these levels; look to book partial profits or trail stops tightly."
        elif mode == "EARLY" and quality_score > 60:
            guidance = " High potential for trend follow-through. Aggressive entries can be considered."
        elif mode == "STEADY" and setup_type == "RSI_PULLBACK":
            guidance = " Ideal 'Buy the Dip' scenario within a confirmed uptrend."
        else:
            guidance = " Monitor for better risk-reward alignment before committing fresh capital."

        # Combine
        full_text = f"{narrative}{setup_msg}{guidance}"
        
        # Cache key
        cache_key = f"{symbol}_{curr_q}_{context.get('timeframe', 'Daily')}"
        cls._commentary_cache[cache_key] = full_text
        
        return full_text

    @classmethod
    def get_commentary(cls, symbol: str, quadrant: str, timeframe: str = "Daily") -> Optional[str]:
        cache_key = f"{symbol}_{quadrant}_{timeframe}"
        return cls._commentary_cache.get(cache_key)
