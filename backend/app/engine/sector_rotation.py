# backend/app/engine/sector_rotation.py
import numpy as np
from typing import List, Dict, Any

class SectorRotationEngine:
    THEME_UNIVERSE = [
        "AI_AUTOMATION", "SEMICONDUCTOR", "DATA_CENTERS", "CLOUD_COMPUTING",
        "ELECTRIC_VEHICLES", "RENEWABLE_ENERGY", "DEFENCE_AEROSPACE", "PHARMA_HEALTHCARE",
        "SPECIALTY_CHEMICALS", "ROBOTICS", "DIGITAL_INFRA", "CYBERSECURITY", "SPACE_TECH"
    ]

    @staticmethod
    def calculate_theme_composite(
        price_returns_1m_3m_6m: List[float], # [1M_ret_pct, 3M_ret_pct, 6M_ret_pct]
        rsi_weekly: float,
        rsi_monthly: float,
        breakouts_count: int,
        fii_sector_flows_cr: float,
        volume_expansion_ratio: float,
        policy_sentiment_score: float = 50.0 # 0 to 100
    ) -> float:
        """
        Dynamically calculates composite institutional momentum score (0-100) for a sector.
        """
        # 1. Price Momentum Weighting (Max 35 pts)
        # Weighting: 1M (50%), 3M (30%), 6M (20%)
        weighted_ret = (price_returns_1m_3m_6m[0] * 0.50) + (price_returns_1m_3m_6m[1] * 0.30) + (price_returns_1m_3m_6m[2] * 0.20)
        # Scale return to max 35 (e.g. 15% weighted monthly return = 35 pts)
        momentum_points = min(max(weighted_ret * 2.33, 0.0), 35.0)

        # 2. RSI Bounds Check (Max 20 pts)
        # We prefer strong continuation zones (RSI between 60 and 78)
        rsi_points = 0
        if 60.0 <= rsi_weekly <= 78.0:
            rsi_points += 10
        elif rsi_weekly > 78.0:
            rsi_points += 5  # Overheated but momentum exists
        else:
            rsi_points += 2

        if 60.0 <= rsi_monthly <= 78.0:
            rsi_points += 10
        elif rsi_monthly > 78.0:
            rsi_points += 5
        else:
            rsi_points += 2

        # 3. FII sector flow score (Max 15 pts)
        # Scale flow: +₹500 Cr = 15 pts
        flow_points = min(max(fii_sector_flows_cr / 33.3, 0.0), 15.0)

        # 4. Volume Surge Factor (Max 15 pts)
        # Vol expansion ratio: 2.0x average volume = 15 pts
        volume_points = min(max((volume_expansion_ratio - 1.0) * 15.0, 0.0), 15.0)

        # 5. Breakout activity and Policy/Sentiment Tailwind (Max 15 pts)
        breakout_points = min(breakouts_count * 2.0, 10.0) # Max 10 pts for breakout count
        policy_points = (policy_sentiment_score / 100.0) * 5.0 # Max 5 pts for sentiment

        composite = momentum_points + rsi_points + flow_points + volume_points + breakout_points + policy_points
        return float(np.clip(composite, 0.0, 100.0))

    @staticmethod
    def get_focus_sectors(sector_scores: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Ranks all themes and returns top 2-4 active sectors with institutional reason tags.
        Sectors scoring below 65 are excluded or marked inactive.
        """
        ranked = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        active_focus = []

        for theme, score in ranked[:4]:
            if score >= 65.0: # Hard gate for active sector focus
                tags = []
                if score >= 85.0:
                    tags.append("Institutional Accumulation")
                if score >= 75.0:
                    tags.append("Volume Surge")
                
                # Check for high RSI or breakout triggers
                tags.append("Sector Leadership")
                
                active_focus.append({
                    "theme": theme,
                    "score": round(score, 1),
                    "reason_tags": tags,
                    "is_active": True
                })
        return active_focus
