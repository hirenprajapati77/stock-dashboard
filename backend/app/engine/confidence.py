import numpy as np
import pandas as pd

class ConfidenceEngine:
    @staticmethod
    def calculate_score(zone: dict, tf: str, atr: float, last_date=None, avg_market_volume=None):
        """
        Calculates a 0-100 score based on structural significance.
        last_date: datetime object of the most recent candle in the dataset.
        avg_market_volume: baseline average volume for the timeframe.
        """
        score = 0
        
        # 1. Touch Strength (Max 30)
        touches = zone.get('touches', 1)
        if touches == 1: score += 10
        elif touches == 2: score += 20
        elif touches >= 3: score += 30
        
        # 2. Timeframe Strength (Max 20)
        tf_scores = {
            '1D': 10,
            '1W': 15,
            '1M': 20,
            '3M': 20
        }
        score += tf_scores.get(tf, 5)
        
        # 3. Recency (Max 15)
        if last_date:
            try:
                zone_date = pd.to_datetime(zone['last_touched'])
                delta_days = (last_date - zone_date).days
                
                # Dynamic threshold based on TF (approx)
                threshold_days = 90 if tf == '1D' else 365
                
                if delta_days <= threshold_days:
                    score += 15
                elif delta_days <= threshold_days * 2:
                    score += 5
            except:
                pass # Fail silently if date parsing issues
        
        # 4. Volume Confirmation (Max 15)
        zone_volume = zone.get('avg_volume', 0)
        if avg_market_volume and avg_market_volume > 0:
            if zone_volume > avg_market_volume * 1.5:
                score += 15
            elif zone_volume > avg_market_volume * 1.2:
                score += 10
            elif zone_volume > avg_market_volume:
                score += 5
        elif zone_volume > 0:
            score += 5 # Minimal score if no market baseline is available
        
        # 5. Confluence / Psychology (Max 20) - Bonus
        price = zone['price']
        if price >= 10:
            # Exact round numbers
            if price % 1000 == 0: score += 20
            elif price % 500 == 0: score += 15
            elif price % 100 == 0: score += 10
            elif price % 50 == 0: score += 5
            else:
                # Proximity checks (within 0.2%)
                if abs(price - round(price, -2)) <= price * 0.002: score += 8
                elif abs(price - round(price, -1)) <= price * 0.002: score += 3
        
        return float(min(score, 100))

    @staticmethod
    def get_label(score: float):
        if score < 30: return "Weak"
        if score < 60: return "Moderate"
        if score < 80: return "Strong"
        return "Very Strong"
