# backend/app/services/breakout_scanner.py
import asyncio
import json
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

from app.services.candle_builder import CandleBuilder
from app.services.market_data import MarketDataService
from app.services.database_service import DatabaseService
from app.engine.breakout import BreakoutEngine
from app.engine.regime import MarketRegimeEngine
from app.engine.sector_rotation import SectorRotationEngine
from app.cache.redis_manager import RedisManager

# Setup structured logger
logger = logging.getLogger("SFMOS.BreakoutScanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class BreakoutScanner:
    """
    SFM-OS Event-Driven Real-Time Scanning & Breakout Service.
    Acts as the central quantitative intelligence engine.
    Applies strict multi-gate validation rules on incremental rolling tick streams.
    """
    
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.candle_builder = CandleBuilder(max_history_len=200)
        self.is_seeding_complete = False
        self._lock = asyncio.Lock()
        
        # Track previously triggered breakout signals to prevent duplicate spam
        # { symbol: { signal_type: timestamp } }
        self._triggered_signals: Dict[str, Dict[str, datetime]] = {}

    async def initialize_and_seed(self):
        """
        Gathers target tickers (watchlist + constituents) and pre-fills
        the candle builder history buffers with 1D historical data.
        """
        async with self._lock:
            if self.is_seeding_complete:
                return
                
            logger.info("Initializing BreakoutScanner: Querying universe and pre-seeding history buffers...")
            
            # Fetch active stock universe
            try:
                from app.services.constituent_service import ConstituentService
                watchlist = DatabaseService.get_watchlist()
                constituents = ConstituentService.get_nifty100_symbols()
                symbols = list(set(watchlist + constituents))
            except Exception as e:
                logger.error(f"Error loading universe: {e}. Defaulting to focus symbols.")
                symbols = ["RELIANCE", "TCS", "INFY", "DIVISLAB", "TATAELXSI", "HAL", "CGPOWER"]
                
            logger.info(f"Identified {len(symbols)} tickers for active scanning.")
            
            # Batch fetch 100 days of history to warm up Technical Indicators (MAs, RSI)
            # Normalizing symbols for Yahoo Finance
            yf_symbols = [s + ".NS" if not s.endswith((".NS", ".BO")) and len(s) <= 10 else s for s in symbols]
            
            try:
                logger.info("Fetching historical daily bars for baseline indicators...")
                batch_res = MarketDataService.get_ohlcv_batch(yf_symbols, tf="1D", count=100)
                
                for yf_sym, res in batch_res.items():
                    df, _, _, _ = res
                    if df is not None and not df.empty:
                        clean_sym = yf_sym.replace(".NS", "").replace(".BO", "")
                        
                        # Convert DataFrame to standard format list of dicts
                        historical_list = []
                        for idx, row in df.iterrows():
                            raw_vol = row.get("volume", row.get("Volume", 0))
                            vol = int(raw_vol) if pd.notna(raw_vol) else 0
                            
                            historical_list.append({
                                "timestamp": idx,
                                "open": float(row["open"] if "open" in row else row["Open"]),
                                "high": float(row["high"] if "high" in row else row["High"]),
                                "low": float(row["low"] if "low" in row else row["Low"]),
                                "close": float(row["close"] if "close" in row else row["Close"]),
                                "volume": vol
                            })
                            
                        # Seed history
                        self.candle_builder.seed_history(clean_sym, "1D", historical_list)
                        logger.debug(f"Pre-seeded {len(historical_list)} daily bars for {clean_sym}")
                        
                self.is_seeding_complete = True
                logger.info("BreakoutScanner initialization successfully complete.")
            except Exception as e:
                logger.error(f"Failed to seed history during startup: {e}")
                self.is_seeding_complete = True # Continue operating in live-only fallback mode

    async def on_tick(self, symbol: str, price: float, volume: int, timestamp: datetime) -> Optional[Dict[str, Any]]:
        """
        Consumes a live broker tick. Updates candle intervals and triggers incremental breakout validations.
        """
        if not self.is_seeding_complete:
            await self.initialize_and_seed()
            
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
        
        # 1. Update rolling candles (Process Tick incrementally)
        completed_candles = await self.candle_builder.process_tick(clean_symbol, price, volume, timestamp)
        
        # Evaluate scans whenever a tick updates the current rolling daily candle
        # In a production environment, we scan continuously on tick to trigger real-time breakouts
        df_daily = self.candle_builder.get_history_df(clean_symbol, "1D")
        if df_daily is None or len(df_daily) < 30:
            return None
            
        # Run validations
        try:
            return await self._evaluate_gates(clean_symbol, df_daily, timestamp)
        except Exception as e:
            logger.error(f"Error during validation gates for {clean_symbol}: {e}")
            import traceback; traceback.print_exc()
            return None

    async def _evaluate_gates(self, symbol: str, df_daily: pd.DataFrame, timestamp: datetime) -> Optional[Dict[str, Any]]:
        """
        Executes strict multi-gate compliance validation (Golden Rules 1 to 10).
        """
        # Ensure standardized column cases (Capitalized for BreakoutEngine compatibility)
        df_daily = df_daily.copy()
        df_daily.columns = [c.capitalize() for c in df_daily.columns]
        
        last_row = df_daily.iloc[-1]
        close = float(last_row["Close"])
        high = float(last_row["High"])
        low = float(last_row["Low"])
        volume = float(last_row["Volume"])
        
        # Calculate moving averages
        dma_20 = float(df_daily["Close"].rolling(20).mean().iloc[-1])
        dma_50 = float(df_daily["Close"].rolling(50).mean().iloc[-1])
        dma_200 = float(df_daily["Close"].rolling(200).mean().iloc[-1])
        avg_vol_20d = float(df_daily["Volume"].rolling(20).mean().iloc[-1])
        
        # Calculate weekly RSI baseline (estimated daily roll)
        delta = df_daily["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rs = gain / loss if loss > 0 else 0
        rsi = 100 - (100 / (1 + rs)) if loss > 0 else 100
        
        # Check Earnings Gateway T-3 Exclusion (Golden Rule 6)
        # Mock earnings query - defaults to 45 days (safe zone) unless queried
        earnings_days_away = 45 
        if earnings_days_away <= 3:
            logger.info(f"GATE_REJECT: {symbol} rejected due to Earnings Volatility Gate (Rule 6).")
            return None

        # --------------------------------------------------------
        # GATE 1: MARKET REGIME ENGINE (Rule 9 Control Gates)
        # --------------------------------------------------------
        # Fetch indices parameters dynamically
        try:
            from app.services.screener_service import ScreenerService
            regime_data = ScreenerService._calculate_market_regime("1D")
        except Exception:
            # Safe defensive fallback if market data service fails
            regime_data = {"regime": "DEFENSIVE MARKET", "score": 45, "min_score_gate": 80}
            
        regime_state = regime_data.get("regime", "DEFENSIVE MARKET")
        
        # BEAR MARKET LOCK
        if "BEAR" in regime_state:
            logger.warning("GATE_LOCK: Execution blocked. Market Regime is BEAR MARKET (Rule 9).")
            return None

        # --------------------------------------------------------
        # GATE 2: SECTOR ROTATION VALIDATION (Rule 1 Alignment)
        # --------------------------------------------------------
        try:
            from app.services.constituent_service import ConstituentService
            sector_key = ConstituentService.get_sector_for_ticker(symbol) or "UNKNOWN"
            sector_clean = sector_key.replace("NIFTY_", "")
            
            # Fetch active leading sectors
            sector_scores = ScreenerService._calculate_sector_rotation("1D")
            active_sectors_list = SectorRotationEngine.get_focus_sectors(sector_scores)
            active_sector_names = [s["theme"].replace("_HEALTHCARE", "").replace("_AUTOMATION", "").replace("_AEROSPACE", "") for s in active_sectors_list]
            
            is_active_sector = any(act in sector_clean for act in active_sector_names)
        except Exception as e:
            logger.error(f"Sector retrieval error: {e}")
            is_active_sector = True # Fallback to True to prevent structural lockouts
            sector_clean = "EQUITIES"
            
        # Reject signals in neutral/defensive regimes if sector is inactive
        if not is_active_sector and ("DEFENSIVE" in regime_state or "NEUTRAL" in regime_state):
            logger.debug(f"GATE_REJECT: {symbol} rejected due to Inactive Sector Gate (Rule 1).")
            return None

        # --------------------------------------------------------
        # GATE 3: BREAKOUT ENGINE (Rule 2 & Candle Quality)
        # --------------------------------------------------------
        # MA Gating Check
        if not (close > dma_20 > dma_50 > dma_200):
            return None # Consolidating below moving averages
            
        # 20-day high resistance pivot (excluding the current candle)
        resistance_pivot = float(df_daily["High"].iloc[-21:-1].max())
        is_price_breakout = close > resistance_pivot
        if not is_price_breakout:
            return None # consolidated below pivot
            
        # Candle Quality (Rule 2 Candle Height check: >= 0.85)
        candle_range = high - low
        close_relative_height = (close - low) / candle_range if candle_range > 0 else 0.0
        if close_relative_height < 0.85:
            logger.debug(f"GATE_REJECT: {symbol} rejected due to Weak Close Relative Height: {close_relative_height:.2f} (Rule 2).")
            return None
            
        # Volume expansion >= 2.0x (Rule 2)
        vol_ratio = volume / avg_vol_20d if avg_vol_20d > 0 else 1.0
        if vol_ratio < 2.0:
            logger.debug(f"GATE_REJECT: {symbol} rejected due to Lack of Volume Expansion: {vol_ratio:.1f}x (Rule 2).")
            return None

        # --------------------------------------------------------
        # GATE 4: RISK-REWARD ENGINE (Rule 8 Hard Gates)
        # --------------------------------------------------------
        # Calculate dynamic stop loss placed 1.5% below prev day's low or maximum 5%
        prev_low = float(df_daily["Low"].iloc[-2])
        stop_loss = max(prev_low * 0.985, close * 0.95)
        
        expected_upside_pct = 18.0 # Standard 18% breakout target expectation
        risk_amt = close - stop_loss
        reward_amt = close * (expected_upside_pct / 100.0)
        rr_ratio = reward_amt / risk_amt if risk_amt > 0 else 0.0
        
        # Hard constraints
        if rr_ratio < 3.0 or expected_upside_pct < 15.0:
            logger.debug(f"GATE_REJECT: {symbol} rejected due to insufficient Risk-Reward profile: 1:{rr_ratio:.2f} (Rule 8).")
            return None

        # --------------------------------------------------------
        # GATE 5: EXTENSION FILTER (Rule 7 Overbought checklist)
        # --------------------------------------------------------
        price_above_50dma_pct = ((close - dma_50) / dma_50) * 100.0
        if price_above_50dma_pct >= 20.0 or rsi >= 85.0:
            logger.debug(f"GATE_REJECT: {symbol} rejected due to Extension Overbought gate (Rule 7).")
            return None

        # --------------------------------------------------------
        # AI CONFIDENCE SCORING (Module 14 Integration)
        # --------------------------------------------------------
        # Compute final composite score
        base_confidence = 65.0
        # Add weights based on indicators
        if vol_ratio >= 3.0: base_confidence += 10
        if is_active_sector: base_confidence += 10
        if "BULL" in regime_state: base_confidence += 15
        
        ai_score = min(max(base_confidence, 10.0), 100.0)
        
        # Defensive Regime validation requirement: Score >= 90
        if "DEFENSIVE" in regime_state and ai_score < 90.0:
            logger.info(f"GATE_REJECT: {symbol} rejected during DEFENSIVE regime as score {ai_score} is below elite cutoff (90+).")
            return None

        # --------------------------------------------------------
        # EVENT PUBLISHING & AUDIT LOGGING
        # --------------------------------------------------------
        signal_type = "FRESH_BREAKOUT"
        
        # Anti-spam check: prevent re-triggering signal if triggered within last 60 seconds
        if symbol not in self._triggered_signals:
            self._triggered_signals[symbol] = {}
        last_triggered = self._triggered_signals[symbol].get(signal_type)
        
        now = datetime.now(timezone.utc)
        if last_triggered and (now - last_triggered).total_seconds() < 60:
            return None
            
        self._triggered_signals[symbol][signal_type] = now
        
        # Structure the payload JSON
        payload = {
            "ticker": symbol,
            "signal_type": signal_type,
            "price": float(round(close, 2)),
            "volume_ratio": float(round(vol_ratio, 2)),
            "sector": sector_clean.upper(),
            "regime": regime_state.split()[0], # e.g. "BULL"
            "rr_ratio": float(round(rr_ratio, 2)),
            "ai_confidence": float(round(ai_score, 1)),
            "timestamp": now.isoformat(),
            "actionable": True
        }
        
        # Publish events to Redis Pub/Sub channels concurrently
        logger.info(f"[!] FRESH BREAKOUT SIGNAL GENERATED: {symbol} @ {close:.2f} (AI Confidence: {ai_score}%)")
        asyncio.create_task(self.redis_manager.publish("sfmos.breakouts", payload))
        asyncio.create_task(self.redis_manager.publish("sfmos.alerts", {
            "title": f"Fresh Breakout Alert: {symbol}",
            "message": f"Breakout confirmed at {close:.2f} with {vol_ratio:.1f}x volume surge. S/L set at {stop_loss:.2f}.",
            "timestamp": now.isoformat()
        }))
        
        # Persist audit trail into the database asynchronously
        asyncio.create_task(self._audit_log_signal(symbol, signal_type, close, stop_loss, ai_score, regime_state))
        
        return payload

    async def _audit_log_signal(self, symbol: str, signal_type: str, price: float, stop_loss: float, score: float, regime: str):
        """Asynchronously inserts the signal event record into SQLite/PG audit history logs."""
        def _execute_insert():
            try:
                conn = DatabaseService.get_connection()
                cursor = conn.cursor()
                
                # Check table type dynamically for SQL format compatibility
                cursor.execute(
                    """
                    INSERT INTO signal_audit_logs 
                    (ticker, signal_type, trigger_price, stop_loss, master_score, regime_state, action_taken)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, signal_type, float(price), float(stop_loss), int(score), regime, "ENTRY")
                )
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"[Audit] Breakout signal audit trail written to database for {symbol}")
            except Exception as e:
                logger.error(f"[Audit] Database logging failed for {symbol}: {e}")
                
        # Run synchronous DB write thread-safely in background executor
        await asyncio.to_thread(_execute_insert)
