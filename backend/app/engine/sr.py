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

        # --- STOP & TARGET ---
        if nearest_sup:
            stop_loss = nearest_sup - (atr * 0.5)
        else:
            stop_loss = cmp * 0.98

        if breakout and len(resistances) > 1:
            target = resistances[1]['price']
        elif nearest_res:
            target = nearest_res
        else:
            target = cmp * 1.05

        rr = (target - cmp) / (cmp - stop_loss) if (cmp - stop_loss) > 0 else 0

        # Fake Breakout Detector (kept from previous version)
        false_break = (
            breakout and
            len(df) >= 2 and
            df['close'].iloc[-1] < df['high'].iloc[-2]
        )

        # -------------------------
        # 🎯 SCORING SYSTEM
        # -------------------------
        score = 0

        # Breakout
        if breakout and regime != "RANGE":
            score += 20

        # Retest
        if retest:
            score += 15

        # Volume
        if vol_ratio >= 2:
            score += 15
        elif vol_ratio >= 1.5:
            score += 10

        # Trend Strength
        if adx >= 25:
            score += 15
        elif adx >= 18:
            score += 10

        # Risk Reward
        if rr >= 2:
            score += 15
        elif rr >= 1.5:
            score += 10

        # Sector Alignment
        if sector_state == "LEADING":
            score += 15
        elif sector_state == "IMPROVING":
            score += 10

        confidence = min(score, 100)

        # Post-score adjustments
        if false_break:
            confidence = max(0, confidence - 20)

        # Liquidity Filter
        if avg_vol < 200_000:
            confidence = min(confidence, 55)

        # -------------------------
        # STATUS LOGIC
        # -------------------------
        if confidence >= 80:
            status = "STRONG_ENTRY"
        elif confidence >= 65:
            status = "ENTRY_READY"
        elif confidence >= 50:
            status = "WATCHLIST"
        else:
            status = "AVOID"

        bias = "BULLISH" if breakout else "RANGE"
        grade = MarketRegimeEngine.get_grade(confidence)

        return {
            "bias": bias,
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
