import pandas as pd
import numpy as np
from typing import Dict, Any

class SmartMoneyEngine:
    @staticmethod
    def detect_smart_money_activity(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyzes volume, spread, and candle structures to identify institutional
        smart money activity: accumulation, distribution, absorption, and manipulation.
        """
        if df is None or df.empty or len(df) < 20:
            return {
                "state": "NEUTRAL",
                "narrative": "Insufficient data to evaluate smart money activity.",
                "candle_type": "NORMAL",
                "volatility_squeeze": False,
                "institutional_bias": "NEUTRAL"
            }
            
        df = df.copy()
        
        # Calculate key candle features
        df['body'] = (df['close'] - df['open']).abs()
        df['spread'] = df['high'] - df['low']
        df['vol_sma'] = df['volume'].rolling(20).mean()
        df['rvol'] = df['volume'] / df['vol_sma']
        
        # Latest bar features
        close = float(df['close'].iloc[-1])
        open_val = float(df['open'].iloc[-1])
        high = float(df['high'].iloc[-1])
        low = float(df['low'].iloc[-1])
        volume = float(df['volume'].iloc[-1])
        rvol = float(df['rvol'].iloc[-1])
        body = float(df['body'].iloc[-1])
        spread = float(df['spread'].iloc[-1])
        
        # Prev bars
        prev_lows = df['low'].iloc[-10:-1].tolist()
        prev_highs = df['high'].iloc[-10:-1].tolist()
        min_prev_low = min(prev_lows) if prev_lows else low
        max_prev_high = max(prev_highs) if prev_highs else high
        
        # Metrics for calculations
        range_percentile = (close - low) / (spread if spread > 0 else 1)
        body_percentile = body / (spread if spread > 0 else 1)
        
        # Squeeze logic for Breakout Loading
        atr_14 = (df['high'] - df['low']).rolling(14).mean()
        latest_atr = atr_14.iloc[-1]
        prev_atr_avg = atr_14.iloc[-6:-1].mean() if len(atr_14) > 6 else latest_atr
        volatility_squeeze = latest_atr < (prev_atr_avg * 0.85)
        
        # Flags
        is_high_volume = rvol > 1.5
        is_ultra_high_volume = rvol > 2.2
        
        state = "NEUTRAL"
        candle_type = "NORMAL"
        institutional_bias = "NEUTRAL"
        narrative = "Market activity is balanced with normal retail volume distribution."
        
        # 1. Spring (Bullish Manipulation)
        # Price dips below key recent low, but recovers to close in the upper 30% of the range.
        if low < min_prev_low and range_percentile >= 0.7 and body_percentile < 0.4 and is_high_volume:
            state = "BULLISH_MANIPULATION"
            candle_type = "SPRING"
            institutional_bias = "BULLISH"
            narrative = "Bullish Spring (stop-hunt) detected. Smart money swept retail stop losses below recent swing lows before aggressively bidding the price back up."
            
        # 2. Upthrust (Bearish Manipulation)
        # Price spikes above key recent high, but fails and closes in the lower 30% of the range.
        elif high > max_prev_high and range_percentile <= 0.3 and body_percentile < 0.4 and is_high_volume:
            state = "BEARISH_MANIPULATION"
            candle_type = "UPTHRUST"
            institutional_bias = "BEARISH"
            narrative = "Bearish Upthrust (trap) detected. Smart money engineered liquidity by pushing prices above recent highs to trap breakout buyers before dumping shares."
            
        # 3. Accumulation / Buying Support
        # High volume, but price close in upper part, narrow spread or bullish bar.
        elif is_high_volume and range_percentile >= 0.65 and close > open_val:
            state = "ACCUMULATION"
            candle_type = "SUPPORT_EFFORT"
            institutional_bias = "BULLISH"
            narrative = "Institutional accumulation active. Large block trades are absorbing floating supply at these levels, creating a strong price floor."
            
        # 4. Distribution / Selling Pressure
        # High volume, but price close in lower part, narrow spread or bearish bar.
        elif is_high_volume and range_percentile <= 0.35 and close < open_val:
            state = "DISTRIBUTION"
            candle_type = "SELLING_PRESSURE"
            institutional_bias = "BEARISH"
            narrative = "Institutional distribution detected. Heavy supply is hitting the market as smart money unloads positions into retail bids."
            
        # 5. Absorption (High Volume near Highs, but narrow spread)
        # S&R context would be useful, but can detect via volume effort vs result.
        elif is_ultra_high_volume and body_percentile < 0.25 and spread < latest_atr:
            state = "ABSORPTION"
            candle_type = "CHURN"
            if close > open_val:
                institutional_bias = "BULLISH"
                narrative = "Supply absorption in progress. Heavy institutional sell orders are being filled by aggressive buyers, preparing for a potential continuation breakout."
            else:
                institutional_bias = "BEARISH"
                narrative = "Demand absorption in progress. Heavy buying effort is being completely matched by institutional sell orders, risking a sharp exhaustion pullback."
                
        # 6. Breakout Loading (Volatility Squeeze + Rising volume)
        elif volatility_squeeze and rvol > 1.1:
            state = "BREAKOUT_LOADING"
            candle_type = "SQUEEZE"
            institutional_bias = "NEUTRAL"
            narrative = "Breakout loading detected. Volatility has contracted into a tight squeeze while volume is quietly accumulating, indicating a major explosive expansion is imminent."
            
        return {
            "state": state,
            "candle_type": candle_type,
            "institutional_bias": institutional_bias,
            "narrative": narrative,
            "rvol": round(rvol, 2),
            "volatility_squeeze": volatility_squeeze
        }
