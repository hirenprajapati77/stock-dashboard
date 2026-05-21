import pandas as pd
import numpy as np
from typing import Dict, Any
from app.services.market_data import MarketDataService

class TimeframeConfluenceEngine:
    @staticmethod
    def calculate_confluence(symbol: str) -> Dict[str, Any]:
        """
        Analyzes the trend bias across multiple timeframes: 5m, 15m, 1H, 1D.
        Calculates an alignment score (0-100) and an overall institutional bias.
        """
        timeframes = ["5m", "15m", "1H", "1D"]
        weights = {
            "5m": 0.15,
            "15m": 0.25,
            "1H": 0.30,
            "1D": 0.30
        }
        
        tf_results = {}
        total_weight_used = 0.0
        weighted_score_sum = 0.0  # Range: -100 to +100
        
        for tf in timeframes:
            try:
                # Fetch OHLCV data for this symbol and timeframe
                # We limit the count to 100 bars to speed up the fetch
                df, _, err, _ = MarketDataService.get_ohlcv(symbol, tf, count=100)
                
                if df is None or df.empty or len(df) < 20:
                    tf_results[tf] = {
                        "bias": "NEUTRAL",
                        "score": 0.0,
                        "close": 0.0,
                        "ema20": 0.0,
                        "status": "INSUFFICIENT_DATA"
                    }
                    continue
                
                # Calculate indicators
                close_series = df['close']
                ema20 = close_series.ewm(span=20, adjust=False).mean()
                ema50 = close_series.ewm(span=50, adjust=False).mean()
                
                cmp = float(close_series.iloc[-1])
                e20 = float(ema20.iloc[-1])
                e50 = float(ema50.iloc[-1])
                
                # Determine score (-100 to +100) for this timeframe
                tf_score = 0.0
                if cmp > e20 > e50:
                    bias = "STRONG_BULLISH"
                    tf_score = 100.0
                elif cmp > e20:
                    bias = "BULLISH"
                    tf_score = 50.0
                elif cmp < e20 < e50:
                    bias = "STRONG_BEARISH"
                    tf_score = -100.0
                elif cmp < e20:
                    bias = "BEARISH"
                    tf_score = -50.0
                else:
                    bias = "NEUTRAL"
                    tf_score = 0.0
                
                # Incorporate RSI if we have enough bars
                if len(close_series) >= 14:
                    from app.engine.rsi import RSIEngine
                    rsi_series = RSIEngine.calculate_rsi(df, period=14)
                    rsi_val = float(rsi_series.iloc[-1])
                    if rsi_val > 60:
                        tf_score = min(100.0, tf_score + 20.0)
                    elif rsi_val < 40:
                        tf_score = max(-100.0, tf_score - 20.0)
                
                tf_results[tf] = {
                    "bias": bias,
                    "score": tf_score,
                    "close": round(cmp, 2),
                    "ema20": round(e20, 2),
                    "ema50": round(e50, 2),
                    "status": "OK"
                }
                
                w = weights[tf]
                weighted_score_sum += tf_score * w
                total_weight_used += w
                
            except Exception as e:
                print(f"[Confluence] Error analyzing timeframe {tf} for {symbol}: {e}", flush=True)
                tf_results[tf] = {
                    "bias": "NEUTRAL",
                    "score": 0.0,
                    "close": 0.0,
                    "ema20": 0.0,
                    "status": f"ERROR: {str(e)}"
                }
        
        # Normalize in case some timeframes failed
        if total_weight_used > 0:
            final_normalized_score = weighted_score_sum / total_weight_used
        else:
            final_normalized_score = 0.0
            
        # Map normalized score (-100 to 100) to alignment score (0 to 100)
        # -100 -> 0%, 0 -> 50%, 100 -> 100%
        alignment_score = round((final_normalized_score + 100.0) / 2.0, 1)
        
        # Determine overall institutional bias based on normalized score
        if final_normalized_score >= 60.0:
            overall_bias = "STRONG_BULLISH"
        elif final_normalized_score >= 15.0:
            overall_bias = "BULLISH"
        elif final_normalized_score <= -60.0:
            overall_bias = "STRONG_BEARISH"
        elif final_normalized_score <= -15.0:
            overall_bias = "BEARISH"
        else:
            overall_bias = "NEUTRAL"
            
        # Build narrative
        bullish_tfs = [tf for tf, res in tf_results.items() if "BULLISH" in res["bias"]]
        bearish_tfs = [tf for tf, res in tf_results.items() if "BEARISH" in res["bias"]]
        
        narrative = f"Trend structure is {overall_bias.replace('_', ' ')} across active timeframes. "
        if len(bullish_tfs) == len(timeframes):
            narrative += "Perfect bullish alignment across all major timeframes indicates strong institutional bidding."
        elif len(bearish_tfs) == len(timeframes):
            narrative += "Perfect bearish alignment across all major timeframes indicates systemic institutional distribution."
        elif len(bullish_tfs) >= 2:
            narrative += f"Bullish momentum is leading on {', '.join(bullish_tfs)}, signaling selective dip-buying."
        elif len(bearish_tfs) >= 2:
            narrative += f"Bearish structure dominates on {', '.join(bearish_tfs)}, signaling smart money selling on rallies."
        else:
            narrative += "Timeframe alignment is fragmented, indicating range-bound trading with no distinct institutional bias."
            
        return {
            "symbol": symbol,
            "alignment_score": alignment_score,
            "institutional_trend_bias": overall_bias,
            "timeframe_details": tf_results,
            "narrative": narrative
        }
