import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

class FibonacciEngine:
    @staticmethod
    def calculate_fib_levels(df: pd.DataFrame, lookback: int = 100) -> Dict[str, List[Dict]]:
        """
        Identifies the absolute High and Low in the recent lookback and calculates Fibonacci levels.
        Works across all timeframes as it operates on the provided DataFrame.
        """
        if df is None or df.empty:
            return {"supports": [], "resistances": []}

        # Use last 100 candles (or less if not available)
        df_slice = df.tail(lookback).copy()
        
        # Identify absolute High and Low in this range
        high_idx = df_slice['high'].idxmax()
        low_idx = df_slice['low'].idxmin()
        
        high_val = float(df_slice['high'].max())
        low_val = float(df_slice['low'].min())
        
        # Determine trend based on order of High and Low
        is_uptrend = high_idx > low_idx
        
        # Define Fibonacci ratios
        ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        
        diff = high_val - low_val
        levels = []
        
        # Calculate pricing for each level
        for r in ratios:
            if is_uptrend:
                # In uptrend, retracement is from High down towards Low
                price = high_val - (r * diff)
            else:
                # In downtrend, retracement is from Low up towards High
                price = low_val + (r * diff)
                
            levels.append({
                'price': round(price, 2),
                'ratio': r,
                'label': f"FIB {int(r*100)}%",
                'type': 'FIBONACCI',
                'strength': 1 if r in [0.5, 0.618] else 0.5 # Golden Pocket gets more strength
            })

        # Classify as supports or resistances based on current CMP
        cmp = float(df['close'].iloc[-1])
        supports = [l for l in levels if l['price'] < cmp]
        # Sort supports newest/nearest first (highest price first)
        supports = sorted(supports, key=lambda x: x['price'], reverse=True)
        
        resistances = [l for l in levels if l['price'] > cmp]
        # Sort resistances nearest first (lowest price first)
        resistances = sorted(resistances, key=lambda x: x['price'])
        
        return {
            "supports": supports, 
            "resistances": resistances,
            "meta": {
                "high": high_val,
                "low": low_val,
                "is_uptrend": is_uptrend,
                "range_diff": round(diff, 2)
            }
        }

    @staticmethod
    def runFibonacciStrategy(df, sector_state, fib_data):
        """
        Fibonacci Retracement Strategy Engine
        Focuses on "Golden Pocket" (50-61.8%) and trend continuity.
        """
        from app.engine.insights import InsightEngine
        from app.engine.regime import MarketRegimeEngine
        
        if not fib_data or not fib_data.get('supports') and not fib_data.get('resistances'):
            return {"bias": "NEUTRAL", "entryStatus": "AVOID", "confidence": 0}

        cmp = float(df['close'].iloc[-1])
        adx = InsightEngine.get_adx(df)
        vol_ratio = InsightEngine.get_volume_ratio(df)
        
        meta = fib_data.get('meta', {})
        is_uptrend = meta.get('is_uptrend', True)
        
        # Calculate retracement depth %
        high = meta.get('high', cmp)
        low = meta.get('low', cmp)
        diff = high - low
        
        if diff == 0:
            return {"bias": "NEUTRAL", "entryStatus": "AVOID", "confidence": 0}
            
        retracement_pct = (high - cmp) / diff if is_uptrend else (cmp - low) / diff
        retracement_pct = round(retracement_pct * 100, 1)

        # 🎯 SCORING SYSTEM
        score = 0
        reasons = []

        # 1. Golden Pocket Logic (50% - 61.8%)
        if 48 <= retracement_pct <= 65:
            score += 40
            reasons.append("GOLDEN_POCKET")
        elif 20 <= retracement_pct <= 40:
            score += 25
            reasons.append("SHALLOW_RETRACTION")
        elif retracement_pct > 75:
            score += 15
            reasons.append("DEEP_VALUE")

        # 2. Trend Strength
        if adx > 25:
            score += 20
        elif adx > 18:
            score += 10

        # 3. Volume Support
        if vol_ratio > 1.5:
            score += 20
        elif vol_ratio > 1.2:
            score += 10

        # 4. Sector Alignment
        if sector_state == "LEADING":
            score += 20
        elif sector_state == "IMPROVING":
            score += 10

        confidence = min(score, 100)
        
        # STATUS Mapping
        if confidence >= 80:
            status = "STRONG_ENTRY"
        elif confidence >= 60:
            status = "ENTRY_READY"
        elif confidence >= 40:
            status = "WATCHLIST"
        else:
            status = "AVOID"

        # Determine Target and Stop Loss
        # Stop Loss usually below 78.6% or recent low
        # Target usually 0% (High) or 1.272 ext (not implemented here yet)
        if is_uptrend:
            # SL below 78.6%
            sl_price = high - (0.85 * diff)
            target_price = high  # First target is back to High
        else:
            sl_price = low + (0.85 * diff)
            target_price = low

        rr = (abs(target_price - cmp)) / (abs(cmp - sl_price)) if abs(cmp - sl_price) > 0 else 0

        return {
            "bias": "BULLISH" if is_uptrend else "BEARISH",
            "side": "LONG" if is_uptrend else "SHORT",
            "entryStatus": status,
            "confidence": confidence,
            "stopLoss": round(sl_price, 2),
            "target": round(target_price, 2),
            "riskReward": round(rr, 2),
            "grade": MarketRegimeEngine.get_grade(confidence),
            "additionalMetrics": {
                "retracementDepth": f"{retracement_pct}%",
                "adx": round(adx, 2),
                "volRatio": round(vol_ratio, 2),
                "goldenPocket": "GOLDEN_POCKET" in reasons,
                "is_uptrend": is_uptrend
            }
        }
