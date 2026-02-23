import numpy as np
import pandas as pd

class ZoneEngine:
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14):
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(window=period).mean()

    @staticmethod
    def cluster_swings(swings: list, atr: float, factor: float = 0.5):
        """
        Clusters nearby swing prices into zones based on ATR.
        """
        if not swings:
            return []
            
        # Sort swings by price
        sorted_swings = sorted(swings, key=lambda x: x['price'])
        zones = []
        
        if not sorted_swings:
            return []
            
        current_zone = [sorted_swings[0]]
        
        for i in range(1, len(sorted_swings)):
            price_diff = sorted_swings[i]['price'] - current_zone[-1]['price']
            
            # If price difference is within ATR-based threshold, add to current zone
            if price_diff <= (atr * factor):
                current_zone.append(sorted_swings[i])
            else:
                # Calculate zone properties
                zone_prices = [s['price'] for s in current_zone]
                zones.append({
                    'price': float(np.mean(zone_prices)),
                    'price_low': float(min(zone_prices)),
                    'price_high': float(max(zone_prices)),
                    'touches': len(current_zone),
                    'last_touched': str(max([s['time'] for s in current_zone])),
                    'avg_volume': float(np.mean([s['volume'] for s in current_zone if 'volume' in s]))
                })
                current_zone = [sorted_swings[i]]
                
        # Handle last zone
        zone_prices = [s['price'] for s in current_zone]
        zones.append({
            'price': float(np.mean(zone_prices)),
            'price_low': float(min(zone_prices)),
            'price_high': float(max(zone_prices)),
            'touches': len(current_zone),
            'last_touched': str(max([s['time'] for s in current_zone])),
            'avg_volume': float(np.mean([s['volume'] for s in current_zone if 'volume' in s]))
        })
        
        return zones

    @staticmethod
    def calculate_demand_supply_zones(df):
        """
        Calculates Demand/Supply zones based on Base-Rally-Drop logic.
        Limit to last 200 candles.
        Base: Min 2 candles, body < 0.6 ATR
        Impulse: Body > 1.5 ATR, Break, Close near extreme
        Merge overlapping zones (>50%)
        """
        df_slice = df.tail(200).copy()
        if df_slice.empty: return []

        atr_series = ZoneEngine.calculate_atr(df_slice)
        zones = []
        
        closes = df_slice['close'].values
        opens = df_slice['open'].values
        highs = df_slice['high'].values
        lows = df_slice['low'].values
        
        # Iterate to find Impulse (Leg-Out)
        # Check from index 3 to ensure space for Base (min 2 candles)
        for i in range(3, len(df_slice)):
            current_atr = atr_series.iloc[i]
            body_size = abs(closes[i] - opens[i])
            
            # 1. Impulse Check
            is_impulse = body_size > 1.5 * current_atr
            
            # Volume Confirmation: > 1.5x Avg Volume (20 period)
            avg_vol = df_slice['volume'].iloc[i-20:i].mean() if i > 20 else df_slice['volume'].iloc[:i].mean()
            vol_valid = df_slice['volume'].iloc[i] > 1.5 * avg_vol
            
            if not is_impulse or not vol_valid: continue

            is_bullish = closes[i] > opens[i]
            
            # Check for strong close (upper/lower 20%)
            range_len = highs[i] - lows[i]
            if range_len == 0: continue
            
            strong_close = False
            if is_bullish:
                strong_close = (highs[i] - closes[i]) <= (0.2 * range_len)
                # Must break previous high
                break_prev = closes[i] > highs[i-1]
            else:
                strong_close = (closes[i] - lows[i]) <= (0.2 * range_len)
                # Must break previous low
                break_prev = closes[i] < lows[i-1]
                
            if not (strong_close and break_prev): continue

            # 2. Base Check (Previous 1-3 candles)
            # We strictly require at least 2 small candles < 0.6 ATR immediately prior
            base_candles = []
            valid_base = False
            
            # Check i-1 and i-2
            c1_body = abs(closes[i-1] - opens[i-1])
            c2_body = abs(closes[i-2] - opens[i-2])
            atr_prev = atr_series.iloc[i-1] # Approx ATR for base check
            
            if c1_body < 0.6 * atr_prev and c2_body < 0.6 * atr_prev:
                # Valid 2-candle base
                base_start = i-2
                base_end = i-1
                valid_base = True
                
                # Check optional i-3
                c3_body = abs(closes[i-3] - opens[i-3])
                if c3_body < 0.6 * atr_prev:
                    base_start = i-3
            
            if not valid_base: continue

            # 3. Construct Zone
            # Demand: Base Low to Base High (or highest body of base)
            # Supply: Base Low to Base High
            # Actually, standard is:
            # Demand: Proximal = Highest Body in Base, Distal = Lowest Low in Base
            # Supply: Proximal = Lowest Body in Base, Distal = Highest High in Base
            
            base_highs = highs[base_start:base_end+1]
            base_lows = lows[base_start:base_end+1]
            base_closes = closes[base_start:base_end+1]
            base_opens = opens[base_start:base_end+1]
            
            if is_bullish:
                # Demand
                distal = min(base_lows)
                # Proximal is highest body top (max(open, close))
                proximal = max([max(o, c) for o, c in zip(base_opens, base_closes)])
                z_type = 'DEMAND'
            else:
                # Supply
                distal = max(base_highs)
                # Proximal is lowest body bottom (min(open, close))
                proximal = min([min(o, c) for o, c in zip(base_opens, base_closes)])
                z_type = 'SUPPLY'
                
            # Valid zone must have width
            if distal == proximal: continue
            
            zones.append({
                'price_high': max(distal, proximal),
                'price_low': min(distal, proximal),
                'type': z_type,
                'strength': 1,
                'creation_idx': i,
                'touched': 0
            })

        # 4. Merge overlapping zones
        # Sort by price to find overlaps
        if not zones: return []
        
        # Separate demand and supply for merging
        demands = sorted([z for z in zones if z['type'] == 'DEMAND'], key=lambda x: x['price_low'])
        supplies = sorted([z for z in zones if z['type'] == 'SUPPLY'], key=lambda x: x['price_low'])
        
        merged_demands = []
        if demands:
            curr = demands[0]
            for next_z in demands[1:]:
                # Check overlap
                # O = max(0, min(curr_high, next_high) - max(curr_low, next_low))
                overlap = max(0, min(curr['price_high'], next_z['price_high']) - max(curr['price_low'], next_z['price_low']))
                range1 = curr['price_high'] - curr['price_low']
                range2 = next_z['price_high'] - next_z['price_low']
                min_range = min(range1, range2)
                
                if min_range > 0 and (overlap / min_range) > 0.5:
                    # Merge
                    curr['price_high'] = max(curr['price_high'], next_z['price_high'])
                    curr['price_low'] = min(curr['price_low'], next_z['price_low'])
                    curr['strength'] += 1
                else:
                    merged_demands.append(curr)
                    curr = next_z
            merged_demands.append(curr)
            
        merged_supplies = []
        if supplies:
            curr = supplies[0]
            for next_z in supplies[1:]:
                overlap = max(0, min(curr['price_high'], next_z['price_high']) - max(curr['price_low'], next_z['price_low']))
                range1 = curr['price_high'] - curr['price_low']
                range2 = next_z['price_high'] - next_z['price_low']
                min_range = min(range1, range2)
                
                if min_range > 0 and (overlap / min_range) > 0.5:
                    curr['price_high'] = max(curr['price_high'], next_z['price_high'])
                    curr['price_low'] = min(curr['price_low'], next_z['price_low'])
                    curr['strength'] += 1
                else:
                    merged_supplies.append(curr)
                    curr = next_z
            merged_supplies.append(curr)

        final_zones = merged_demands + merged_supplies
        
        # 5. Process Invalidation & Freshness (Scan Forward)
        # We need to map zones back to the full timeframe or scan from creation index
        # For simplicity in this slice, we scan from creation_idx to end
        active_zones = []
        
        for z in final_zones:
            # Creation index in the slice
            # Note: merged zones might have multiple creation indices, we take the latest or approx
            c_idx = z.get('creation_idx', 0)
            
            is_valid = True
            touches = 0
            
            # Scan price action after creation
            for i in range(c_idx + 1, len(df_slice)):
                row = df_slice.iloc[i]
                
                if z['type'] == 'DEMAND':
                    # Violation: Close below distal (low)
                    if row['close'] < z['price_low']:
                        is_valid = False
                        break
                    # Touch: Low touches proximal (high)
                    if row['low'] <= z['price_high']:
                        touches += 1
                        
                elif z['type'] == 'SUPPLY':
                    # Violation: Close above distal (high)
                    if row['close'] > z['price_high']:
                        is_valid = False
                        break
                    # Touch: High touches proximal (low)
                    if row['high'] >= z['price_low']:
                        touches += 1
            
            z['touches'] = touches
            z['last_touched'] = str(df_slice.index[-1]) # Approximate for now
            
            # Filter: Exclude if invalid or too many touches
            if is_valid and touches < 3:
                # 6. Time Decay
                # If older than 150 candles, reduce strength
                age = len(df_slice) - c_idx
                if age > 150:
                     z['strength'] *= 0.5
                
                # Add compatibility fields
                z['price'] = (z['price_high'] + z['price_low']) / 2
                z['timeframe'] = 'ZONE'
                active_zones.append(z)

        return active_zones

    @staticmethod
    def runDemandSupplyStrategy(df, sector_state, zones=[]):
        """
        Demand / Supply Strategy Engine — Pro Version
        Weighted scoring model with 6 factors + regime/liquidity guards.
        Status: STRONG_ENTRY | ENTRY_READY | WATCHLIST | AVOID
        """
        from app.engine.zones import ZoneEngine
        from app.engine.insights import InsightEngine
        from app.engine.regime import MarketRegimeEngine

        cmp = float(df['close'].iloc[-1])
        atr = ZoneEngine.calculate_atr(df).iloc[-1]
        adx = InsightEngine.get_adx(df)
        vol_ratio = float(df['volume'].iloc[-1] / df['volume'].tail(20).mean())
        avg_vol = float(df['volume'].tail(20).mean())
        regime = MarketRegimeEngine.detect_regime(df)

        demand_zones = [z for z in zones if z['type'] == 'DEMAND' and z['price'] < cmp]
        demand_zones = sorted(demand_zones, key=lambda x: x['price'], reverse=True)

        if not demand_zones:
            return {
                "bias": "NEUTRAL",
                "entryStatus": "AVOID",
                "stopLoss": round(cmp * 0.95, 2),
                "target": round(cmp * 1.05, 2),
                "riskReward": 0,
                "confidence": 0,
                "grade": "D",
                "additionalMetrics": {"regime": regime}
            }

        zone = demand_zones[0]

        nearest_sup = zone['price_low']
        stop_loss = nearest_sup - (atr * 0.3)
        target = cmp + (cmp - stop_loss) * 2
        rr = (target - cmp) / (cmp - stop_loss) if (cmp - stop_loss) > 0 else 0

        zone_width = zone['price_high'] - zone['price_low']
        tight_zone = zone_width <= atr

        # -------------------------
        # 🎯 SCORING MODEL
        # -------------------------
        score = 0

        # Zone Strength
        if zone['strength'] >= 2:
            score += 20
        else:
            score += 10

        # Zone Tightness
        if tight_zone:
            score += 15

        # Trend Strength
        if adx >= 25:
            score += 15
        elif adx >= 18:
            score += 10

        # Volume
        if vol_ratio >= 1.5:
            score += 15

        # Risk Reward
        if rr >= 2:
            score += 15

        # Sector Alignment
        if sector_state == "LEADING":
            score += 15
        elif sector_state == "IMPROVING":
            score += 10

        # Regime penalty
        if regime == "STRONG_DOWNTREND":
            score -= 20

        confidence = min(max(score, 0), 100)

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

        grade = MarketRegimeEngine.get_grade(confidence)

        return {
            "bias": "BULLISH",
            "entryStatus": status,
            "stopLoss": round(stop_loss, 2),
            "target": round(target, 2),
            "riskReward": round(rr, 2),
            "confidence": confidence,
            "grade": grade,
            "additionalMetrics": {
                "zoneWidth": round(zone_width, 2),
                "adx": round(adx, 2),
                "volRatio": round(vol_ratio, 2),
                "regime": regime
            }
        }
