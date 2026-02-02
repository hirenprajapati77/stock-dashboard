from app.ai.registry import ModelRegistry

class BreakoutClassifier:
    def __init__(self):
        self.model = ModelRegistry.load_model("breakout_rf")

    def analyze(self, features: dict):
        """
        Determines if a breakout is Likely Genuine or Fake.
        """
        # 1. Heuristic Fallback (Safety Net)
        # If Volume is low (< 1.5x avg) and ATR expansion is weak (< 1.0x), likely fake.
        
        vol_ratio = features.get('vol_ratio', 1.0)
        atr_expansion = features.get('atr_expansion', 1.0)
        
        # Default State
        result = {
            "breakout_quality": "UNCLEAR",
            "reason": "Insufficient data to classify breakout.",
            "confidence_bucket": "NEUTRAL"
        }

        # Heuristic Logic (Explainable)
        if vol_ratio < 1.0:
            result = {
                "breakout_quality": "LIKELY_FAKE",
                "reason": f"Breakout volume is weak ({vol_ratio}x avg). Genuine breakouts usually require >1.5x volume.",
                "confidence_bucket": "LOW"
            }
        elif vol_ratio > 2.0 and atr_expansion > 1.5:
             result = {
                "breakout_quality": "LIKELY_GENUINE",
                "reason": f"Strong volume ({vol_ratio}x) and wide range ({atr_expansion}x ATR) suggest conviction.",
                "confidence_bucket": "HIGH"
            }
        
        # ML Logic (Assistive Upgrade)
        if self.model:
            try:
                # Prepare features in the same order as training: vol_ratio, atr_expansion, dist_from_ema
                X = [[vol_ratio, atr_expansion, features.get('dist_from_ema', 0.0)]]
                prediction = self.model.predict(X)[0]
                prob = self.model.predict_proba(X)[0][prediction]
                
                # If ML is confident, we can refine the reason
                if prob > 0.6:
                    ml_quality = "LIKELY_GENUINE" if prediction == 1 else "LIKELY_FAKE"
                    # We blend ML with heuristics for safety
                    if ml_quality != result['breakout_quality']:
                        result['breakout_quality'] = ml_quality
                        result['reason'] = f"AI Analysis: {ml_quality.replace('_', ' ')} based on {int(prob*100)}% model confidence."
                        result['confidence_bucket'] = "HIGH" if prob > 0.8 else "MEDIUM"
            except Exception as e:
                print(f"ML prediction error: {e}")

        return result
