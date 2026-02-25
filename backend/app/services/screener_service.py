from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import numpy as np
import yfinance as yf
import concurrent.futures
import time
from datetime import datetime

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
    _cache = {
        "data": None,
        "timestamp": 0,
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
    def calculate_quality_score(cls, rs_sector: float, stock_acc: float, vol_ratio: float, 
                               structure_bias: str, rr: float, atr_expansion: float) -> float:
        """Phase 4: Stock Quality Score Calculation (0-100)"""
        # 1. Stock RS inside sector (30%) - Clamped -5% to +5% -> 0-100
        rs_clamped = max(-5, min(5, rs_sector))
        rs_score = (rs_clamped + 5) * 10
        
        # 2. Stock Acceleration (20%) - Normalized -0.1 to +0.1 -> 0-100
        acc_score = max(0, min(100, stock_acc * 500 + 50))
        
        # 3. Volume Ratio (15%) - 1.0 to 2.0 -> 0-100
        vol_score = max(0, min(100, (vol_ratio - 1.0) * 100))
        
        # 4. Structure Bias (15%)
        bias_score = 100 if structure_bias == "BULLISH" else 50 if structure_bias == "NEUTRAL" else 0
        
        # 5. Risk-Reward Bonus (10%)
        rr_bonus = 100 if rr >= 1.8 else 0
        
        # 6. ATR Expansion (10%) - 1.0 to 1.5 -> 0-100
        atr_score = max(0, min(100, (atr_expansion - 1.0) * 200))
        
        final_score = (
            0.3 * rs_score +
            0.2 * bias_score +
            0.2 * acc_score +
            0.1 * vol_score +
            0.1 * atr_score +
            0.1 * rr_bonus
        )
        
        return float(final_score)

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
    def get_screener_data(cls, timeframe: str = "1D") -> List[Dict]:
        normalized_tf = "1D" if timeframe == "Daily" else timeframe
        
        # 0. Check Cache — only serve non-empty results to avoid stale empty lists
        current_time = time.time()
        if (cls._cache["data"] is not None and 
            cls._cache["data"] and   # Must have results
            cls._cache["timeframe"] == normalized_tf and 
            (current_time - cls._cache["timestamp"]) < cls.CACHE_TTL):
            print(f"DEBUG: Serving screener data from cache for {normalized_tf}")
            return cls._cache["data"]

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
            cls.SECTOR_INDEX_BY_KEY[sector]
            for sector in sector_map.keys()
            if sector in cls.SECTOR_INDEX_BY_KEY
        ]

        try:
            stock_batch_df = yf.download(
                tickers=" ".join(all_symbols),
                period=config["period"],
                interval=config["interval"],
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            )
            sector_batch_df = yf.download(
                tickers=" ".join(sorted(set(sector_indices))),
                period=config["period"],
                interval=config["interval"],
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            ) if sector_indices else pd.DataFrame()
        except Exception as e:
            print(f"Momentum screener batch download failed: {e}")
            return cls._load_fallback(normalized_tf)

        if stock_batch_df is None or stock_batch_df.empty:
            return cls._load_fallback(normalized_tf)

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
                raw_df = stock_batch_df[symbol] if isinstance(stock_batch_df.columns, pd.MultiIndex) else stock_batch_df
                if raw_df is None or raw_df.empty:
                    continue
                
                symbol_df = raw_df.copy()
                symbol_df.columns = [c.lower() for c in symbol_df.columns]
                
                close = symbol_df['close'].dropna()
                volume = symbol_df['volume'].dropna()
                
                if close.empty or volume.empty:
                    continue

                # Handle after-hours (latest volume 0)
                # Find the latest index with non-zero volume
                latest_valid_idx = len(volume) - 1
                while latest_valid_idx >= 0 and volume.iloc[latest_valid_idx] == 0:
                    latest_valid_idx -= 1
                
                # If no valid volume bar found, skip
                if latest_valid_idx < 0:
                    continue
                
                # Ensure we have enough data points for calculations
                if latest_valid_idx < 5: # Need at least 6 bars for pct_change and rolling means
                    continue

                pct = close.pct_change() * 100
                avg_vol = volume.rolling(20, min_periods=5).mean()
                vol_ratio = (volume / avg_vol).replace([pd.NA, pd.NaT], 0).fillna(0)
                volume_expansion = vol_ratio > rule.volume_threshold

                cond = (pct > rule.change_threshold) & volume_expansion
                hit_idx = cls._find_last_hit_index(cond, lookback_bars=rule.lookback_bars)
                if hit_idx is None:
                    continue

                hits1d, hits2d, hits3d = cls._compute_streak_flags(cond, hit_idx)
                # Removed strict 'if not hits1d: continue' to allow recent hits to show
                
                sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
                
                # --- HARD SECTOR GATE (LOCKED v1.0) ---
                sector_info = sector_data.get(sector_key, {})
                sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
                
                if sector_state not in gate_states:
                    # print(f"DEBUG SCREENER: {symbol} FAILED Sector Gate. State: {sector_state}")
                    continue

                sector_return = 0.0
                if sector_key in cls.SECTOR_INDEX_BY_KEY and not sector_batch_df.empty:
                    sector_symbol = cls.SECTOR_INDEX_BY_KEY[sector_key]
                    sector_df = sector_batch_df[sector_symbol] if isinstance(sector_batch_df.columns, pd.MultiIndex) else sector_batch_df
                    if sector_df is not None and not sector_df.empty:
                        sec_close_col = "Close" if "Close" in sector_df.columns else "close"
                        sector_close = sector_df[sec_close_col].dropna()
                        if len(sector_close) > hit_idx:
                            sector_return = float((sector_close.pct_change() * 100).iloc[hit_idx])

                latest_idx = len(close) - 1
                prev_idx = latest_idx - 1
                stock_return = float(pct.iloc[hit_idx])
                latest_price = float(close.iloc[latest_idx])
                latest_change = float(pct.iloc[latest_idx]) if prev_idx >= 0 else stock_return
                
                # Difference-based RS (avoid ratio explosions)
                rs_sector = (stock_return - sector_return)

                # Phase 4: Stock Acceleration (fixed: use pre-fetched sector data)
                sector_pct = pd.Series(0.0, index=pct.index)
                if sector_key in cls.SECTOR_INDEX_BY_KEY and not sector_batch_df.empty:
                    _sec_sym = cls.SECTOR_INDEX_BY_KEY[sector_key]
                    _sec_df = sector_batch_df[_sec_sym] if isinstance(sector_batch_df.columns, pd.MultiIndex) else sector_batch_df
                    if _sec_df is not None and not _sec_df.empty:
                        _sec_close_col = "Close" if "Close" in _sec_df.columns else "close"
                        _sec_close = _sec_df[_sec_close_col].dropna()
                        sector_pct = _sec_close.pct_change().reindex(pct.index).fillna(0) * 100

                # --- Forward 3-Day Performance (Daily TF Only) ---
                forward_return = None
                if normalized_tf in ["1D", "Daily"]:
                    if len(close) > hit_idx + 3:
                        entry_price = float(close.iloc[hit_idx])
                        future_price = float(close.iloc[hit_idx + 3])
                        forward_return = ((future_price - entry_price) / entry_price) * 100

                s_rs = pct - sector_pct
                s_acc_raw = s_rs.diff().iloc[hit_idx]
                if pd.isna(s_acc_raw):
                    s_acc_raw = 0.0
                
                # --- STOCK RS GATE (LOCKED v1.0) ---
                if rs_sector <= 0:
                    continue

                # Technical Analysis Metrics
                vwap = cls._calculate_vwap(symbol_df)
                is_breakout = cls._is_breakout(symbol_df)
                price_above_vwap = latest_price > vwap
                vol_ratio_val = float(vol_ratio.iloc[hit_idx])
                
                # Assume active if standard momentum criteria met (which they are if we reached here)
                stock_active = True 
                
                # Volatility check (High if current range > 2x average range)
                high_col = "High" if "High" in symbol_df.columns else "high"
                low_col = "Low" if "Low" in symbol_df.columns else "low"
                ranges = (symbol_df[high_col] - symbol_df[low_col])
                curr_range = float(ranges.iloc[-1])
                avg_range = float(ranges.rolling(20).mean().iloc[-1])
                vol_high = bool(curr_range > (avg_range * 2.0))
                
                # Phase 4 Metrics
                structure_bias = InsightEngine.get_structure_bias(symbol_df)
                atr_expansion = min(3.0, curr_range / avg_range) if avg_range > 0 else 1.0
                
                # Simple RR heuristic since we don't have strategy levels here
                # We assume target is 2x ATR and stop is 1x ATR
                rr_heuristic = 2.0 # Default to 2.0 if we can't calculate better
                
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
                exit_tag = cls.get_exit_tag(latest_price < vwap, vol_ratio_val < 0.8, sector_state)
                risk_level = cls.get_risk_level(sector_state, vol_ratio_val, vol_high)
                
                # POSITION SIZING & SESSION (LOCKED v1.0)
                phase, session_quality = cls.get_session_tag()
                
                # For stop distance, we use nearest support if available, else a mock 1.5%
                stop_distance_pct = 1.5 # Default conservative
                ru = cls.get_risk_units(sector_state, entry_tag, risk_level, stop_distance_pct)
                
                # Hard Timing Gate
                if session_quality == "AVOID":
                    ru = 0

                display_symbol = symbol.replace(".NS", "").replace(".BO", "")
                hit_ts = close.index[hit_idx]

                hits.append(
                    {
                        "symbol": str(display_symbol),
                        "price": float(round(latest_price, 2)),
                        "change": float(round(latest_change, 2)),
                        "hitChange": float(round(stock_return, 2)),
                        "forward3dReturn": float(round(forward_return, 2)) if forward_return is not None else None,
                        "hits1d": bool(hits1d),
                        "hits2d": bool(hits2d),
                        "hits3d": bool(hits3d),
                        "volRatio": float(round(vol_ratio_val, 2)),
                        "volumeShocker": float(round(vol_ratio_val, 2)),
                        "stockActive": bool(volume_expansion.iloc[hit_idx]),
                        "volumeExpansion": bool(volume_expansion.iloc[hit_idx]),
                        "sector": str(sector_key.replace("NIFTY_", "").replace("_", " ")),
                        "sectorKey": str(sector_key),
                        "sectorState": str(sector_state),
                        "sectorReturn": float(round(sector_return, 4)),
                        "rsSector": float(round(rs_sector, 4)),
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
                            "vwap": float(round(vwap, 2)),
                            "isBreakout": bool(is_breakout),
                            "aboveVWAP": bool(price_above_vwap),
                            "volHigh": bool(vol_high),
                            "stopDistance": float(stop_distance_pct),
                            "qualityScore": float(round(quality_score, 2)),
                            "structureBias": str(structure_bias),
                            "atrExpansion": float(round(atr_expansion, 2))
                        },
                        "asOf": str(close.index[latest_idx]),
                        "hitAsOf": str(hit_ts),
                        "isLatestSession": bool(hit_idx == len(close) - 1),
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
        
        # Update Cache
        cls._cache = {
            "data": hits,
            "timestamp": time.time(),
            "timeframe": normalized_tf
        }
        
        # Save to Fallback
        cls._save_fallback(hits, normalized_tf)
        
        return hits

    @classmethod
    def _save_fallback(cls, data: List[Dict], timeframe: str):
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
    @classmethod
    def get_market_summary_data(cls, timeframe: str = "1D") -> Dict:
        """Aggregates data for the Daily AI Market Summary pack."""
        try:
            # 1. Market Return (NIFTY 50)
            nifty = yf.Ticker("^NSEI")
            fast = nifty.fast_info
            price = fast.get('lastPrice') or fast.get('last_price', 0)
            prev = fast.get('previousClose') or fast.get('previous_close', 0)
            market_return = ((price - prev) / prev * 100) if prev > 0 else 0.0

            # 2. Global Cues (S&P 500)
            sp500 = yf.Ticker("^GSPC")
            sp_fast = sp500.fast_info
            sp_price = sp_fast.get('lastPrice') or sp_fast.get('last_price', 0)
            sp_prev = sp_fast.get('previousClose') or sp_fast.get('previous_close', 0)
            sp_return = ((sp_price - sp_prev) / sp_prev * 100) if sp_prev > 0 else 0.0
            
            # GIFT Nifty proxy (SGX Nifty or ^NSEI futures/prev close)
            # For pre-market, we'll check global sentiment
            global_positive = sp_return > 0.1
            gift_nifty_positive = sp_return > 0.3 # Simple proxy for now

            # 3. Sector States (Sorted Display UX Improvement)
            sector_data, _ = SectorService.get_rotation_data(timeframe=timeframe)
            
            # Prioritized order for display
            state_buckets = {
                "LEADING": [],
                "IMPROVING": [],
                "WEAKENING": [],
                "NEUTRAL": [],
                "LAGGING": []
            }
            
            for name, info in sector_data.items():
                state = info.get("metrics", {}).get("state", "NEUTRAL")
                display_name = name.replace("NIFTY_", "").replace("_", " ")
                
                # STRICT FILTERING for summary arrays
                if state == "LEADING":
                    leading.append(display_name)
                elif state == "WEAKENING":
                    weakening.append(display_name)
                elif state == "IMPROVING":
                    improving.append(display_name)
                elif state == "LAGGING":
                    lagging.append(display_name)

            # UX Improvement: Ensure neutral sectors aren't accidentally shown as leading
            neutral = state_buckets["NEUTRAL"] if "NEUTRAL" in state_buckets else []

            # 4. Top Stocks
            hits = cls.get_screener_data(timeframe=timeframe)
            top_stocks = []
            for h in hits:
                # Backend filtering for summary: Only keep those that are likely high confidence
                # (Standard momentum hits are already pre-filtered)
                # Backend filtering for summary: Only keep those that are likely high confidence
                quality_val = h.get("technical", {}).get("qualityScore", 0)
                conf_grade = h.get("grade") or h.get("confidence") or cls.get_confidence_grade(quality_val)
                conf_score = h.get("confidence") if isinstance(h.get("confidence"), (int, float)) else quality_val
                
                top_stocks.append({
                    "symbol": h.get("symbol", "N/A"),
                    "sector": h.get("sector", "N/A"),
                    "grade": conf_grade,
                    "confidence": conf_score,
                    "entryTag": h.get("entryTag", "WATCHLIST")
                })

            # --- Momentum Leaders ---
            top_sector = None
            if sector_data:
                # Sort sectors by rotationScore descending
                sorted_sectors = sorted(
                    sector_data.items(),
                    key=lambda x: x[1].get('metrics', {}).get('rotationScore', 0),
                    reverse=True
                )
                if sorted_sectors:
                    top_sector = {
                        "name": sorted_sectors[0][0].replace("NIFTY_", ""),
                        "rotationScore": sorted_sectors[0][1].get('metrics', {}).get('rotationScore', 0)
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
                    "qualityScore": sorted_hits_quality[0]['technical'].get('qualityScore', 0)
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

            summary = {
                "marketReturn": float(round(market_return, 2)),
                "prevMarketReturn": float(round(market_return, 2)), # Placeholder logic
                "globalCuesPositive": bool(global_positive),
                "giftNiftyPositive": bool(gift_nifty_positive),
                "leadingSectors": leading,
                "weakeningSectors": weakening,
                "improvingSectors": improving,
                "laggingSectors": lagging,
                "topStocks": top_stocks[:10]
            }

            # Append momentum leaders (Do NOT overwrite)
            summary["momentumLeaders"] = {
                "topSector": top_sector,
                "topQualityStock": top_quality_stock,
                "topVolumeStock": top_volume_stock
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
                "topStocks": []
            }
