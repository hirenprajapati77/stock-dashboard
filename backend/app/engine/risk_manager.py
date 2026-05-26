# backend/app/engine/risk_manager.py
from typing import Dict, Any

class RiskManager:
    @staticmethod
    def calculate_position_size(
        portfolio_val: float,
        price: float,
        stop_loss: float,
        regime: str,
        active_sector_exposure_pct: float,
        expected_upside_pct: float
    ) -> Dict[str, Any]:
        """
        Calculates position sizes, enforcing strict risk rules and market regime allocation gates.
        Enforces Golden Rules 8, 11, 14, and 15.
        """
        # 1. Bear Market Cash Rule (Golden Rule 11/12)
        if regime == "BEAR MARKET":
            return {
                "status": "REJECT",
                "reason": "Bear market rules enforce 100% cash buffer. Survival mode active."
            }

        # 2. Risk-Reward & Upside Hard Gates (Golden Rule 8)
        risk_per_share = price - stop_loss
        if risk_per_share <= 0:
            return {"status": "REJECT", "reason": "Invalid stop loss level (must be below entry price)"}

        reward_per_share = (price * (expected_upside_pct / 100.0))
        risk_reward_ratio = reward_per_share / risk_per_share
        
        if risk_reward_ratio < 3.0:
            return {
                "status": "REJECT",
                "reason": f"Risk-Reward ratio is {risk_reward_ratio:.2f}:1. Minimum required is 1:3."
            }

        if expected_upside_pct < 15.0:
            return {
                "status": "REJECT",
                "reason": f"Expected move is {expected_upside_pct:.1f}%. Minimum required is 15-20%."
            }

        # 3. Sector Concentration Cap (Golden Rule 15)
        if active_sector_exposure_pct >= 35.0:
            return {
                "status": "REJECT",
                "reason": f"Sector concentration is {active_sector_exposure_pct:.1f}%. Maximum allowed is 35.0%."
            }

        # 4. Base Sizing Parameters by Regime (Golden Rule 11 & 14)
        regime_rules = {
            "BULL MARKET": {"max_pos_pct": 0.08, "portfolio_risk_limit": 0.015},
            "NEUTRAL MARKET": {"max_pos_pct": 0.05, "portfolio_risk_limit": 0.010},
            "DEFENSIVE MARKET": {"max_pos_pct": 0.025, "portfolio_risk_limit": 0.005}
        }
        
        rules = regime_rules.get(regime, regime_rules["DEFENSIVE MARKET"])
        
        # Sizing Calculation: allocation limited by portfolio risk capacity (volatility) or hard allocation cap
        allowed_risk_amt = portfolio_val * rules["portfolio_risk_limit"]
        suggested_shares = int(allowed_risk_amt // risk_per_share)
        
        max_investment = portfolio_val * rules["max_pos_pct"]
        suggested_investment = suggested_shares * price
        
        if suggested_investment > max_investment:
            suggested_shares = int(max_investment // price)
            suggested_investment = suggested_shares * price
            
        allocation_pct = (suggested_investment / portfolio_val) * 100.0
        
        return {
            "status": "APPROVED",
            "shares": suggested_shares,
            "investment_amt": round(suggested_investment, 2),
            "allocation_pct": round(allocation_pct, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "target_price": round(price + reward_per_share, 2),
            "portfolio_risk_pct": round((suggested_shares * risk_per_share / portfolio_val) * 100.0, 2)
        }
