# backend/app/engine/breakout.py
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, Any

class BreakoutEngine:
    @staticmethod
    def evaluate_breakout_day1(df_daily: pd.DataFrame, avg_vol_20d: float, active_sector: bool) -> Dict[str, Any]:
        """
        Runs Day 1 Breakout Checks (Golden Rule 2 & 7).
        All strict conditions must pass to trigger a FRESH BREAKOUT.
        """
        if len(df_daily) < 60:
            return {"status": "WATCHLIST", "reason": "Insufficient historical data (< 60 bars)"}

        if not active_sector:
            return {"status": "AVOID", "reason": "Stock is not in an active focus sector"}

        # Standardize columns to capitalized
        df_daily = df_daily.copy()
        df_daily.columns = [c.capitalize() for c in df_daily.columns]

        last_row = df_daily.iloc[-1]
        prev_row = df_daily.iloc[-2]
        
        close = float(last_row['Close'])
        high = float(last_row['High'])
        low = float(last_row['Low'])
        volume = float(last_row['Volume'])
        
        # 1. Price above key DMAs
        dma_20 = df_daily['Close'].rolling(20).mean().iloc[-1]
        dma_50 = df_daily['Close'].rolling(50).mean().iloc[-1]
        dma_200 = df_daily['Close'].rolling(200).mean().iloc[-1]
        
        if close <= dma_20 or close <= dma_50 or close <= dma_200:
            return {"status": "AVOID", "reason": "Price is below key moving averages (20, 50, 200 DMA)"}
            
        # 2. Breaking multi-week resistance (60-day high check)
        lookback_resistance = df_daily['High'].iloc[-60:-1].max()
        if close <= lookback_resistance:
            return {"status": "WATCHLIST", "reason": "Price is still consolidating below 60-day resistance"}

        # 3. Volume > 2x average on breakout day
        if volume < avg_vol_20d * 2.0:
            return {"status": "WATCHLIST", "reason": f"Breakout lacks volume expansion (RVol: {volume/avg_vol_20d:.1f}x < 2x)"}

        # 4. Upper 70% candle close check
        candle_range = high - low
        if candle_range > 0:
            close_position = (close - low) / candle_range
            if close_position < 0.70:
                # Weak close: Day 1 fails and downgrades to watchlist (Golden Rule 8)
                return {"status": "WATCHLIST", "reason": f"Weak breakout close ({close_position*100:.1f}% of range is < 70%)"}

        # All filters passed -> Day 1 Buy Triggered
        # Stop loss is set 1.5% below the previous day's low or key support
        stop_loss = float(prev_row['Low'] * 0.985)
        return {
            "status": "FRESH BREAKOUT",
            "trigger_price": close,
            "stop_loss": stop_loss,
            "reason": "Clean range breakout on massive volume with an elite close."
        }

    @staticmethod
    def evaluate_breakout_day2(df_daily: pd.DataFrame, breakout_zone: float, day1_sl: float) -> Dict[str, Any]:
        """
        Runs Day 2 Confirmation Checks (Golden Rule 3).
        """
        if len(df_daily) < 2:
            return {"status": "WATCHLIST", "action": "HOLD", "stop_loss": day1_sl}

        # Standardize columns to capitalized
        df_daily = df_daily.copy()
        df_daily.columns = [c.capitalize() for c in df_daily.columns]

        last_row = df_daily.iloc[-1]
        close_day2 = float(last_row['Close'])
        
        if close_day2 >= breakout_zone:
            # Confirmed Day 2 Breakout
            return {
                "status": "CONFIRMED BREAKOUT",
                "action": "HOLD",
                "stop_loss": day1_sl,
                "reason": "Day 2 holds successfully above the breakout zone."
            }
        else:
            # Day 2 Failure: Reversed below breakout zone
            avoid_until = datetime.now() + timedelta(days=10)
            return {
                "status": "FAILED BREAKOUT",
                "action": "LIQUIDATE IMMEDIATELY",
                "avoid_until": avoid_until.isoformat(),
                "reason": "Golden Rule 3 Violation: Price reversed below breakout zone on Day 2. Enforcing 10-day avoid period."
            }
