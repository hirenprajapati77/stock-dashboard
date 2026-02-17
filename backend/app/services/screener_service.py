from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
import concurrent.futures
from datetime import datetime

from app.services.constituent_service import ConstituentService


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
            
            last_price = fast.get('lastPrice') or fast.get('last_price')
            prev_close = fast.get('previousClose') or fast.get('previous_close')
            
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
    def _get_live_quote(cls, symbol: str, fallback_price: float, fallback_change: float) -> tuple[float, float]:
        """Best-effort quote refresh so UI can reflect live values, not only last candle close."""
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            live_price = cls._extract_fast_value(fast_info, 'lastPrice', 'last_price', 'regularMarketPrice')
            prev_close = cls._extract_fast_value(fast_info, 'previousClose', 'regularMarketPreviousClose')

            if live_price is None:
                return fallback_price, fallback_change

            live_price = float(live_price)
            if prev_close is not None and float(prev_close) > 0:
                live_change = ((live_price - float(prev_close)) / float(prev_close)) * 100
            else:
                live_change = fallback_change
            return live_price, float(live_change)
        except Exception:
            return fallback_price, fallback_change

    @classmethod
    def get_screener_data(cls, timeframe: str = "1D") -> List[Dict]:
        normalized_tf = "1D" if timeframe == "Daily" else timeframe
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
            return []

        if stock_batch_df is None or stock_batch_df.empty:
            return []

        sector_by_symbol = {
            symbol: sector
            for sector, symbols in sector_map.items()
            for symbol in symbols
        }

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
                live_price, live_change = cls._get_live_quote(symbol, latest_price, latest_change)
                rs_sector = (stock_return / sector_return) if abs(sector_return) > 1e-6 else 0.0

                display_symbol = symbol.replace(".NS", "").replace(".BO", "")
                hit_ts = close.index[hit_idx]

                hits.append(
                    {
                        "symbol": display_symbol,
                        # Keep screening qualification tied to the most-recent momentum hit,
                        # but always surface current tradable price/change for live sync in UI.
                        "price": round(live_price, 2),
                        "change": round(live_change, 2),
                        "hitChange": round(stock_return, 2),
                        "hits1d": hits1d,
                        "hits2d": hits2d,
                        "hits3d": hits3d,
                        "volRatio": round(float(vol_ratio.iloc[hit_idx]), 2),
                        "volumeShocker": round(float(vol_ratio.iloc[hit_idx]), 2),
                        "volumeExpansion": bool(volume_expansion.iloc[hit_idx]),
                        "sector": sector_key.replace("NIFTY_", "").replace("_", " "),
                        "sectorKey": sector_key,
                        "sectorReturn": round(sector_return, 4),
                        "rsSector": round(rs_sector, 4),
                        "tradeReady": hits2d or hits3d,
                        "asOf": str(close.index[latest_idx]),
                        "hitAsOf": str(hit_ts),
                        "isLatestSession": bool(hit_idx == len(close) - 1),
                    }
                )
            except Exception:
                continue

        # --- REAL-TIME VALIDATION STEP ---
        # The hits generation above uses batch data which might be 15-60m delayed or from yesterday.
        # We must verify the "Price" and "Change" with live data from fast_info.
        
        valid_hits = []
        if hits:
            # Collect symbols to verify
            symbols_to_verify = [h['symbol'] for h in hits]
            realtime_map = {}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                future_to_sym = {executor.submit(cls._fetch_realtime_price, sym): sym for sym in symbols_to_verify}
                for future in concurrent.futures.as_completed(future_to_sym):
                    res = future.result()
                    if res and res.get("valid"):
                        # Map base symbol back to result
                        # Note: _fetch_realtime_price returns the symbol passed to it
                        realtime_map[res["symbol"]] = res
            
            # Update hits with real-time data
            for hit in hits:
                rt_data = realtime_map.get(hit['symbol'])
                if rt_data:
                    # found real-time data, update the hit
                    hit['price'] = round(float(rt_data['price']), 2)
                    hit['change'] = round(float(rt_data['change']), 2)
                    
                    # Optional: Re-qualify the hit?
                    # If it was a momentum hit (>2%) but now is <0%, do we hide it?
                    # User feedback: "Stock are down even though showing 5% up"
                    # We should definitely show the CORRECT change.
                    # Whether to keep it in the list:
                    # Ideally, we only show valid hits. But strictly filtering might empty the list if yfinance is super volatile.
                    # Let's keep it but show the correct (live) red/green status.
                
                valid_hits.append(hit)
        else:
            valid_hits = hits

        valid_hits.sort(key=lambda row: (row["hits3d"], row["hits2d"], row["rsSector"], row["volRatio"]), reverse=True)
        return valid_hits
