class SREngine:
    @staticmethod
    def classify_levels(zones: list, cmp: float):
        """
        Classifies zones as Support (below CMP) or Resistance (above CMP).
        """
        supports = [z for z in zones if z['price'] < cmp]
        resistances = [z for z in zones if z['price'] > cmp]
        
        # Sort supports from high to low (nearest first)
        supports = sorted(supports, key=lambda x: x['price'], reverse=True)
        # Sort resistances from low to high (nearest first)
        resistances = sorted(resistances, key=lambda x: x['price'])
        
        return supports[:4], resistances[:4]

    @staticmethod
    def calculate_sr_levels(df, window=5):
        """
        Calculates SR levels based on short-term pivots.
        Limit to last 120 candles.
        """
        # Limit to last 120 candles
        df_slice = df.tail(120).copy()
        highs = df_slice['high'].values
        lows = df_slice['low'].values
        levels = []

        # Simple pivot detection
        for i in range(window, len(df_slice) - window):
            # Pivot High
            if all(highs[i] > highs[i-j] for j in range(1, window+1)) and \
               all(highs[i] > highs[i+j] for j in range(1, window+1)):
                levels.append({'price': float(highs[i]), 'type': 'RESISTANCE', 'strength': 1})
            
            # Pivot Low
            if all(lows[i] < lows[i-j] for j in range(1, window+1)) and \
               all(lows[i] < lows[i+j] for j in range(1, window+1)):
                levels.append({'price': float(lows[i]), 'type': 'SUPPORT', 'strength': 1})

        # Consolidate nearby levels (within 0.5% range)
        consolidated = []
        if not levels: return [], []

        levels.sort(key=lambda x: x['price'])
        current_group = [levels[0]]

        for i in range(1, len(levels)):
            if (levels[i]['price'] - current_group[-1]['price']) / current_group[-1]['price'] < 0.005:
                current_group.append(levels[i])
            else:
                avg_price = sum(l['price'] for l in current_group) / len(current_group)
                consolidated.append({'price': avg_price, 'strength': len(current_group)})
                current_group = [levels[i]]
        
        # Add last group
        if current_group:
            avg_price = sum(l['price'] for l in current_group) / len(current_group)
            consolidated.append({'price': avg_price, 'strength': len(current_group)})

        # Classify relative to CMP
        cmp = df['close'].iloc[-1]
        supports = [{'price': l['price'], 'visits': l['strength'], 'timeframe': 'SR'} for l in consolidated if l['price'] < cmp]
        resistances = [{'price': l['price'], 'visits': l['strength'], 'timeframe': 'SR'} for l in consolidated if l['price'] > cmp]

        return sorted(supports, key=lambda x: x['price'], reverse=True)[:5], sorted(resistances, key=lambda x: x['price'])[:5]

    @staticmethod
    def runSRStrategy(df, sector_state, supports, resistances):
        """
        Support / Resistance Strategy Engine — Pro Version
        Scoring system with 6 weighted factors + regime/liquidity/fake-break guards.
        Status: STRONG_ENTRY | ENTRY_READY | WATCHLIST | AVOID
        """
        from app.engine.zones import ZoneEngine
        from app.engine.insights import InsightEngine
        from app.engine.regime import MarketRegimeEngine

        cmp = float(df['close'].iloc[-1])
        vol_ratio = InsightEngine.get_volume_ratio(df)
        avg_vol = float(df['volume'].tail(20).mean())
        adx = InsightEngine.get_adx(df)
        retest = InsightEngine.detect_retest(df, supports + resistances)
        atr = ZoneEngine.calculate_atr(df).iloc[-1]
        regime = MarketRegimeEngine.detect_regime(df)

        nearest_res = resistances[0]['price'] if resistances else None
        nearest_sup = supports[0]['price'] if supports else None

        breakout = cmp > nearest_res if nearest_res else False

        # --- SIDE & DIRECTIONAL BIAS ---
        # Rule: Side depends on whether we are bouncing off Support or breaking Resistance
        dist_to_sup = (cmp - nearest_sup) / nearest_sup if nearest_sup else 1.0
        dist_to_res = (nearest_res - cmp) / cmp if nearest_res else 1.0
        
        # Default Side
        side = "LONG"
        if dist_to_res < dist_to_sup and not breakout:
            # If price is closer to Resistance and not breaking out, bias might be SHORT (rejection)
            # but we only flip to SHORT if the trend is weak or bearish
            if regime in ["RANGE", "WEAK_TREND"] or InsightEngine.get_ema_bias(df) == "Caution":
                side = "SHORT"

        # --- STOP & TARGET (Dynamic) ---
        if side == "LONG":
            stop_loss = nearest_sup - (atr * 0.5) if nearest_sup else cmp * 0.98
            if breakout and len(resistances) > 1:
                target = resistances[1]['price']
            elif nearest_res:
                target = nearest_res
            else:
                target = cmp * 1.05
        else: # SHORT
            stop_loss = nearest_res + (atr * 0.5) if nearest_res else cmp * 1.02
            if nearest_sup:
                target = nearest_sup
            else:
                target = cmp * 0.95

        rr = (abs(target - cmp)) / (abs(cmp - stop_loss)) if abs(cmp - stop_loss) > 0 else 0

        # Fake Breakout Detector
        false_break = (
            breakout and side == "LONG" and
            len(df) >= 2 and
            df['close'].iloc[-1] < df['high'].iloc[-2]
        )

        # -------------------------
        # 🎯 SCORING SYSTEM
        # -------------------------
        score = 0

        # Breakout / Momentum
        if breakout and side == "LONG":
            score += 20 if regime != "RANGE" else 10
        
        # Proximity / Bounce Bonus (New)
        if side == "LONG" and dist_to_sup <= 0.015:
            score += 15 # Bounce setup
        elif side == "SHORT" and dist_to_res <= 0.015:
            score += 15 # Resistance rejection setup

        # Trend Bonus (New)
        if regime in ["STRONG_UPTREND", "UPTREND"] and side == "LONG":
            score += 15
        elif regime in ["STRONG_DOWNTREND", "DOWNTREND"] and side == "SHORT":
            score += 15

        # Retest
        if retest:
            score += 10

        # Volume
        if vol_ratio >= 1.5:
            score += 10
        elif vol_ratio >= 1.2: # Lowered threshold for normal markets
            score += 5

        # Trend Strength (ADX)
        if adx >= 25:
            score += 10
        elif adx >= 18:
            score += 5

        # Risk Reward
        if rr >= 1.5:
            score += 15
        elif rr >= 1.2:
            score += 10

        # Sector Alignment
        if sector_state == "LEADING" and side == "LONG":
            score += 10
        elif sector_state == "LAGGING" and side == "SHORT":
            score += 10

        confidence = min(score, 100)

        # Post-score adjustments
        if false_break:
            confidence = max(0, confidence - 20)

        # Liquidity Filter
        if avg_vol < 200_000:
            confidence = min(confidence, 55)

        # -------------------------
        # STATUS LOGIC (Relaxed Thresholds)
        # -------------------------
        if confidence >= 75:
            status = "STRONG_ENTRY"
        elif confidence >= 60:
            status = "ENTRY_READY"
        else:
            status = "WATCHLIST"

        bias = "BULLISH" if (breakout or regime == "STRONG_UPTREND") else "BEARISH" if regime == "STRONG_DOWNTREND" else "RANGE"
        grade = MarketRegimeEngine.get_grade(confidence)

        return {
            "bias": bias,
            "side": side,
            "entryStatus": status,
            "stopLoss": round(stop_loss, 2),
            "target": round(target, 2),
            "riskReward": round(rr, 2),
            "confidence": confidence,
            "grade": grade,
            "additionalMetrics": {
                "adx": round(adx, 2),
                "volRatio": round(vol_ratio, 2),
                "breakout": breakout,
                "retest": retest,
                "regime": regime,
                "falseBreak": false_break
            }
        }
