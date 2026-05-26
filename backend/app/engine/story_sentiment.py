# backend/app/engine/story_sentiment.py
from typing import Dict, Any

class StorySentimentEngine:
    @staticmethod
    def calculate_story_score(
        policy_tailwind: float,  # 0 to 100
        macro_alignment: float,  # 0 to 100
        sentiment_score: float,  # 0 to 100
        theme_momentum: float    # 0 to 100
    ) -> Dict[str, Any]:
        """
        Enforces Golden Rules 7 & 13: Narrative Story-Based Investing with Exit Discipline.
        When story score drops below 50 (Dead Story), it triggers an automated liquidation exit signal.
        """
        # Weighted Score Formulation
        score = (
            (policy_tailwind * 0.30) +
            (theme_momentum * 0.30) +
            (macro_alignment * 0.20) +
            (sentiment_score * 0.20)
        )
        score = float(max(min(score, 100.0), 0.0))

        # Classification & Actions
        if score >= 80.0:
            status = "Strong Story"
            action = "HOLD / ADD ON BREAKOUTS"
            reason = "High institutional and policy alignment. Trend persistence is highly probable."
        elif score >= 50.0:
            status = "Fading Story"
            action = "CAUTION / TIGHTEN STOPS"
            reason = "Story tailwinds are weakening. Reduce new exposures, raise existing stop losses."
        else:
            status = "Dead Story"
            action = "LIQUIDATE POSITION IMMEDIATELY"
            reason = "Narrative is complete. Golden Rule 13 enforces automated exit on dead stories."

        return {
            "score": round(score, 1),
            "status": status,
            "action": action,
            "reason": reason
        }
