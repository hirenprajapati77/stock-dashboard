import math
import pandas as pd
from typing import Dict, Any

class GannEngine:
    @staticmethod
    def calculate_gann_levels(price: float) -> Dict[str, float]:
        """
        Calculates Gann Square of 9 levels based on square root price logic.
        Standard step angles:
          - 45 degrees: factor = 0.25 (G1)
          - 90 degrees: factor = 0.50 (G2)
          - 180 degrees: factor = 1.00 (G3)
        """
        if price <= 0:
            return {
                "g1_res": 0.0, "g2_res": 0.0, "g3_res": 0.0,
                "g1_supp": 0.0, "g2_supp": 0.0, "g3_supp": 0.0
            }
            
        root = math.sqrt(price)
        
        # Resistance Levels (root + angle factor)^2
        g1_res = (root + 0.125) ** 2  # 22.5 degrees (G1)
        g2_res = (root + 0.25) ** 2   # 45 degrees (G2)
        g3_res = (root + 0.5) ** 2    # 90 degrees (G3)
        
        # Support Levels (root - angle factor)^2
        g1_supp = (root - 0.125) ** 2
        g2_supp = (root - 0.25) ** 2
        g3_supp = (root - 0.5) ** 2
        
        return {
            "g1_res": round(g1_res, 2),
            "g2_res": round(g2_res, 2),
            "g3_res": round(g3_res, 2),
            "g1_supp": round(g1_supp, 2),
            "g2_supp": round(g2_supp, 2),
            "g3_supp": round(g3_supp, 2)
        }

    @staticmethod
    def evaluate_gann_breakouts(df: pd.DataFrame, levels: Dict[str, float]) -> Dict[str, Any]:
        """
        Checks if the current price is breaking through any key Gann Resistance or Support levels.
        """
        if df is None or df.empty or not levels:
            return {"status": "NEUTRAL", "level": None, "strength": 0}
            
        cmp = float(df['close'].iloc[-1])
        prev_cmp = float(df['close'].iloc[-2]) if len(df) > 1 else cmp
        
        # Check breakouts above resistances
        if prev_cmp <= levels["g1_res"] < cmp:
            return {"status": "BREAKOUT_G1", "level": levels["g1_res"], "strength": 1, "bias": "BULLISH"}
        elif prev_cmp <= levels["g2_res"] < cmp:
            return {"status": "BREAKOUT_G2", "level": levels["g2_res"], "strength": 2, "bias": "BULLISH"}
        elif prev_cmp <= levels["g3_res"] < cmp:
            return {"status": "BREAKOUT_G3", "level": levels["g3_res"], "strength": 3, "bias": "BULLISH"}
            
        # Check breakdowns below supports
        if prev_cmp >= levels["g1_supp"] > cmp:
            return {"status": "BREAKDOWN_G1", "level": levels["g1_supp"], "strength": 1, "bias": "BEARISH"}
        elif prev_cmp >= levels["g2_supp"] > cmp:
            return {"status": "BREAKDOWN_G2", "level": levels["g2_supp"], "strength": 2, "bias": "BEARISH"}
        elif prev_cmp >= levels["g3_supp"] > cmp:
            return {"status": "BREAKDOWN_G3", "level": levels["g3_supp"], "strength": 3, "bias": "BEARISH"}
            
        # Current position check
        if cmp > levels["g3_res"]:
            return {"status": "ABOVE_G3", "level": levels["g3_res"], "strength": 3, "bias": "STRONG_BULLISH"}
        elif cmp < levels["g3_supp"]:
            return {"status": "BELOW_G3", "level": levels["g3_supp"], "strength": 3, "bias": "STRONG_BEARISH"}
            
        return {"status": "RANGE", "level": None, "strength": 0, "bias": "NEUTRAL"}
