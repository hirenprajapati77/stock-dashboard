import pandas as pd
import numpy as np

class SwingEngine:
    @staticmethod
    def get_swings(df: pd.DataFrame, window: int = 2):
        """
        Detects Swing Highs and Swing Lows using an N-candle window.
        A high is a swing high if it's highest in window before and after.
        """
        highs = df['high'].values
        lows = df['low'].values
        
        swing_highs = []
        swing_lows = []
        
        for i in range(window, len(df) - window):
            # Check for Swing High
            is_high = True
            for j in range(1, window + 1):
                if highs[i] <= highs[i-j] or highs[i] <= highs[i+j]:
                    is_high = False
                    break
            if (is_high):
                swing_highs.append({
                    'index': int(i), 
                    'price': float(highs[i]), 
                    'time': str(df.index[i]),
                    'volume': int(df['volume'].iloc[i])
                })
                
            # Check for Swing Low
            is_low = True
            for j in range(1, window + 1):
                if lows[i] >= lows[i-j] or lows[i] >= lows[i+j]:
                    is_low = False
                    break
            if is_low:
                swing_lows.append({
                    'index': int(i), 
                    'price': float(lows[i]), 
                    'time': str(df.index[i]),
                    'volume': int(df['volume'].iloc[i])
                })
                
        return swing_highs, swing_lows

    @staticmethod
    def calculate_swing_levels(df, tf='1D'):
        """
        Calculates Major Swing Levels (Structural).
        Adapts window size based on timeframe so 1W/1M still produce levels.
        """
        # Adapt pivot window to timeframe — higher TFs have fewer bars
        window_map = {
            '5m': 10, '10m': 10, '15m': 10, '30m': 8, '45m': 6, '75m': 5,
            '1H': 5, '2H': 4, '3H': 4, '4H': 4,
            '1D': 5, '1W': 3, '1M': 2
        }
        window = window_map.get(tf, 5)

        # Limit to last 200 candles for structure
        df_slice = df.tail(200).copy()

        # Need at least 2*window+1 candles to detect any pivot
        if len(df_slice) < (2 * window + 1):
            window = max(1, len(df_slice) // 4)

        sh, sl = SwingEngine.get_swings(df_slice, window=window)

        all_pivots = sh + sl
        levels = []

        for p in all_pivots:
            levels.append({'price': p['price'], 'type': 'SWING_PIVOT'})

        if not levels: return [], []

        levels.sort(key=lambda x: x['price'])
        consolidated = []
        current_group = [levels[0]]

        # Use wider consolidation for higher TFs (2% for weekly/monthly, 1% for intraday)
        consolidation_pct = 0.02 if tf in ('1W', '1M') else 0.015 if tf in ('1D', '4H', '3H', '2H', '1H') else 0.01

        for i in range(1, len(levels)):
            gap = (levels[i]['price'] - current_group[-1]['price']) / current_group[-1]['price']
            if gap < consolidation_pct:
                current_group.append(levels[i])
            else:
                avg_price = sum(l['price'] for l in current_group) / len(current_group)
                consolidated.append({'price': avg_price})
                current_group = [levels[i]]

        if current_group:
            avg_price = sum(l['price'] for l in current_group) / len(current_group)
            consolidated.append({'price': avg_price})

        cmp = df['close'].iloc[-1]
        supports = [{'price': l['price'], 'visits': 1, 'timeframe': tf} for l in consolidated if l['price'] < cmp]
        resistances = [{'price': l['price'], 'visits': 1, 'timeframe': tf} for l in consolidated if l['price'] > cmp]

        return sorted(supports, key=lambda x: x['price'], reverse=True)[:5], sorted(resistances, key=lambda x: x['price'])[:5]

    @staticmethod
    def runSwingStrategy(df, sector_state, htf_trend="NEUTRAL", supports=[], resistances=[]):
        """
        Swing Strategy Engine — Pro Version
        Regime-aware scoring with liquidity filter and institutional grade.
        Status: STRONG_ENTRY | ENTRY_READY | WATCHLIST | AVOID
        """
        from app.engine.insights import InsightEngine
        from app.engine.zones import ZoneEngine
        from app.engine.regime import MarketRegimeEngine

        cmp = float(df['close'].iloc[-1])
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        atr = ZoneEngine.calculate_atr(df).iloc[-1]
        avg_vol = float(df['volume'].tail(20).mean())

        structure = InsightEngine.get_structure_bias(df)
        adx = InsightEngine.get_adx(df)
        vol_ratio = float(df['volume'].iloc[-1] / df['volume'].tail(20).mean())
        regime = MarketRegimeEngine.detect_regime(df)

        # -------------------------
        # Support Logic
        # -------------------------
        nearest_support_price = supports[0]['price'] if supports else cmp * 0.95

        stop_loss = nearest_support_price - (atr * 0.5)
        # 2R default swing target
        target = cmp + (cmp - stop_loss) * 2
        rr = (target - cmp) / (cmp - stop_loss) if (cmp - stop_loss) > 0 else 0

        ema_aligned = cmp > ema20 and cmp > ema50
        htf_aligned = htf_trend == "BULLISH"

        pullback_quality = abs(cmp - nearest_support_price) / nearest_support_price <= 0.015

        # -------------------------
        # 🎯 SCORING MODEL
        # -------------------------
        score = 0

        if structure == "BULLISH":
            score += 20
        elif structure == "NEUTRAL" and adx >= 20:
            score += 10 # Trend continuation candidate

        if ema_aligned:
            score += 15

        if htf_aligned:
            score += 10

        if pullback_quality:
            score += 15

        if adx >= 25:
            score += 10
        elif adx >= 18:
            score += 5

        if vol_ratio >= 1.2: # Relaxed from 1.5
            score += 10

        if rr >= 1.5: # Relaxed from 2
            score += 10

        if sector_state == "LEADING":
            score += 10
        elif sector_state == "IMPROVING":
            score += 5

        # Regime penalty (Reduced and made conditional)
        if regime in ["RANGE", "WEAK_TREND"]:
            if adx < 20:
                score -= 5 # Only penalize if truly sideways
            else:
                score += 5 # Counter-trend or mean reversion possible
        
        # Pullback Bonus (Specific for Swing)
        if pullback_quality and structure == "BULLISH":
            score += 10 # Extra weight for swing pullback setups

        # Trend Bonus (New)
        if regime in ["STRONG_UPTREND", "UPTREND"] and structure == "BULLISH":
            score += 10

        confidence = min(max(score, 0), 100)

        # Liquidity Filter
        if avg_vol < 200_000:
            confidence = min(confidence, 55)

        # -------------------------
        # STATUS LOGIC (Further Relaxed)
        # -------------------------
        if confidence >= 70:
            status = "STRONG_ENTRY"
        elif confidence >= 55:
            status = "ENTRY_READY"
        else:
            status = "WATCHLIST"

        grade = MarketRegimeEngine.get_grade(confidence)

        return {
            "bias": structure,
            "side": "LONG" if structure == "BULLISH" else "SHORT",
            "entryStatus": status,
            "stopLoss": round(stop_loss, 2),
            "target": round(target, 2),
            "riskReward": round(rr, 2),
            "confidence": confidence,
            "grade": grade,
            "additionalMetrics": {
                "structure": structure,
                "emaAlignment": ema_aligned,
                "htfTrend": htf_trend,
                "pullback": pullback_quality,
                "regime": regime,
                "adx": round(adx, 2),
                "volRatio": round(vol_ratio, 2)
            }
        }
