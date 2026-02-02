from app.ai.features import FeatureEngineer
from app.ai.logic import BreakoutClassifier, RegimeClassifier, ReliabilityAdjuster

class AIEngine:
    def __init__(self):
        self.breakout_clf = BreakoutClassifier()
        self.regime_clf = RegimeClassifier()
        self.reliability_adj = ReliabilityAdjuster()

    def get_insights(self, df, base_confidence=None):
        """
        Runs all AI modules and returns an aggregated insight object.
        """
        if df.empty or len(df) < 50:
            return {
                "status": "error",
                "message": "Insufficient data for AI analysis (min 50 candles required)."
            }

        # 1. Feature Engineering
        features = FeatureEngineer.calculate_features(df)
        
        # 2. Module Inference
        breakout = self.breakout_clf.analyze(features)
        regime = self.regime_clf.analyze(features)
        
        # 3. Base Confidence Adjustment (if provided)
        reliability = None
        if base_confidence is not None:
            reliability = self.reliability_adj.adjust(base_confidence, features)

        # 4. Smart Alert Prioritization (Simplified Logic)
        priority = "LOW"
        if regime['market_regime'].startswith("TRENDING") and breakout['breakout_quality'] == "LIKELY_GENUINE":
            priority = "HIGH"
        elif breakout['breakout_quality'] != "LIKELY_FAKE":
            priority = "MEDIUM"

        return {
            "status": "success",
            "breakout": breakout,
            "regime": regime,
            "reliability": reliability,
            "priority": {
                "level": priority,
                "reason": f"Market is {regime['market_regime']} with {breakout['breakout_quality']} quality."
            },
            "noise_suppression": {
                "state": "LOW" if features.get('atr_expansion', 1.0) > 0.8 else "HIGH",
                "action": "NONE" if features.get('atr_expansion', 1.0) > 0.8 else "SUPPRESS_MINOR_ALERTS"
            }
        }
