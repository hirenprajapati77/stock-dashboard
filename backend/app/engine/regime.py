# backend/app/engine/regime.py
from typing import Dict, Any, Optional

class MarketRegimeEngine:
    @staticmethod
    def detect_regime(df) -> str:
        """
        Classifies current market into one of 5 regimes:
        STRONG_UPTREND | STRONG_DOWNTREND | TRENDING | WEAK_TREND | RANGE

        Uses ADX for trend strength and EMA20/50 crossover for direction.
        """
        try:
            # Handle casing anomalies gracefully
            df = df.copy()
            df.columns = [c.lower() for c in df.columns]
            
            from app.engine.insights import InsightEngine
            
            adx = InsightEngine.get_adx(df)
            ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
            cmp = float(df['close'].iloc[-1])

            if adx >= 25:
                if cmp > ema20 > ema50:
                    return "STRONG_UPTREND"
                elif cmp < ema20 < ema50:
                    return "STRONG_DOWNTREND"
                else:
                    return "TRENDING"
            elif adx >= 18:
                return "WEAK_TREND"
            else:
                return "RANGE"
        except Exception:
            return "RANGE"

    @staticmethod
    def get_grade(confidence: int) -> str:
        """
        Maps confidence score to an institutional-style trade grade.
        """
        if confidence >= 85:
            return "A+"
        elif confidence >= 75:
            return "A"
        elif confidence >= 65:
            return "B"
        elif confidence >= 55:
            return "C"
        else:
            return "D"

    @staticmethod
    def calculate_regime(
        index_price: float,
        dma_50: float,
        dma_200: float,
        vix: float,
        advance_decline_ratio: float,
        pct_above_50dma: float,
        pct_above_200dma: float,
        new_highs_count: int,
        new_lows_count: int,
        fii_net_flow_cr: float
    ) -> Dict[str, Any]:
        """
        Calculates the system-wide Market Regime Score (0-100) and classifies the market state.
        This governs buy gates and position sizing across all screener engines.
        """
        score = 0
        
        # 1. Index vs Key DMAs (Max 25 pts)
        # Price > 50 DMA > 200 DMA (Elite Bullish)
        if index_price > dma_50 > dma_200:
            score += 25
        elif index_price > dma_50:
            score += 15
        elif index_price > dma_200:
            score += 10
        else:
            # Below both DMAs
            score += 0

        # 2. Volatility (VIX) Factor (Max 20 pts)
        if vix < 13.0:
            score += 20  # Low volatility, steady accumulation
        elif vix < 16.0:
            score += 15  # Normal volatility
        elif vix < 20.0:
            score += 8   # Moderate uncertainty
        elif vix < 25.0:
            score += 3   # High fear
        else:
            score += 0   # Crisis / Bear market levels
            
        # 3. Advance/Decline Breadth (Max 15 pts)
        if advance_decline_ratio >= 2.0:
            score += 15  # Broad market participation
        elif advance_decline_ratio >= 1.5:
            score += 12
        elif advance_decline_ratio >= 1.0:
            score += 8   # Neutral / Balanced
        elif advance_decline_ratio >= 0.5:
            score += 3   # Lagging breadth
        else:
            score += 0

        # 4. Stock Breadth Metrics (Max 20 pts)
        # Average of % above 50dma & % above 200dma
        breadth_avg = (pct_above_50dma + pct_above_200dma) / 2.0
        if breadth_avg >= 75.0:
            score += 20
        elif breadth_avg >= 60.0:
            score += 15
        elif breadth_avg >= 45.0:
            score += 10
        elif breadth_avg >= 30.0:
            score += 5
        else:
            score += 0

        # 5. New Highs vs New Lows (Max 10 pts)
        total_hl = new_highs_count + new_lows_count
        if total_hl > 0:
            highs_ratio = new_highs_count / total_hl
            if highs_ratio >= 0.75:
                score += 10
            elif highs_ratio >= 0.55:
                score += 7
            elif highs_ratio >= 0.40:
                score += 4
            else:
                score += 0
        else:
            score += 5 # Neutral if no data

        # 6. FII Net Flows (Max 10 pts)
        if fii_net_flow_cr > 2000.0:
            score += 10  # Heavy institutional buying
        elif fii_net_flow_cr > 500.0:
            score += 7
        elif fii_net_flow_cr >= -500.0:
            score += 4   # Balanced
        else:
            score += 0   # Heavy institutional selling

        # Regime Classification based on final score
        if score >= 75:
            regime = "BULL MARKET"
            mode = "Aggressive"
            min_score_gate = 65
            max_pos_size_pct = 8.0
            cash_buffer_pct = 15.0
        elif score >= 55:
            regime = "NEUTRAL MARKET"
            mode = "Balanced"
            min_score_gate = 72
            max_pos_size_pct = 5.0
            cash_buffer_pct = 30.0
        elif score >= 35:
            regime = "DEFENSIVE MARKET"
            mode = "Defensive"
            min_score_gate = 80
            max_pos_size_pct = 2.5
            cash_buffer_pct = 60.0
        else:
            regime = "BEAR MARKET"
            mode = "Capital Protection"
            min_score_gate = 85
            max_pos_size_pct = 0.0
            cash_buffer_pct = 100.0

        # High Volatility Override
        is_high_volatility = vix > 22.0

        return {
            "score": score,
            "regime": regime,
            "mode": mode,
            "min_score_gate": min_score_gate,
            "max_pos_size_pct": max_pos_size_pct,
            "cash_buffer_pct": cash_buffer_pct,
            "is_high_volatility": is_high_volatility,
            "vix": vix,
            "advance_decline_ratio": advance_decline_ratio,
            "breadth_pct": float(breadth_avg)
        }
