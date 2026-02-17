class ReliabilityAdjuster:
    def adjust(self, base_confidence: int, features: dict):
        """
        Adjusts the confidence score based on recent context and momentum alignment.
        """
        adjustment = 0
        reasons = []
        
        ema_dist = features.get('dist_from_ema', 0.0)
        rsi = features.get('rsi', 50.0)
        adx = features.get('adx', 20.0)
        vol_ratio = features.get('vol_ratio', 1.0)
        atr_expansion = features.get('atr_expansion', 1.0)
        
        # 1. Momentum Consistency
        # Price and RSI in same direction (Confirmation)
        if (ema_dist > 0 and rsi > 55) or (ema_dist < 0 and rsi < 45):
            adjustment += 2
            reasons.append("Momentum alignment (+2)")
        elif (ema_dist > 0 and rsi < 45) or (ema_dist < 0 and rsi > 55):
            adjustment -= 3
            reasons.append("Momentum divergence (-3)")
            
        # 2. Trend Stability (ADX)
        if adx > 30:
            adjustment += 2
            reasons.append("Strong trend stability (+2)")
        elif adx < 15:
            adjustment -= 2
            reasons.append("Choppy/Weak trend (-2)")

        # 3. Volume Confirmation
        if vol_ratio > 1.8:
            adjustment += 2
            reasons.append("Volume confirmation (+2)")
            
        # 4. Volatility Penalty
        if atr_expansion > 2.8:
            adjustment -= 3
            reasons.append("Volatility risk (-3)")
            
        # Clamp adjustment to +/- 8 for more impact
        final_adjustment = max(-8, min(8, adjustment))
        
        return {
            "base_confidence": int(base_confidence),
            "ai_adjustment": int(final_adjustment),
            "final_confidence": int(max(0, min(100, base_confidence + final_adjustment))),
            "reason": str("; ".join(reasons) if reasons else "No major AI adjustments.")
        }
