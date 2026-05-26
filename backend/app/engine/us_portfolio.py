# backend/app/engine/us_portfolio.py
from typing import Dict, Any

class USQualityPortfolioEngine:
    @staticmethod
    def evaluate_us_quality(fundamentals: Dict[str, Any], rsi_daily: float) -> Dict[str, Any]:
        """
        Enforces Golden Rule 9: US Market is a separate, quality-first investment portfolio.
        No complex technical filters - focus strictly on fundamental and competitive dominance.
        """
        mcap_billions = fundamentals.get("market_cap_billion", 0.0)
        roe = fundamentals.get("roe_pct", 0.0)
        rev_growth = fundamentals.get("revenue_growth_3y", 0.0)
        profit_growth = fundamentals.get("profit_growth_3y", 0.0)
        debt_to_equity = fundamentals.get("debt_to_equity", 1.0)
        has_fcf = fundamentals.get("free_cash_flow_positive", True)

        # 1. Hard Quality Gates
        if mcap_billions < 2.0:
            return {"signal": "AVOID", "quality_score": 0, "reason": "Fails Minimum Market Cap Gate ($2 Billion)"}
        
        if roe < 15.0:
            return {"signal": "AVOID", "quality_score": 0, "reason": "Fails Minimum Return on Equity Gate (15%)"}
            
        if rev_growth < 15.0 or profit_growth < 15.0:
            return {"signal": "AVOID", "quality_score": 0, "reason": "Fails Minimum Growth Threshold Gate (15% Sales & Profit Growth)"}

        # 2. Quality Scoring Algorithm (Max 100)
        # Base score of 60 for passing the hard gates
        quality_score = 60
        
        # Debt buffer
        if debt_to_equity < 0.30:
            quality_score += 20
        elif debt_to_equity < 0.50:
            quality_score += 10
            
        # Cash flow stability
        if has_fcf:
            quality_score += 20
        else:
            quality_score -= 10

        # 3. Simple Valuation & Position Adjustments (chase protection)
        if rsi_daily < 30.0:
            signal = "BUY"  # Deep value compression buy
            reason = "Extreme value compression zone. Dominant franchise available at deep discount."
        elif rsi_daily > 80.0:
            signal = "HOLD" # Extended; let existing profits run, but do not buy fresh positions
            reason = "Technically extended (RSI > 80). Protect capital and hold current positions."
        else:
            signal = "BUY"
            reason = "Dominant globally leading business model in a solid accumulation base."
            
        return {
            "signal": signal,
            "quality_score": int(quality_score),
            "reason": reason
        }
