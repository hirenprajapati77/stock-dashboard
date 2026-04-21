from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import time
from datetime import datetime
from app.services.signal_archive_service import SignalArchiveService

"""
Stock Logic v1.0 (LOCKED)

Rules:
- Sector state is a hard gate (LEADING/IMPROVING only)
- Stock must outperform its sector (RS > 0)
- Volume expansion is mandatory (Vol > 1.5x)
- No stock intelligence in lagging sectors

Any change must update tests.
"""

from app.services.constituent_service import ConstituentService
from app.services.sector_service import SectorService
from app.engine.insights import InsightEngine


@dataclass
class ScreenerRule:
    """
    Default Momentum Criteria v1.1 (Modified for better hit frequency)
    """
    change_threshold: float = 1.4      # Down from 2.0
    volume_threshold: float = 1.25     # Down from 1.5
    vol_shock_threshold: float = 2.0
    lookback_bars: int = 15            # Up from 10
    min_confidence: int = 50


class ScreenerService:
    """Builds stock-intelligence rows for the trader intelligence panel."""

    TIMEFRAME_MAP: Dict[str, Dict[str, str]] = {
        "5m": {"interval": "5m", "period": "5d"},
        "15m": {"interval": "15m", "period": "5d"},
        "1D": {"interval": "1d", "period": "6mo"},
        "Daily": {"interval": "1d", "period": "6mo"},
    }

    RULES_BY_TF: Dict[str, ScreenerRule] = {
        "5m": ScreenerRule(change_threshold=0.7, volume_threshold=1.5),
        "15m": ScreenerRule(change_threshold=0.9, volume_threshold=1.5),
        "1D": ScreenerRule(change_threshold=1.4, volume_threshold=1.25, lookback_bars=15),
        "Daily": ScreenerRule(change_threshold=1.4, volume_threshold=1.25, lookback_bars=15),
    }

    SECTOR_INDEX_BY_KEY: Dict[str, str] = {
        "NIFTY_BANK": "^NSEBANK",
        "NIFTY_IT": "^CNXIT",
        "NIFTY_FMCG": "^CNXFMCG",
        "NIFTY_METAL": "^CNXMETAL",
        "NIFTY_PHARMA": "^CNXPHARMA",
        "NIFTY_ENERGY": "^CNXENERGY",
        "NIFTY_AUTO": "^CNXAUTO",
        "NIFTY_REALTY": "^CNXREALTY",
        "NIFTY_PSU_BANK": "^CNXPSUBANK",
    }

    # Class-level cache
    _cache: Dict[str, Any] = {
        "data": None,
        "timestamp": 0.0,
        "timeframe": None
    }
    CACHE_TTL = 900 # 15 minutes to reduce yfinance load

    @staticmethod
    def _fetch_realtime_price(symbol: str) -> Optional[Dict]:
        """Fetches real-time price using fast_info to validate/update screener hits."""
        try:
            # Handle .NS suffix or indices
            ticker_sym = symbol
            if "." not in symbol and not symbol.startswith("^"):
                ticker_sym = f"{symbol}.NS"
            
            ticker = yf.Ticker(ticker_sym)
            fast = ticker.fast_info
            
            last_price = float(fast.get('lastPrice') or fast.get('last_price'))
            prev_close = float(fast.get('previousClose') or fast.get('previous_close'))
            
            if last_price and prev_close:
                change_pct = ((last_price - prev_close) / prev_close) * 100
                return {
                    "symbol": symbol,
                    "price": last_price,
                    "change": change_pct,
                    "valid": True
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _find_last_hit_index(cond: pd.Series, lookback_bars: int = 10) -> Optional[int]:
        if cond is None or cond.empty:
            return None
        start = max(0, len(cond) - lookback_bars)
        for pos in range(len(cond) - 1, start - 1, -1):
            if bool(cond.iloc[pos]):
                return pos
        return None

    @staticmethod
    def _compute_streak_flags(cond: pd.Series, idx: int) -> tuple[bool, bool, bool]:
        hits1d = bool(cond.iloc[idx])
        hits2d = hits1d and idx - 1 >= 0 and bool(cond.iloc[idx - 1])
        hits3d = hits2d and idx - 2 >= 0 and bool(cond.iloc[idx - 2])
        return hits1d, hits2d, hits3d

    @staticmethod
    def get_confidence_grade(quality_score: float) -> str:
        if quality_score >= 85:
            return "A"
        elif quality_score >= 70:
            return "B"
        elif quality_score >= 55:
            return "C"
        else:
            return "D"


    @staticmethod
    def _extract_fast_value(fast_info, *keys):
        for key in keys:
            value = fast_info.get(key)
            if value is not None:
                return value
        return None

    @classmethod
    def _calculate_vwap(cls, df: pd.DataFrame) -> float:
        """Calculates VWAP for the current session or period."""
        if df.empty: return 0.0
        close_col = "Close" if "Close" in df.columns else "close"
        vol_col = "Volume" if "Volume" in df.columns else "volume"
        high_col = "High" if "High" in df.columns else "high"
        low_col = "Low" if "Low" in df.columns else "low"
        
        if all(c in df.columns for c in [high_col, low_col, close_col, vol_col]):
            tp = (df[high_col] + df[low_col] + df[close_col]) / 3
            return float((tp * df[vol_col]).sum() / df[vol_col].sum()) if df[vol_col].sum() > 0 else float(df[close_col].iloc[-1])
        return float(df[close_col].iloc[-1])

    @classmethod
    def _is_breakout(cls, df: pd.DataFrame, window: int = 10) -> bool:
        """Simple breakout detection: Current high > max of previous N highs."""
        if len(df) <= window: return False
        high_col = "High" if "High" in df.columns else "high"
        curr_high = df[high_col].iloc[-1]
        prev_highs = df[high_col].iloc[-(window+1):-1]
        return bool(curr_high > prev_highs.max())

    @classmethod
    def _calculate_rsi(cls, prices: pd.Series, period: int = 14) -> pd.Series:
        """Lightweight RSI calculation."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @classmethod
    def _identify_setup_type(cls, df: pd.DataFrame, vol_ratio: float) -> str:
        """Categorizes the momentum hit into a specific technical setup."""
        if len(df) < 20: return "MOMENTUM_HIT"
        
        # 1. Breakout Check
        if cls._is_breakout(df, window=10):
            return "BREAKOUT"
            
        # 2. RSI Pullback Check
        close = df['close'] if 'close' in df.columns else df['Close']
        rsi = cls._calculate_rsi(close)
        if not rsi.empty:
            curr_rsi = rsi.iloc[-1]
            prev_rsis = rsi.iloc[-5:-1]
            # If RSI was oversold/neutral recently and now turning up
            if any(prev_rsis < 45) and curr_rsi > prev_rsis.max():
                return "RSI_PULLBACK"
                
        # 3. Volume Surge
        if vol_ratio >= 2.5:
            return "VOLUME_SURGE"
            
        return "MOMENTUM_HIT"

    @classmethod
    def calculate_quality_score(cls, rs_sector: float, stock_acc: float, vol_ratio: float, 
                               structure_bias: str, rr: float, atr_expansion: float) -> float:
        """Phase 4: Stock Quality Score Calculation (0-100)"""
        # 1. Stock RS inside sector (30%) - Clamped -5% to +5% -> 0-100
        rs_clamped = float(max(-5.0, float(min(5.0, float(rs_sector)))))
        rs_score = (rs_clamped + 5.0) * 10.0
        
        # 2. Stock Acceleration (20%) - Normalized -0.1 to +0.1 -> 0-100
        acc_score = float(max(0.0, float(min(100.0, float(stock_acc) * 500.0 + 50.0))))
        
        # 3. Volume Ratio (15%) - Smoother gradient
        vol_ratio_f = float(vol_ratio)
        if vol_ratio_f >= 1.5:
            vol_score = 100
        elif vol_ratio_f >= 1.2:
            vol_score = 90
        elif vol_ratio_f >= 1.0:
            vol_score = 75
        elif vol_ratio_f >= 0.8:
            vol_score = 50
        else:
            vol_score = 10
        
        # 4. Structure Bias (15%)
        bias_score = 100 if structure_bias == "BULLISH" else 50 if structure_bias == "NEUTRAL" else 0
        
        # 5. Risk-Reward Bonus (10%)
        rr_bonus = 100 if rr >= 1.8 else 0
        
        # 6. ATR Expansion (10%) - 1.0 to 1.5 -> 0-100
        atr_score = float(max(0.0, float(min(100.0, (float(atr_expansion) - 1.0) * 200.0))))
        
        final_score = (
            0.30 * rs_score +
            0.25 * bias_score +
            0.15 * acc_score +
            0.15 * vol_score +
            0.10 * atr_score +
            0.05 * rr_bonus
        )
        
        return float(final_score)

    @classmethod
    def _calculate_sector_concentration(cls, hits: List[Dict]) -> List[Dict]:
        """Aggregates hits by sector to find trending market themes."""
        counts = {}
        for h in hits:
            s = h.get("sector", "Unknown")
            counts[s] = counts.get(s, 0) + 1
        
        # Sort by count descending
        sorted_counts = sorted(
            [{"sector": s, "count": c} for s, c in counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )
        return sorted_counts

    @classmethod
    def get_entry_tag(cls, quality_score: float, sector_state: str, stock_active: bool) -> str:
        """Phase 4: Updated Entry Tagging Logic based on Quality Score"""
        if sector_state == "LAGGING" or not stock_active:
            return "AVOID"
        
        if quality_score >= 80:
            return "STRONG_ENTRY"
        if quality_score >= 65:
            return "ENTRY_READY"
        if quality_score >= 50:
            return "WATCHLIST"
            
        return "AVOID"

    @classmethod
    def get_smart_money_tier(cls, vol_ratio: float) -> str:
        """Categorizes institutional activity based on volume expansion."""
        if vol_ratio >= 2.5: return "STRONG"
        if vol_ratio >= 1.8: return "MODERATE"
        if vol_ratio >= 1.5: return "WEAK"
        return "NONE"

    @classmethod
    def get_momentum_strength(cls, score: float, vol_ratio: float, acc: float) -> str:
        """Derived metric based on price change, volume and acceleration with color-coded classification."""
        m_strength_val = (score * (vol_ratio / 2.0)) + (acc * 5)
        if m_strength_val >= 75: return "STRONG"
        if m_strength_val >= 45: return "MODERATE"
        return "WEAK"

    @classmethod
    def get_exit_tag(cls, price_below_vwap: bool, vol_drop: bool, sector_state: str) -> str:
        """Exit Tagging Logic v1.0 (LOCKED)"""
        if sector_state == "LAGGING" or (price_below_vwap and vol_drop):
            return "EXIT"
        return "HOLD"

    @classmethod
    def get_risk_level(cls, sector_state: str, vol_ratio: float, vol_high: bool) -> str:
        """Risk Level Logic v1.0 (LOCKED)"""
        if vol_high:
            return "HIGH"
        if sector_state == "LEADING" and vol_ratio >= 2.0:
            return "LOW"
        if vol_ratio >= 1.5:
            return "MEDIUM"
        return "HIGH"

    @classmethod
    def get_risk_units(cls, sector_state: str, entry_tag: str, risk_level: str, stop_distance_pct: float) -> float:
        """RU Logic v1.0 (LOCKED)"""
        if entry_tag in ["AVOID", "WATCHLIST"]: return 0.0
        if entry_tag == "WAIT": return 0.5
        
        # ENTRY_READY
        ru = 0.5
        if sector_state == "LEADING" and risk_level == "LOW":
            ru = 1.5
        elif risk_level == "MEDIUM":
            ru = 1.0
            
        # Stop-Distance Awareness
        if stop_distance_pct > 1.2:
            ru = max(0.5, ru - 0.5)
            
        return float(ru)

    @classmethod
    def get_session_tag(cls) -> tuple[str, str]:
        """Session Timing Logic v1.0 (LOCKED) - India Market IST"""
        # Render/Cloud servers are UTC. Convert to IST (UTC+5:30)
        from datetime import timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        
        # Handle weekends: NSE/BSE closed on Sat (5) and Sun (6)
        if now_ist.weekday() >= 5: return "CLOSED", "BEST"
        
        cur_time = now_ist.hour * 100 + now_ist.minute
        
        if 915 <= cur_time < 930: return "OPEN", "AVOID"
        if 930 <= cur_time < 1030: return "EARLY", "CAUTION"
        if 1030 <= cur_time < 1430: return "MID", "BEST"
        if 1430 <= cur_time < 1510: return "LATE", "CAUTION"
        if 1510 <= cur_time < 1530: return "CLOSE", "AVOID"
        
        return "CLOSED", "BEST"

    @classmethod
    def _get_live_quote(cls, symbol: str, fallback_price: float, fallback_change: float) -> tuple[float, float]:
        """Best-effort quote refresh so UI can reflect live values, not only last candle close."""
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            live_price = cls._extract_fast_value(fast_info, 'lastPrice', 'last_price', 'regularMarketPrice')
            prev_close = cls._extract_fast_value(fast_info, 'previousClose', 'regularMarketPreviousClose')

            if live_price is None:
                return float(fallback_price), float(fallback_change)

            live_price = float(live_price)
            if prev_close is not None and float(prev_close) > 0:
                live_change = ((live_price - float(prev_close)) / float(prev_close)) * 100
            else:
                live_change = fallback_change
            return float(live_price), float(live_change)
        except Exception:
            return float(fallback_price), float(fallback_change)

    @classmethod
    def get_screener_data(cls, timeframe: str = "1D", force: bool = False) -> List[Dict]:
        normalized_tf = "1D" if timeframe == "Daily" else timeframe
        
        # 0. Check Cache — only serve non-empty results to avoid stale empty lists
        from app.services.market_status_service import MarketStatusService
        market_status = MarketStatusService.get_market_status()
        ttl = cls.CACHE_TTL if market_status["mode"] in ["OPEN", "PRE_MARKET"] else 3600 * 12

        current_time = float(time.time())
        if not force and (cls._cache.get("data") is not None and 
            cls._cache.get("data") and   # Must have results
            cls._cache.get("timeframe") == normalized_tf and 
            (current_time - float(cls._cache.get("timestamp") or 0.0)) < ttl):
            print(f"DEBUG: Serving screener data from memory cache for {normalized_tf}")
            return {
                "hits": cls._cache["data"],
                "sector_concentration": cls._cache.get("sector_concentration", []),
                "source": "cached"
            }

        config = cls.TIMEFRAME_MAP.get(normalized_tf, cls.TIMEFRAME_MAP["1D"])
        rule = cls.RULES_BY_TF.get(normalized_tf, cls.RULES_BY_TF["1D"])

        sector_map = {
            sector_key: symbols
            for sector_key, symbols in ConstituentService.SECTOR_CONSTITUENTS.items()
            if symbols
        }
        all_symbols = sorted({symbol for symbols in sector_map.values() for symbol in symbols})
        if not all_symbols:
            return []

        sector_indices = [
            str(cls.SECTOR_INDEX_BY_KEY.get(str(sector), ""))
            for sector in sector_map.keys()
            if str(sector) in cls.SECTOR_INDEX_BY_KEY
        ]

        # 1. Fetch data for all symbols and sectors using MarketDataService (Batch)
        print(f"DEBUG: Fetching {len(all_symbols)} stocks and {len(sector_indices)} sectors for Screener via Batch...", flush=True)
        stock_batch_data = {}
        sector_batch_data = {}
        
        from app.services.market_data import MarketDataService
        
        # Combine all targets for a single batch pass
        all_targets = all_symbols + sector_indices
        
        last_err = None
        try:
            batch_results = MarketDataService.get_ohlcv_batch(all_targets, normalized_tf, count=200)
            
            for sym, res in batch_results.items():
                df, currency, err, source = res
                if err: last_err = err # Capture last error for diagnostic
                if df is not None and not df.empty:
                    # columns and timezones are handled by batch method
                    if sym in sector_indices:
                        sector_batch_data[sym] = df
                    else:
                        stock_batch_data[sym] = df
        except Exception as e:
            print(f"ERROR: Batch data fetch failed in screener: {e}", flush=True)
            last_err = str(e)

        if not stock_batch_data:
            is_expired = last_err and "Fyers Token Expired" in str(last_err)
            print(f"WARNING: No stock data fetched for screener (Expired: {is_expired}). Using fallback.", flush=True)
            fb_list = cls._load_fallback(normalized_tf)
            return {
                "hits": fb_list,
                "sector_concentration": cls._calculate_sector_concentration(fb_list),
                "source": "expired" if is_expired else "fallback",
                "message": last_err if is_expired else None
            }


        sector_by_symbol = {
            symbol: sector
            for sector, symbols in sector_map.items()
            for symbol in symbols
        }

        # Fetch sector rotation data to get current states for the hard gate
        sector_data, _ = SectorService.get_rotation_data(timeframe=normalized_tf, include_constituents=False)
        all_sector_states = {info.get("metrics", {}).get("state", "NEUTRAL") 
                             for info in sector_data.values()}
        # Relax sector gate to NEUTRAL if most sectors are NEUTRAL 
        # (can happen during initial boot or off-market hours)
        gate_states = ["LEADING", "IMPROVING"]
        if sum(1 for s in all_sector_states if s in gate_states) == 0:
            gate_states = ["LEADING", "IMPROVING", "NEUTRAL"]
            print("WARNING: No LEADING/IMPROVING sectors found. Relaxing gate to include NEUTRAL.")

        hits: List[Dict] = []
        for symbol in all_symbols:
            try:
                # 1. Fetch & Standardize DF
                raw_df = stock_batch_data.get(symbol)
                if raw_df is None or raw_df.empty:
                    continue
                
                symbol_df = raw_df.copy()
                symbol_df.columns = [c.lower() for c in symbol_df.columns]
                
                close = pd.to_numeric(symbol_df['close'], errors='coerce').dropna()
                volume = pd.to_numeric(symbol_df['volume'], errors='coerce').dropna()
                
                if close.empty or volume.empty:
                    continue

                # Handle after-hours (latest volume 0)
                latest_valid_idx = len(volume) - 1
                while latest_valid_idx >= 0 and volume.iloc[latest_valid_idx] == 0:
                    latest_valid_idx -= 1
                
                if latest_valid_idx < 0:
                    continue
                
                if latest_valid_idx < 5:
                    continue

                latest_price = float(close.iloc[latest_valid_idx])
                pct = close.pct_change() * 100
                latest_change = float(pct.iloc[latest_valid_idx]) if not pd.isna(pct.iloc[latest_valid_idx]) else 0.0
                
                avg_vol = volume.rolling(20, min_periods=5).mean()
                vol_ratio = (volume / avg_vol).replace([pd.NA, pd.NaT, np.inf, -np.inf], 0).fillna(0)
                volume_expansion = vol_ratio > rule.volume_threshold

                cond = (pct > rule.change_threshold) & volume_expansion
                hit_idx = cls._find_last_hit_index(cond, lookback_bars=rule.lookback_bars)
                if hit_idx is None:
                    continue

                hits1d, hits2d, hits3d = cls._compute_streak_flags(cond, hit_idx)
                
                sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
                sector_info = sector_data.get(sector_key, {})
                sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
                
                # Sector state is no longer a hard gate for hits (v1.5)
                # We allow all sectors and let the quality_score + UI filters decide visibility
                pass 

                # Calculate RS and Sector Return
                sector_return = 0.0
                rs_sector = 0.0
                s_acc_raw = 0.0
                stock_return = float(pct.iloc[hit_idx])
                
                if str(sector_key) in cls.SECTOR_INDEX_BY_KEY:
                    sector_symbol = str(cls.SECTOR_INDEX_BY_KEY.get(str(sector_key), ""))
                    sector_df = sector_batch_data.get(sector_symbol)
                    if sector_df is not None and not sector_df.empty:
                        sec_close_col = "Close" if "Close" in sector_df.columns else "close"
                        sector_close = pd.to_numeric(sector_df[sec_close_col], errors='coerce').dropna()
                        if len(sector_close) >= len(close):
                            # Align indices if possible or use simple positioning
                            sec_pct = sector_close.pct_change() * 100
                            sector_return = float(sec_pct.iloc[hit_idx]) if hit_idx < len(sec_pct) else 0.0
                            rs_sector = stock_return - sector_return
                            
                            # Series calculation for acceleration
                            s_rs = pct - sec_pct
                            if hit_idx < len(s_rs):
                                s_rs_diff = s_rs.diff()
                                s_acc_raw = float(s_rs_diff.iloc[hit_idx]) if not pd.isna(s_rs_diff.iloc[hit_idx]) else 0.0
                
                # --- STOCK RS GATE (LOCKED v1.0) ---
                if rs_sector <= 0:
                    continue

                # --- Forward 3-Day Performance (Daily TF Only) ---
                forward_return = None
                if normalized_tf in ["1D", "Daily"]:
                    if len(close) > hit_idx + 3:
                        entry_price = float(close.iloc[hit_idx])
                        future_price = float(close.iloc[hit_idx + 3])
                        forward_return = ((future_price - entry_price) / entry_price) * 100

                # Technical Analysis Metrics
                vwap = cls._calculate_vwap(symbol_df)
                is_breakout = cls._is_breakout(symbol_df)
                price_above_vwap = latest_price > vwap
                vol_ratio_val = float(vol_ratio.iloc[hit_idx])

                # --- INTELLIGENCE LAYER: EARLY BREAKOUT DETECTION ---
                early_tag = None
                early_tooltip = None
                early_details = {}
                try:
                    from app.engine.early_breakout import detect_early_breakout
                    eb = detect_early_breakout(symbol_df)
                    if eb.signal:
                        early_tag = "EARLY_SETUP"
                        early_tooltip = eb.tooltip
                        early_details = eb.details or {}
                except Exception:
                    pass
                
                stock_active = True 
                
                # Volatility check
                high_col = "High" if "High" in symbol_df.columns else "high"
                low_col = "Low" if "Low" in symbol_df.columns else "low"
                ranges = (symbol_df[high_col] - symbol_df[low_col])
                curr_range = float(ranges.iloc[-1])
                avg_range = float(ranges.rolling(20).mean().iloc[-1])
                vol_high = bool(curr_range > (avg_range * 2.0))
                
                # Phase 4 Metrics
                structure_bias = InsightEngine.get_structure_bias(symbol_df)
                atr_expansion = min(3.0, curr_range / avg_range) if avg_range > 0 else 1.0
                rr_heuristic = 2.0 
                
                quality_score = cls.calculate_quality_score(
                    rs_sector=rs_sector,
                    stock_acc=s_acc_raw,
                    vol_ratio=vol_ratio_val,
                    structure_bias=structure_bias,
                    rr=rr_heuristic,
                    atr_expansion=atr_expansion
                )
                
                # Compute Tags
                entry_tag = cls.get_entry_tag(quality_score, sector_state, stock_active)
                
                h20 = symbol_df[high_col].rolling(20).max().iloc[-2] if len(symbol_df) >= 21 else symbol_df[high_col].iloc[0]
                is_breakout_actual = latest_price > h20
                false_breakout = is_breakout_actual and (vol_ratio_val < 1.5 or not price_above_vwap)
                
                if false_breakout:
                    if entry_tag in ["ENTRY_READY", "STRONG_ENTRY"]:
                        entry_tag = "WATCHLIST"
                
                momentum_strength = cls.get_momentum_strength(quality_score, vol_ratio_val, s_acc_raw)
                exit_tag = cls.get_exit_tag(latest_price < vwap, vol_ratio_val < 0.8, sector_state)
                risk_level = cls.get_risk_level(sector_state, vol_ratio_val, vol_high)

                if latest_change <= -2 and sector_state != "LEADING":
                    if entry_tag == "ENTRY_READY":
                        entry_tag = "WATCHLIST"

                market_regime = "NEUTRAL"
                if market_regime == "WEAK":
                    if entry_tag == "STRONG_ENTRY":
                        entry_tag = "ENTRY_READY"
                    elif entry_tag == "ENTRY_READY":
                        entry_tag = "WATCHLIST"

                phase, session_quality = cls.get_session_tag()
                stop_distance_pct = 1.5 
                ru = cls.get_risk_units(sector_state, entry_tag, risk_level, stop_distance_pct)
                
                if session_quality == "AVOID":
                    ru = 0

                display_symbol = symbol.replace(".NS", "").replace(".BO", "")
                hit_ts = close.index[hit_idx]

                hits.append(
                    {
                        "symbol": str(display_symbol),
                        "price": float(round(float(latest_price) * 100.0) / 100.0),
                        "change": float(round(float(latest_change) * 100.0) / 100.0),
                        "hitChange": float(round(float(stock_return) * 100.0) / 100.0),
                        "forward3dReturn": float(round(float(forward_return) * 100.0) / 100.0) if forward_return is not None else None,
                        "hits1d": bool(hits1d),
                        "hits2d": bool(hits2d),
                        "hits3d": bool(hits3d),
                        "volRatio": float(round(float(vol_ratio_val) * 100.0) / 100.0),
                        "volumeShocker": float(round(float(vol_ratio_val) * 100.0) / 100.0),
                        "stockActive": bool(volume_expansion.iloc[hit_idx]),
                        "volumeExpansion": bool(volume_expansion.iloc[hit_idx]),
                        "sector": str(str(sector_key).replace("NIFTY_", "").replace("_", " ")),
                        "sectorKey": str(sector_key),
                        "sectorState": str(sector_state),
                        "sectorReturn": float(int(float(sector_return) * 10000.0 + 0.5) / 10000.0),
                        "rsSector": float(int(float(rs_sector) * 10000.0 + 0.5) / 10000.0),
                        "tradeReady": bool(hits2d or hits3d),
                        "confidence": cls.get_confidence_grade(quality_score),
                        "grade": cls.get_confidence_grade(quality_score),
                        "entryTag": str(entry_tag),
                        "exitTag": str(exit_tag),
                        "riskLevel": str(risk_level),
                        "riskUnits": float(ru),
                        "session": {
                            "phase": str(phase),
                            "quality": str(session_quality)
                        },
                        "technical": {
                            "vwap": float(int(float(vwap) * 100.0 + 0.5) / 100.0),
                            "isBreakout": bool(is_breakout),
                            "isFalseBreakout": bool(false_breakout),
                            "aboveVWAP": bool(price_above_vwap),
                            "volHigh": bool(vol_high),
                            "stopDistance": float(int(float(stop_distance_pct) * 100.0 + 0.5) / 100.0),
                            "qualityScore": float(int(float(quality_score) * 100.0 + 0.5) / 100.0),
                            "structureBias": str(structure_bias),
                            "atrExpansion": float(int(float(atr_expansion) * 100.0 + 0.5) / 100.0),
                            "institutionalActivity": cls.get_smart_money_tier(vol_ratio_val),
                            "momentumStrength": str(momentum_strength),
                            "earlyBreakoutSignal": bool(early_tag == "EARLY_SETUP"),
                            "earlyTag": early_tag,
                            "earlyTooltip": early_tooltip,
                            "earlyDetails": early_details,
                            "setupType": cls._identify_setup_type(symbol_df, vol_ratio_val),
                        },
                        "asOf": str(close.index[latest_valid_idx]),
                        "hitAsOf": str(hit_ts),
                        "isLatestSession": bool(hit_idx == latest_valid_idx),
                    }
                )
            except Exception as e:
                print(f"ERROR SCREENER: Unexpected error for {symbol}: {e}")
                import traceback
                traceback.print_exc()
                continue

        if hits:
            try:
                # Optimized: We Skip batch real-time minute download to save time and prevent hangs.
                # The daily batch data already has latest session info.
                pass 
            except Exception as e:
                print(f"Batch real_time verify skipped/failed: {e}")

        hits.sort(key=lambda row: (row["hits3d"], row["hits2d"], row["rsSector"], row["volRatio"]), reverse=True)
        
        # Update Cache only if hits exist, otherwise keep previous valid data
        if hits:
            cls._cache = {
                "data": hits,
                "timestamp": time.time(),
                "timeframe": normalized_tf,
                "sector_concentration": cls._calculate_sector_concentration(hits)
            }
            # Archive Signals (V6: Persistent historical signals)
            if normalized_tf == "1D":
                SignalArchiveService.archive_signals(hits)
            
            # Save to Fallback
            cls._save_fallback(hits, normalized_tf)
        else:
            # If hits is empty (e.g., market closed/no volume), try serving the last valid scan
            fallback_data = cls._load_fallback(normalized_tf)
            if fallback_data:
                print(f"DEBUG: 0 hits found live, returning fallback EOD data for {normalized_tf}")
                return {
                    "hits": fallback_data,
                    "sector_concentration": cls._calculate_sector_concentration(fallback_data),
                    "source": "fallback"
                }

        
        return {
            "hits": hits,
            "sector_concentration": cls._calculate_sector_concentration(hits) if hits else [],
            "source": "live"
        }


    @classmethod
    def get_early_breakout_setups(cls, timeframe: str = "1D", limit: int = 5) -> List[Dict]:
        """
        Returns early accumulation candidates (pre-breakout) as an additive intelligence layer.
        This does NOT modify existing screener signals; it's a separate output.
        """
        normalized_tf = "1D" if timeframe == "Daily" else timeframe
        
        # 0. Check Cache
        current_time = float(time.time())
        if hasattr(cls, '_early_cache') and cls._early_cache.get("data") is not None:
            if cls._early_cache.get("timeframe") == normalized_tf and (current_time - float(cls._early_cache.get("timestamp", 0.0))) < 300: # 5 min cache
                print(f"DEBUG: Serving {len(cls._early_cache['data'])} early setups from memory cache.")
                return cls._early_cache["data"]

        config = cls.TIMEFRAME_MAP.get(normalized_tf, cls.TIMEFRAME_MAP["1D"])

        sector_map = {
            sector_key: symbols
            for sector_key, symbols in ConstituentService.SECTOR_CONSTITUENTS.items()
            if symbols
        }
        all_symbols = sorted({symbol for symbols in sector_map.values() for symbol in symbols})
        if not all_symbols:
            return []

        sector_by_symbol = {
            symbol: sector
            for sector, symbols in sector_map.items()
            for symbol in symbols
        }

        sector_data, _ = SectorService.get_rotation_data(timeframe=normalized_tf, include_constituents=False)
        all_sector_states = {info.get("metrics", {}).get("state", "NEUTRAL") for info in sector_data.values()}
        gate_states = ["LEADING", "IMPROVING"]
        if sum(1 for s in all_sector_states if s in gate_states) == 0:
            gate_states = ["LEADING", "IMPROVING", "NEUTRAL"]

        filtered_symbols = []
        for symbol in all_symbols:
            sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
            sector_info = sector_data.get(sector_key, {})
            sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
            if sector_state in gate_states:
                filtered_symbols.append(symbol)

        if not filtered_symbols:
            return []

        # 1. Fetch data for filtered symbols ONLY using MarketDataService
        print(f"DEBUG: Fetching data for {len(filtered_symbols)} early setups (filtered from {len(all_symbols)}) via Batch...")
        stock_batch_data = {}
        from app.services.market_data import MarketDataService
        
        try:
            batch_results = MarketDataService.get_ohlcv_batch(filtered_symbols, normalized_tf)
            for symbol, res in batch_results.items():
                df, currency, err, source = res
                if df is not None and not df.empty:
                    stock_batch_data[symbol] = df
        except Exception as e:
            print(f"ERROR: Failed to fetch batch data for early setups: {e}")

        if not stock_batch_data:
            return []

        from app.engine.early_breakout import detect_early_breakout

        setups: List[Dict] = []
        for symbol in filtered_symbols:
            try:
                raw_df = stock_batch_data.get(symbol)
                if raw_df is None or raw_df.empty:
                    continue
                sdf = raw_df.copy()
                sdf.columns = [c.lower() for c in sdf.columns]

                sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
                sector_info = sector_data.get(sector_key, {})
                sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
                
                eb = detect_early_breakout(sdf)
                if not eb.signal:
                    continue

                close = float(pd.to_numeric(sdf["close"], errors="coerce").dropna().iloc[-1])
                vol_ratio = float(eb.details.get("volRatio20", 0.0))
                range_pct = float(eb.details.get("rangePct", 0.0))

                display_symbol = str(symbol).replace(".NS", "").replace(".BO", "")
                
                # Rounding workaround for restrictive round() overload
                price_val = float(int(float(close) * 100.0 + 0.5) / 100.0)
                
                setups.append({
                    "symbol": str(display_symbol),
                    "price": price_val,
                    "sector": str(str(sector_key).replace("NIFTY_", "").replace("_", " ")),
                    "sectorKey": str(sector_key),
                    "sectorState": str(sector_state),
                    "tag": "EARLY_SETUP",
                    "tooltip": str(eb.tooltip),
                    "details": eb.details,
                    "volRatio": float(vol_ratio),
                    "rangePct": float(range_pct),
                })
            except Exception:
                continue

        setups.sort(key=lambda x: (float(x.get("rangePct", 99.0)), -float(x.get("volRatio", 0.0))), reverse=False)
        num_setups = int(max(1, int(limit)))
        final_setups = [setups[i] for i in range(min(len(setups), num_setups))]
        
        if not hasattr(cls, '_early_cache'):
            cls._early_cache = {}
        cls._early_cache["data"] = final_setups
        cls._early_cache["timestamp"] = time.time()
        cls._early_cache["timeframe"] = normalized_tf
        
        return final_setups

    @classmethod
    def get_next_session_watchlist(cls, timeframe: str = "1D") -> Dict:
        """
        Compiles the Next Session Watchlist containing:
        - Strong Sectors to focus on
        - Weak Sectors to avoid
        - Key Breakout Levels (Early Setups)
        """
        # 1. Get Sectors
        from app.services.sector_service import SectorService
        sector_data, _ = SectorService.get_rotation_data(timeframe=timeframe, include_constituents=False)
        
        strong_sectors = []
        avoid_sectors = []
        
        for name, info in sector_data.items():
            state = info.get("metrics", {}).get("state", "NEUTRAL")
            clean_name = str(name).replace("NIFTY_", "").replace("_", " ")
            if state in ["LEADING", "IMPROVING"]:
                strong_sectors.append(clean_name)
            elif state in ["LAGGING", "WEAKENING"]:
                avoid_sectors.append(clean_name)
                
        # 2. Get Breakout Candidates (Early Setups)
        breakout_candidates = cls.get_early_breakout_setups(timeframe=timeframe, limit=8)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "strong_sectors": strong_sectors,
            "avoid_sectors": avoid_sectors,
            "breakout_candidates": breakout_candidates
        }

    @classmethod
    def _save_fallback(cls, data: List[Dict], timeframe: str):
        if not data:
            return
        try:
            import json
            from pathlib import Path
            fallback_path = Path(__file__).parent.parent / "data" / "screener_fallback.json"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback_path, "w") as f:
                json.dump({
                    "data": data,
                    "timestamp": time.time(),
                    "timeframe": timeframe
                }, f)
        except Exception as e:
            print(f"Error saving screener fallback: {e}")

    @classmethod
    def _load_fallback(cls, timeframe: str) -> List[Dict]:
        try:
            import json
            from pathlib import Path
            fallback_path = Path(__file__).parent.parent / "data" / "screener_fallback.json"
            if fallback_path.exists():
                with open(fallback_path, "r") as f:
                    stored = json.load(f)
                    if stored.get("timeframe") == timeframe:
                        print(f"DEBUG: Loaded screener fallback for {timeframe}")
                        return stored["data"]
            else:
                print(f"DEBUG: Screener fallback file not found for {timeframe}")
        except Exception as e:
            print(f"Error loading screener fallback: {e}")
        return []

    @staticmethod
    def calculate_performance_stats(hits: list) -> dict:
        """
        V6: System Performance is now calculated from historical archival data 
        rather than just current hits.
        """
        return SignalArchiveService.get_performance_metrics()
    @classmethod
    def get_market_summary_data(cls, timeframe: str = "1D") -> Dict:
        """Aggregates data for the Daily AI Market Summary pack."""
        try:
            # 1. Market Return (NIFTY 50)
            market_return = 0.0
            # 1. Market Return (NIFTY 50) using MarketDataService
            market_return = 0.0
            try:
                from app.services.market_data import MarketDataService
                n_df, _, _, _ = MarketDataService.get_ohlcv("^NSEI", timeframe)
                if n_df is not None and len(n_df) >= 2:
                    n_close = n_df["close" if "close" in n_df.columns else "Close"]
                    market_return = float(((n_close.iloc[-1] - n_close.iloc[-2]) / n_close.iloc[-2]) * 100)
            except Exception as e:
                print(f"Warning: NIFTY fetch failed: {e}")

            # Fetch sector data for breadth calculation (Optimized: No constituents needed for breadth)
            from app.services.sector_service import SectorService
            sector_data, alerts = SectorService.get_rotation_data(timeframe=timeframe, include_constituents=False)
            
            # IMPORTANT: Attach sector names for frontend rendering (UI-only enhancement).
            # SectorService returns a dict keyed by sector name; values don't include the key,
            # which causes "[object Object]" when the UI tries to render leadership lists.
            sectors = []
            if isinstance(sector_data, dict):
                for sector_key, payload in sector_data.items():
                    if not isinstance(payload, dict):
                        continue
                    sectors.append({
                        "name": sector_key.replace("NIFTY_", ""),
                        "sectorKey": sector_key,
                        **payload
                    })

            leading = [s for s in sectors if s.get('metrics', {}).get('state') == 'LEADING']
            weakening = [s for s in sectors if s.get('metrics', {}).get('state') == 'WEAKENING']
            improving = [s for s in sectors if s.get('metrics', {}).get('state') == 'IMPROVING']
            lagging = [s for s in sectors if s.get('metrics', {}).get('state') == 'LAGGING']
            
            total_sectors = len(sector_data) if sector_data else 9 # type: ignore
            leading_count = len(list(leading))  # type: ignore
            breadth_score = (leading_count / total_sectors) # Return 0-1 for frontend consistency, though frontend handles 0-100 too

            # Improvement 1: Enhanced Market Regime Filter
            if breadth_score >= 40:
                market_regime = "RISK-ON"
            elif breadth_score >= 20:
                market_regime = "NEUTRAL"
            else:
                market_regime = "RISK-OFF"

            # Global cues (positive if market return > 0, simple heuristic)
            global_positive = market_return > 0
            gift_nifty_positive = market_return > 0  # Simplified proxy

            # 4. Top Stocks
            screener_res = cls.get_screener_data(timeframe=timeframe)
            hits = screener_res.get("hits", []) if isinstance(screener_res, dict) else screener_res
            performance = cls.calculate_performance_stats(hits)
            top_stocks = []
            for h in hits:
                # Backend filtering for summary: Only keep those that are likely high confidence
                quality_val = h.get("technical", {}).get("qualityScore", 0)
                conf_grade = h.get("grade") or h.get("confidence") or cls.get_confidence_grade(quality_val)
                conf_score = h.get("confidence") if isinstance(h.get("confidence"), (int, float)) else quality_val
                
                top_stocks.append({
                    "symbol": h.get("symbol", "N/A"),
                    "sector": h.get("sector", "N/A"),
                    "grade": conf_grade,
                    "confidence": conf_score,
                    "entryTag": h.get("entryTag", "WATCHLIST"),
                    "institutionalActivity": h.get("technical", {}).get("institutionalActivity", "NONE"),
                    "momentumStrength": h.get("technical", {}).get("momentumStrength", "WEAK")
                })

            # --- Momentum Leaders ---
            top_sector = None
            if sector_data:
                # Sort sectors by rotationScore descending
                sorted_sectors = sorted(
                    sector_data.items(),  # type: ignore
                    key=lambda x: x[1].get('metrics', {}).get('rotationScore', 0),
                    reverse=True
                )
                if sorted_sectors:
                    top_sector = {
                        "name": sorted_sectors[0][0].replace("NIFTY_", ""),
                        "rotationScore": sorted_sectors[0][1].get('metrics', {}).get('rotationScore', 0),
                        "state": sorted_sectors[0][1].get('metrics', {}).get('state', 'NEUTRAL')
                    }

            top_quality_stock = None
            top_volume_stock = None
            if hits:
                # Sort for quality
                sorted_hits_quality = sorted(
                    hits,
                    key=lambda x: x.get('technical', {}).get('qualityScore', 0),
                    reverse=True
                )
                top_quality_stock = {
                    "symbol": sorted_hits_quality[0]['symbol'],
                    "qualityScore": sorted_hits_quality[0]['technical'].get('qualityScore', 0),
                    "sector": sorted_hits_quality[0].get('sector', 'N/A'),
                    "sectorState": sorted_hits_quality[0].get('sectorState', 'NEUTRAL'),
                    "institutionalActivity": sorted_hits_quality[0].get('technical', {}).get('institutionalActivity', 'NONE')
                }

                # Sort for volume
                sorted_hits_vol = sorted(
                    hits,
                    key=lambda x: x.get('volRatio', 0),
                    reverse=True
                )
                top_volume_stock = {
                    "symbol": sorted_hits_vol[0]['symbol'],
                    "volRatio": sorted_hits_vol[0]['volRatio']
                }

            # --- Simplified Market Summary (Decision-Driven) ---
            bias = "NEUTRAL"
            if market_regime == "RISK-ON": bias = "BULLISH"
            elif market_regime == "RISK-OFF": bias = "BEARISH"
            
            strategy_suggestion = "Wait for setups"
            if bias == "BULLISH": strategy_suggestion = "Focus on LEADING sector breakouts"
            elif bias == "BEARISH": strategy_suggestion = "Avoid fresh longs, trail stops"
            else: strategy_suggestion = "Range-bound play, focus on mean reversion"

            summary = {
                "marketBias": bias,
                "marketReturn": float(int(float(market_return) * 100.0 + 0.5) / 100.0),
                "marketRegime": str(market_regime),
                "suggestedStrategy": strategy_suggestion,
                "strongSectors": [s.get("name") for s in leading] + [s.get("name") for s in improving],
                "weakSectors": [s.get("name") for s in lagging] + [s.get("name") for s in weakening],
                "breadthScore": float(int(float(breadth_score) * 100.0 + 0.5) / 100.0),
                "topStocks": [top_stocks[i] for i in range(min(len(top_stocks), 5))],
                "systemPerformance": dict(performance),
                "momentumLeaders": {
                    "topSector": top_sector,
                    "topQualityStock": top_quality_stock,
                    "topVolumeStock": top_volume_stock
                }
            }

            return summary
        except Exception as e:
            print(f"Error generating market summary: {e}")
            return {
                "marketReturn": 0.0,
                "prevMarketReturn": 0.0,
                "globalCuesPositive": False,
                "giftNiftyPositive": False,
                "leadingSectors": [],
                "weakeningSectors": [],
                "improvingSectors": [],
                "laggingSectors": [],
                "topStocks": [],
                "systemPerformance": {
                    "totalSignals": 0,
                    "winRate": 0,
                    "avgReturn": 0,
                    "sectorAccuracy": {}
                }
            }
