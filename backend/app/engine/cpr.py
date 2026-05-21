import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any

class CPREngine:
    @staticmethod
    def calculate_cpr_levels(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculates CPR levels (TC, PP, BC) and associated support/resistance pivots (R1-R4, S1-S4).
        Also identifies if any recent CPR was a "Virgin CPR" and determines the CPR Width classification.
        Works across all timeframes.
        """
        if df is None or df.empty:
            return {"supports": [], "resistances": [], "cpr": {}, "virgin_cprs": [], "meta": {}}

        # Ensure index is datetime if possible
        if not isinstance(df.index, pd.DatetimeIndex):
            try:
                df = df.copy()
                df.index = pd.to_datetime(df.index)
            except Exception:
                pass

        # Aggregate to daily bars to get previous day's High, Low, Close
        if isinstance(df.index, pd.DatetimeIndex):
            df_daily = df.groupby(df.index.date).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        else:
            df_daily = df.copy()

        if len(df_daily) < 2:
            # Fallback if there is not enough daily data (e.g. only 1 candle or new symbol)
            # Use current candle as approximation
            cmp = float(df['close'].iloc[-1])
            H = float(df['high'].max())
            L = float(df['low'].min())
            C = float(df['close'].iloc[-1])
            df_daily = pd.DataFrame([{
                'open': cmp, 'high': H, 'low': L, 'close': C, 'volume': 0
            }, {
                'open': cmp, 'high': H, 'low': L, 'close': C, 'volume': 0
            }])

        # Today's CPR is calculated from YESTERDAY's High, Low, Close (index -2 of daily df)
        prev_day = df_daily.iloc[-2]
        H = float(prev_day['high'])
        L = float(prev_day['low'])
        C = float(prev_day['close'])

        PP = (H + L + C) / 3.0
        BC = (H + L) / 2.0
        TC = (PP - BC) + PP

        # Standard plotted values (ensure TC is physically above BC)
        tc_plotted = max(TC, BC)
        bc_plotted = min(TC, BC)

        # Standard Pivot Levels associated with CPR
        R1 = 2 * PP - L
        S1 = 2 * PP - H
        R2 = PP + (H - L)
        S2 = PP - (H - L)
        R3 = R1 + (H - L)
        S3 = S1 - (H - L)
        R4 = R3 + (H - L)
        S4 = S3 - (H - L)

        # Calculate width percentage and compare to historical widths (20-day average)
        widths = []
        for i in range(1, min(22, len(df_daily))):
            if i + 1 > len(df_daily):
                break
            hist_prev = df_daily.iloc[-i - 1]
            h_h = float(hist_prev['high'])
            h_l = float(hist_prev['low'])
            h_c = float(hist_prev['close'])
            h_pp = (h_h + h_l + h_c) / 3.0
            h_bc = (h_h + h_l) / 2.0
            h_tc = 2 * h_pp - h_bc
            widths.append(abs(h_tc - h_bc) / h_pp * 100)

        current_width = abs(tc_plotted - bc_plotted) / PP * 100
        avg_width = sum(widths) / len(widths) if widths else current_width
        relative_width = current_width / avg_width if avg_width > 0 else 1.0

        if relative_width < 0.75:
            width_type = "NARROW"
            width_desc = "Highly compressed CPR range. Signals potential for an explosive trend or breakout today!"
        elif relative_width > 1.25:
            width_type = "WIDE"
            width_desc = "Highly expanded CPR range. Signals a highly probable range-bound, sideways, or mean-reverting session today."
        else:
            width_type = "AVERAGE"
            width_desc = "Average CPR range width. Standard trend-following and pivot boundary rules apply."

        # Find recent "Virgin CPRs" in the last 15 days (where daily High/Low never touched/crossed the CPR range)
        virgin_cprs = []
        max_lookback = min(15, len(df_daily) - 1)
        for i in range(1, max_lookback):
            if i + 2 > len(df_daily):
                break
            hist_day = df_daily.iloc[-i - 1]
            hist_prev_day = df_daily.iloc[-i - 2]

            hd_high = float(hist_day['high'])
            hd_low = float(hist_day['low'])

            h_h = float(hist_prev_day['high'])
            h_l = float(hist_prev_day['low'])
            h_c = float(hist_prev_day['close'])

            h_pp = (h_h + h_l + h_c) / 3.0
            h_bc = (h_h + h_l) / 2.0
            h_tc = 2 * h_pp - h_bc

            h_tc_p = max(h_tc, h_bc)
            h_bc_p = min(h_tc, h_bc)

            # A day where the entire price range is completely above or completely below the CPR
            if hd_low > h_tc_p or hd_high < h_bc_p:
                virgin_cprs.append({
                    "date": hist_day.name.isoformat() if hasattr(hist_day.name, "isoformat") else str(hist_day.name),
                    "pp": round(h_pp, 2),
                    "tc": round(h_tc_p, 2),
                    "bc": round(h_bc_p, 2),
                    "type": "VIRGIN_CPR",
                    "level_range": f"{round(h_bc_p, 2)} - {round(h_tc_p, 2)}"
                })

        cmp = float(df['close'].iloc[-1])

        cpr_levels = {
            "tc": round(tc_plotted, 2),
            "pp": round(PP, 2),
            "bc": round(bc_plotted, 2),
            "width_pct": round(current_width, 3),
            "relative_width": round(relative_width, 2),
            "width_classification": width_type,
            "width_description": width_desc,
        }

        # Build support/resistance list for chart rendering
        levels_list = [
            {"price": round(R1, 2), "label": "CPR R1", "type": "RESISTANCE", "strength": 0.8},
            {"price": round(R2, 2), "label": "CPR R2", "type": "RESISTANCE", "strength": 1.2},
            {"price": round(R3, 2), "label": "CPR R3", "type": "RESISTANCE", "strength": 1.5},
            {"price": round(R4, 2), "label": "CPR R4", "type": "RESISTANCE", "strength": 2.0},
            {"price": round(S1, 2), "label": "CPR S1", "type": "SUPPORT", "strength": 0.8},
            {"price": round(S2, 2), "label": "CPR S2", "type": "SUPPORT", "strength": 1.2},
            {"price": round(S3, 2), "label": "CPR S3", "type": "SUPPORT", "strength": 1.5},
            {"price": round(S4, 2), "label": "CPR S4", "type": "SUPPORT", "strength": 2.0},
            {"price": round(tc_plotted, 2), "label": "CPR TC", "type": "RESISTANCE" if tc_plotted > cmp else "SUPPORT", "strength": 1.0},
            {"price": round(bc_plotted, 2), "label": "CPR BC", "type": "RESISTANCE" if bc_plotted > cmp else "SUPPORT", "strength": 1.0},
            {"price": round(PP, 2), "label": "CPR PP", "type": "RESISTANCE" if PP > cmp else "SUPPORT", "strength": 1.2},
        ]

        # Inject active Virgin CPRs as support/resistance levels
        for vc in virgin_cprs:
            levels_list.append({
                "price": vc["pp"],
                "label": f"Virgin CPR PP ({vc['date']})",
                "type": "SUPPORT" if vc["pp"] < cmp else "RESISTANCE",
                "strength": 2.0
            })

        supports = [l for l in levels_list if l["type"] == "SUPPORT"]
        resistances = [l for l in levels_list if l["type"] == "RESISTANCE"]

        supports = sorted(supports, key=lambda x: x['price'], reverse=True)
        resistances = sorted(resistances, key=lambda x: x['price'])

        return {
            "supports": supports[:5],
            "resistances": resistances[:5],
            "cpr": cpr_levels,
            "virgin_cprs": virgin_cprs[:3],  # Limit to 3 most recent
            "meta": {
                "prev_high": H,
                "prev_low": L,
                "prev_close": C,
                "current_cmp": cmp
            }
        }

    @staticmethod
    def runCPRStrategy(df: pd.DataFrame, sector_state: str, cpr_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        CPR Strategy Engine
        Evaluates trend bias, narrow breakout opportunities, wide range mean reversion,
        and virgin CPR tests.
        """
        from app.engine.insights import InsightEngine
        from app.engine.regime import MarketRegimeEngine
        from app.engine.zones import ZoneEngine

        if not cpr_data or "cpr" not in cpr_data:
            return {"bias": "NEUTRAL", "entryStatus": "AVOID", "confidence": 0}

        cmp = float(df['close'].iloc[-1])
        vol_ratio = InsightEngine.get_volume_ratio(df)
        adx = InsightEngine.get_adx(df)
        atr = ZoneEngine.calculate_atr(df).iloc[-1]

        cpr = cpr_data["cpr"]
        tc = cpr["tc"]
        pp = cpr["pp"]
        bc = cpr["bc"]
        width_classification = cpr["width_classification"]
        relative_width = cpr["relative_width"]

        # Determine price location relative to CPR lines
        if cmp > tc:
            position = "ABOVE_CPR"
            bias = "BULLISH"
            side = "LONG"
        elif cmp < bc:
            position = "BELOW_CPR"
            bias = "BEARISH"
            side = "SHORT"
        else:
            position = "INSIDE_CPR"
            bias = "RANGE"
            side = "LONG" # Default long at BC support

        # 🎯 SCORING & SETUP SYSTEM
        score = 0
        reasons = []

        # Setup 1: Narrow CPR Breakout
        if width_classification == "NARROW":
            if position == "ABOVE_CPR":
                score += 35
                reasons.append("NARROW_CPR_BULLISH_BREAKOUT")
                if vol_ratio > 1.4:
                    score += 20
                    reasons.append("HIGH_VOLUME_BREAKOUT")
            elif position == "BELOW_CPR":
                score += 35
                reasons.append("NARROW_CPR_BEARISH_BREAKDOWN")
                if vol_ratio > 1.4:
                    score += 20
                    reasons.append("HIGH_VOLUME_BREAKDOWN")
                    
        # Setup 2: Wide CPR Range Mean Reversion
        elif width_classification == "WIDE":
            if position == "INSIDE_CPR":
                dist_to_bc = abs(cmp - bc) / bc * 100
                dist_to_tc = abs(cmp - tc) / tc * 100
                if dist_to_bc < 0.25:
                    score += 40
                    reasons.append("WIDE_CPR_SUPPORT_BOUNCE")
                    side = "LONG"
                elif dist_to_tc < 0.25:
                    score += 40
                    reasons.append("WIDE_CPR_RESISTANCE_REJECTION")
                    side = "SHORT"
            else:
                # Reversion from standard S1/S2 or R1/R2 boundaries back to CPR Pivot
                supports = cpr_data.get("supports", [])
                resistances = cpr_data.get("resistances", [])
                cpr_s = [s for s in supports if "CPR S" in s.get("label", "")]
                cpr_r = [r for r in resistances if "CPR R" in r.get("label", "")]

                if cpr_s and abs(cmp - cpr_s[0]["price"]) / cmp < 0.002:
                    score += 30
                    reasons.append("CPR_S1_SUPPORT_REVERSION")
                    side = "LONG"
                elif cpr_r and abs(cmp - cpr_r[0]["price"]) / cmp < 0.002:
                    score += 30
                    reasons.append("CPR_R1_RESISTANCE_REVERSION")
                    side = "SHORT"

        # Setup 3: Virgin CPR Magnetic Test
        # Rejections off historical virgin CPR levels
        virgin_cprs = cpr_data.get("virgin_cprs", [])
        for vc in virgin_cprs:
            vc_pp = vc["pp"]
            if abs(cmp - vc_pp) / cmp < 0.0025:
                score += 35
                reasons.append(f"VIRGIN_CPR_REJECTION ({vc['date']})")
                side = "SHORT" if cmp > vc_pp else "LONG"
                break

        # Setup 4: Trend strength (ADX) & Volume filter
        if bias in ["BULLISH", "BEARISH"] and adx > 20:
            score += 15
        if vol_ratio > 1.2:
            score += 10

        # Setup 5: Sector Alignment
        if sector_state == "LEADING" and side == "LONG":
            score += 15
        elif sector_state == "LAGGING" and side == "SHORT":
            score += 15

        confidence = min(score, 100)

        # Entry Status
        if confidence >= 70:
            status = "STRONG_ENTRY"
        elif confidence >= 55:
            status = "ENTRY_READY"
        elif confidence >= 35:
            status = "WATCHLIST"
        else:
            status = "AVOID"

        # Target & SL calculations based on CPR boundaries
        if side == "LONG":
            stop_loss = bc - (atr * 0.5) if cmp > bc else cmp * 0.985
            target = tc if cmp < tc else tc + abs(tc - bc) * 1.5
        else:
            stop_loss = tc + (atr * 0.5) if cmp < tc else cmp * 1.015
            target = bc if cmp > bc else bc - abs(tc - bc) * 1.5

        rr = abs(target - cmp) / abs(cmp - stop_loss) if abs(cmp - stop_loss) > 0 else 0

        return {
            "bias": bias,
            "side": side,
            "entryStatus": status,
            "confidence": confidence,
            "stopLoss": round(stop_loss, 2),
            "target": round(target, 2),
            "riskReward": round(rr, 2),
            "grade": MarketRegimeEngine.get_grade(confidence),
            "additionalMetrics": {
                "cpr_position": position,
                "width_classification": width_classification,
                "relative_width": round(relative_width, 2),
                "reasons": reasons,
                "volRatio": round(vol_ratio, 2),
                "adx": round(adx, 2)
            }
        }

    @staticmethod
    def calculate_cpr(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Bridge method for backward compatibility with SignalEngine.
        Flattens and returns a dict with tc, pp, bc, and width_status.
        """
        res = CPREngine.calculate_cpr_levels(df)
        cpr_dict = res.get("cpr", {})
        flat = {
            "tc": cpr_dict.get("tc"),
            "pp": cpr_dict.get("pp"),
            "bc": cpr_dict.get("bc"),
            "width_pct": cpr_dict.get("width_pct"),
            "relative_width": cpr_dict.get("relative_width"),
            "width_classification": cpr_dict.get("width_classification"),
            "width_status": cpr_dict.get("width_classification"),
            "width_description": cpr_dict.get("width_description"),
            "supports": res.get("supports", []),
            "resistances": res.get("resistances", []),
            "virgin_cprs": res.get("virgin_cprs", []),
            "meta": res.get("meta", {})
        }
        return flat

