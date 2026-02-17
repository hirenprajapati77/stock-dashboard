from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
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


@dataclass(frozen=True)
class MomentumRule:
    change_threshold: float
    volume_threshold: float


class ScreenerService:
    """Builds stock-intelligence rows for the trader intelligence panel."""

    TIMEFRAME_MAP: Dict[str, Dict[str, str]] = {
        "5m": {"interval": "5m", "period": "5d"},
        "15m": {"interval": "15m", "period": "5d"},
        "1D": {"interval": "1d", "period": "6mo"},
        "Daily": {"interval": "1d", "period": "6mo"},
    }

    RULES_BY_TF: Dict[str, MomentumRule] = {
        "5m": MomentumRule(change_threshold=0.7, volume_threshold=1.5),
        "15m": MomentumRule(change_threshold=0.9, volume_threshold=1.5),
        "1D": MomentumRule(change_threshold=2.0, volume_threshold=1.5),
        "Daily": MomentumRule(change_threshold=2.0, volume_threshold=1.5),
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
    CACHE_TTL = 300 # 5 minutes

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
    def get_entry_tag(cls, stock_active: bool, sector_state: str, price_above_vwap: bool, breakout_confirmed: bool, vol_ratio: float) -> str:
        """Entry Tagging Logic v1.0 (LOCKED)"""
        if sector_state == "LAGGING" or not stock_active:
            return "AVOID"
        
        # Best case
        if price_above_vwap and breakout_confirmed and vol_ratio >= 1.8:
            return "ENTRY_READY"
        
        # Good setup, wait
        if price_above_vwap and vol_ratio >= 1.5:
            return "WAIT"
            
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
        if entry_tag == "AVOID": return 0.0
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
        
        # 0. Check Cache
        current_time = time.time()
        if (cls._cache["data"] is not None and 
            cls._cache["timeframe"] == normalized_tf and 
            (current_time - cls._cache["timestamp"]) < cls.CACHE_TTL):
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
        sector_data, _ = SectorService.get_rotation_data(timeframe=normalized_tf)

        hits: List[Dict] = []
        for symbol in all_symbols:
            try:
                symbol_df = stock_batch_df[symbol] if isinstance(stock_batch_df.columns, pd.MultiIndex) else stock_batch_df
                if symbol_df is None or symbol_df.empty:
                    continue

                close_col = "Close" if "Close" in symbol_df.columns else "close"
                vol_col = "Volume" if "Volume" in symbol_df.columns else "volume"
                if close_col not in symbol_df.columns or vol_col not in symbol_df.columns:
                    continue

                close = symbol_df[close_col].dropna()
                volume = symbol_df[vol_col].dropna()
                if len(close) < 6 or len(volume) < 6:
                    continue

                pct = close.pct_change() * 100
                avg_vol = volume.rolling(20, min_periods=5).mean()
                vol_ratio = (volume / avg_vol).replace([pd.NA, pd.NaT], 0).fillna(0)
                volume_expansion = vol_ratio > rule.volume_threshold

                cond = (pct > rule.change_threshold) & volume_expansion
                hit_idx = cls._find_last_hit_index(cond, lookback_bars=10)
                if hit_idx is None:
                    continue

                hits1d, hits2d, hits3d = cls._compute_streak_flags(cond, hit_idx)
                if not hits1d:
                    continue

                sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
                
                # --- HARD SECTOR GATE (LOCKED v1.0) ---
                sector_info = sector_data.get(sector_key, {})
                sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
                
                if sector_state not in ["LEADING", "IMPROVING"]:
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
                
                # Compute Tags
                entry_tag = cls.get_entry_tag(stock_active, sector_state, price_above_vwap, is_breakout, vol_ratio_val)
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
                            "stopDistance": float(stop_distance_pct)
                        },
                        "asOf": str(close.index[latest_idx]),
                        "hitAsOf": str(hit_ts),
                        "isLatestSession": bool(hit_idx == len(close) - 1),
                    }
                )
            except Exception:
                continue

        # --- OPTIMIZED BATCH REAL-TIME FETCH ---
        if hits:
            try:
                # Instead of loop + fast_info, we do a single batch download for 1-day daily to get last close
                # This is much faster and less likely to hit rate limits for small batches
                unique_hit_symbols = sorted(list(set([h['symbol'] + ".NS" for h in hits])))
                print(f"DEBUG: Batch verifying {len(unique_hit_symbols)} hits for real-time accuracy...")
                
                rt_df = yf.download(
                    tickers=" ".join(unique_hit_symbols),
                    period="1d",
                    interval="1m",
                    progress=False,
                    group_by="ticker",
                    auto_adjust=False
                )
                
                for hit in hits:
                    sym = hit['symbol'] + ".NS"
                    ticker_rt = rt_df[sym] if isinstance(rt_df.columns, pd.MultiIndex) else rt_df
                    if not ticker_rt.empty:
                        # Update price and change with newest available minute data
                        rt_close = float(ticker_rt['Close'].iloc[-1])
                        # For change, we still need previous day's close for accuracy
                        # The regular batch scan 'latest_change' is likely more accurate as it has day-1 context
                        # but we can adjust price to the literal "now" minute price.
                        hit['price'] = round(rt_close, 2)
                        # We don't recalculate 'change' here as daily change needs T-1 close which aren't in rt_df
            except Exception as e:
                print(f"Batch real-time verify failed: {e}")

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
        except Exception as e:
            print(f"Error loading screener fallback: {e}")
        return []
