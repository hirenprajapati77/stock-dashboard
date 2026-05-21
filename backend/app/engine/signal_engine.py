import pandas as pd
import numpy as np
from typing import Dict, Any
from app.services.market_data import MarketDataService

# Engine imports
from app.engine.cpr import CPREngine
from app.engine.gann import GannEngine
from app.engine.vwap import VWAPEngine
from app.engine.volume import VolumeEngine
from app.engine.rsi import RSIEngine
from app.engine.timeframe_confluence import TimeframeConfluenceEngine
from app.engine.smart_money import SmartMoneyEngine
from app.services.database_service import DatabaseService

class SignalEngine:
    @staticmethod
    def generate_signal(symbol: str, timeframe: str = "15m") -> Dict[str, Any]:
        """
        Generates a composite BUY/SELL/HOLD signal based on institutional weighted scoring:
          - CPR = 20%
          - Gann = 20%
          - Volume = 25%
          - VWAP = 15%
          - RSI = 10%
          - Trend Confluence = 10%
        """
        try:
            # 1. Fetch OHLCV data for primary symbol/timeframe
            # We fetch 100 bars to ensure all rolling/smoothed metrics can calculate
            df, currency, err, source = MarketDataService.get_ohlcv(symbol, timeframe, count=100)
            
            if df is None or df.empty or len(df) < 20:
                return {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "signal": "HOLD",
                    "confidence": 0.0,
                    "strength": "WEAK",
                    "narrative": f"Insufficient historical data available for {symbol} on {timeframe}.",
                    "scores": {},
                    "details": {}
                }
            
            cmp = float(df['close'].iloc[-1])
            
            # --- CALCULATE CPR (Weight: 20) ---
            cpr_points = 0.0
            cpr_levels = CPREngine.calculate_cpr(df)
            cpr_state = "NEUTRAL"
            if cpr_levels and cpr_levels.get("tc") and cpr_levels.get("bc"):
                tc = cpr_levels["tc"]
                bc = cpr_levels["bc"]
                # Pivot levels
                if cmp > max(tc, bc):
                    cpr_points = 20.0
                    cpr_state = "ABOVE_CPR"
                elif cmp < min(tc, bc):
                    cpr_points = -20.0
                    cpr_state = "BELOW_CPR"
                else:
                    cpr_points = 0.0
                    cpr_state = "INSIDE_CPR"
            
            # --- CALCULATE GANN (Weight: 20) ---
            gann_points = 0.0
            gann_levels = GannEngine.calculate_gann_levels(cmp)
            gann_breakout = GannEngine.evaluate_gann_breakouts(df, gann_levels)
            gann_state = gann_breakout.get("bias", "NEUTRAL")
            if gann_state in ["BULLISH", "STRONG_BULLISH"]:
                gann_points = 20.0
            elif gann_state in ["BEARISH", "STRONG_BEARISH"]:
                gann_points = -20.0
                
            # --- CALCULATE VOLUME (Weight: 25) ---
            volume_points = 0.0
            vol_metrics = VolumeEngine.calculate_volume_metrics(df)
            rvol = vol_metrics.get("rvol", 1.0)
            vol_state = "NEUTRAL"
            if vol_metrics.get("is_spike"):
                vol_state = "SPIKE"
                
            buy_press = vol_metrics.get("buying_pressure_pct", 50.0)
            sell_press = vol_metrics.get("selling_pressure_pct", 50.0)
            
            if buy_press > sell_press:
                # Bullish volume bias
                if rvol > 2.0:
                    volume_points = 25.0
                elif rvol > 1.2:
                    volume_points = 18.0
                else:
                    volume_points = 12.0
            else:
                # Bearish volume bias
                if rvol > 2.0:
                    volume_points = -25.0
                elif rvol > 1.2:
                    volume_points = -18.0
                else:
                    volume_points = -12.0
                    
            # --- CALCULATE VWAP (Weight: 15) ---
            vwap_points = 0.0
            vwap_series = VWAPEngine.calculate_vwap(df, timeframe)
            vwap_evaluation = VWAPEngine.evaluate_vwap_state(df, vwap_series)
            vwap_state = vwap_evaluation.get("position", "NEUTRAL")
            if "ABOVE" in vwap_state:
                vwap_points = 15.0
            elif "BELOW" in vwap_state:
                vwap_points = -15.0
                
            # --- CALCULATE RSI (Weight: 10) ---
            rsi_points = 0.0
            rsi_series = RSIEngine.calculate_rsi(df, period=14)
            rsi_evaluation = RSIEngine.evaluate_rsi_state(rsi_series)
            rsi_state = rsi_evaluation.get("bias", "NEUTRAL")
            if rsi_state == "BULLISH":
                rsi_points = 10.0
            elif rsi_state == "BEARISH":
                rsi_points = -10.0
            elif rsi_state == "BULLISH_REVERSAL_RISK":
                rsi_points = 5.0  # oversold
            elif rsi_state == "BEARISH_DIVERGENCE_RISK":
                rsi_points = -5.0  # overbought
                
            # --- CALCULATE TREND CONFLUENCE (Weight: 10) ---
            trend_points = 0.0
            confluence = TimeframeConfluenceEngine.calculate_confluence(symbol)
            trend_state = confluence.get("institutional_trend_bias", "NEUTRAL")
            if trend_state == "STRONG_BULLISH":
                trend_points = 10.0
            elif trend_state == "BULLISH":
                trend_points = 6.0
            elif trend_state == "STRONG_BEARISH":
                trend_points = -10.0
            elif trend_state == "BEARISH":
                trend_points = -6.0
                
            # --- DETECT SMART MONEY (Add-on overlay, no direct raw weight but modifies narrative) ---
            sm_metrics = SmartMoneyEngine.detect_smart_money_activity(df)
            
            # --- COMPUTE COMPOSITE SCORE ---
            composite_score = cpr_points + gann_points + volume_points + vwap_points + rsi_points + trend_points
            
            # Determine Signal & Confidence
            # Total score ranges from -100 to +100
            if composite_score >= 35.0:
                signal = "BUY"
                confidence = round(composite_score, 1)
                strength = "STRONG" if composite_score >= 65.0 else "MODERATE"
            elif composite_score <= -35.0:
                signal = "SELL"
                confidence = round(abs(composite_score), 1)
                strength = "STRONG" if composite_score <= -65.0 else "MODERATE"
            else:
                signal = "HOLD"
                confidence = round(100.0 - abs(composite_score), 1)
                # Map confidence to a reasonable range if near middle
                if confidence > 90.0:
                    strength = "WEAK"
                else:
                    strength = "MODERATE"
                    
            # Build Bloomberg-grade institutional narrative
            narrative = f"Market structure for {symbol} on {timeframe} remains "
            if signal == "BUY":
                narrative += f"highly bullish (Composite Score: +{composite_score:.0f}). Price action trades "
                if cpr_state == "ABOVE_CPR":
                    narrative += "firmly above the Central Pivot Range (CPR) "
                if "ABOVE" in vwap_state:
                    narrative += "with a constructive bullish VWAP positioning. "
                if rvol > 1.2:
                    narrative += f"Relative volume (RVOL: {rvol:.1f}x) confirms elevated institutional buying pressure ({buy_press:.0f}% buying partition). "
                if gann_breakout.get("status") != "RANGE":
                    narrative += f"A key Gann {gann_breakout.get('status').replace('_', ' ')} breakout adds strong bullish momentum. "
                if sm_metrics.get("institutional_bias") == "BULLISH":
                    narrative += f"AI smart money indicators confirm active {sm_metrics.get('state').lower()} patterns. "
                narrative += "Expect continuation toward higher institutional liquidity levels."
            elif signal == "SELL":
                narrative += f"distinctly bearish (Composite Score: {composite_score:.0f}). Price is trading "
                if cpr_state == "BELOW_CPR":
                    narrative += "below key Central Pivot Range (CPR) levels, "
                if "BELOW" in vwap_state:
                    narrative += "exhibiting clear bearish VWAP positioning. "
                if rvol > 1.2:
                    narrative += f"High relative volume (RVOL: {rvol:.1f}x) verifies heavy institutional distribution ({sell_press:.0f}% selling partition). "
                if gann_breakout.get("status") != "RANGE":
                    narrative += f"A key Gann level breakdown ({gann_breakout.get('status').replace('_', ' ')}) has compromised support structure. "
                if sm_metrics.get("institutional_bias") == "BEARISH":
                    narrative += f"Smart money analytics detect active {sm_metrics.get('state').lower()} distribution cycles. "
                narrative += "Risk remains heavily tilted to the downside."
            else:
                narrative += f"balanced and range-bound (Composite Score: {composite_score:.0f}). "
                narrative += f"CPR indicates neutral placement ({cpr_state.replace('_', ' ')}), and prices are pivoting around VWAP ({vwap_evaluation.get('distance_pct')}% deviation). "
                if sm_metrics.get("state") == "BREAKOUT_LOADING":
                    narrative += "However, a severe volatility squeeze indicates heavy breakout loading; a volatile expansion is highly imminent."
                else:
                    narrative += "Wait for clear expansion or structural breakout before committing fresh capital."
                    
            # --- CACHE SIGNAL TO DATABASE ---
            try:
                DatabaseService.save_scanner_signal(
                    symbol=symbol,
                    timeframe=timeframe,
                    signal=signal,
                    confidence=confidence,
                    rvol=rvol,
                    cpr_width=cpr_levels.get("width_status", "WIDE"),
                    cpr_position=cpr_state,
                    smart_money=sm_metrics.get("state", "NEUTRAL")
                )
            except Exception as dbe:
                print(f"[SignalEngine] Error saving signal to database: {dbe}", flush=True)

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "signal": signal,
                "confidence": confidence,
                "strength": strength,
                "narrative": narrative,
                "scores": {
                    "cpr": cpr_points,
                    "gann": gann_points,
                    "volume": volume_points,
                    "vwap": vwap_points,
                    "rsi": rsi_points,
                    "trend": trend_points,
                    "composite": composite_score
                },
                "details": {
                    "cmp": round(cmp, 2),
                    "cpr": cpr_levels,
                    "gann": gann_levels,
                    "gann_breakout": gann_breakout,
                    "vwap": vwap_evaluation,
                    "volume": vol_metrics,
                    "rsi": rsi_evaluation,
                    "trend": confluence,
                    "smart_money": sm_metrics
                }
            }
        except Exception as ex:
            print(f"[SignalEngine] Exception calculating signal for {symbol}: {ex}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "signal": "HOLD",
                "confidence": 0.0,
                "strength": "WEAK",
                "narrative": f"Error running composite signal analysis: {str(ex)}",
                "scores": {},
                "details": {}
            }
