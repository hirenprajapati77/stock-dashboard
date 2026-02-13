from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from app.services.constituent_service import ConstituentService


@dataclass(frozen=True)
class MomentumRule:
    change_threshold: float
    volume_threshold: float


class ScreenerService:
    """Builds momentum-hit rows consumed by the Intelligence dashboard."""

    TIMEFRAME_MAP: Dict[str, Dict[str, str]] = {
        "5m": {"interval": "5m", "period": "5d"},
        "15m": {"interval": "15m", "period": "5d"},
        "75m": {"interval": "60m", "period": "1mo"},
        "1H": {"interval": "60m", "period": "1mo"},
        "2H": {"interval": "60m", "period": "1mo"},
        "4H": {"interval": "60m", "period": "3mo"},
        "1D": {"interval": "1d", "period": "6mo"},
        "1W": {"interval": "1wk", "period": "3y"},
        "1M": {"interval": "1mo", "period": "8y"},
    }

    # Slightly relaxed price threshold on intraday candles; volume threshold stays strict.
    RULES_BY_TF: Dict[str, MomentumRule] = {
        "5m": MomentumRule(change_threshold=0.7, volume_threshold=1.5),
        "15m": MomentumRule(change_threshold=0.9, volume_threshold=1.5),
        "75m": MomentumRule(change_threshold=1.2, volume_threshold=1.5),
        "1H": MomentumRule(change_threshold=1.2, volume_threshold=1.5),
        "2H": MomentumRule(change_threshold=1.5, volume_threshold=1.5),
        "4H": MomentumRule(change_threshold=1.7, volume_threshold=1.5),
        "1D": MomentumRule(change_threshold=2.0, volume_threshold=1.5),
        "1W": MomentumRule(change_threshold=3.0, volume_threshold=1.5),
        "1M": MomentumRule(change_threshold=4.0, volume_threshold=1.5),
    }


    @staticmethod
    def _find_last_hit_index(cond: pd.Series, lookback_bars: int = 10) -> Optional[int]:
        """Return the latest index position within lookback where momentum condition is true."""
        if cond is None or cond.empty:
            return None

        start = max(0, len(cond) - lookback_bars)
        for pos in range(len(cond) - 1, start - 1, -1):
            if bool(cond.iloc[pos]):
                return pos
        return None

    @staticmethod
    def _compute_streak_flags(cond: pd.Series, idx: int) -> tuple[bool, bool, bool]:
        """Compute 1D/2D/3D flags ending at the provided bar index."""
        hits1d = bool(cond.iloc[idx])
        hits2d = hits1d and idx - 1 >= 0 and bool(cond.iloc[idx - 1])
        hits3d = hits2d and idx - 2 >= 0 and bool(cond.iloc[idx - 2])
        return hits1d, hits2d, hits3d

    @classmethod
    def get_screener_data(cls, timeframe: str = "1D") -> List[Dict]:
        config = cls.TIMEFRAME_MAP.get(timeframe, cls.TIMEFRAME_MAP["1D"])
        rule = cls.RULES_BY_TF.get(timeframe, cls.RULES_BY_TF["1D"])

        sector_map = {
            sector_key: symbols
            for sector_key, symbols in ConstituentService.SECTOR_CONSTITUENTS.items()
            if symbols
        }
        all_symbols = sorted({symbol for symbols in sector_map.values() for symbol in symbols})
        if not all_symbols:
            return []

        try:
            batch_df = yf.download(
                tickers=" ".join(all_symbols),
                period=config["period"],
                interval=config["interval"],
                progress=False,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
            )
        except Exception as e:
            print(f"Momentum screener batch download failed: {e}")
            return []

        if batch_df is None or batch_df.empty:
            return []

        sector_by_symbol = {
            symbol: sector
            for sector, symbols in sector_map.items()
            for symbol in symbols
        }

        hits: List[Dict] = []
        for symbol in all_symbols:
            try:
                symbol_df = batch_df[symbol] if isinstance(batch_df.columns, pd.MultiIndex) else batch_df
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

                cond = (pct > rule.change_threshold) & (vol_ratio > rule.volume_threshold)

                # If no hit on the very last bar (e.g., market closed/quiet),
                # fall back to the most recent qualifying session within a short lookback.
                hit_idx = cls._find_last_hit_index(cond, lookback_bars=10)
                if hit_idx is None:
                    continue

                hits1d, hits2d, hits3d = cls._compute_streak_flags(cond, hit_idx)
                if not hits1d:
                    continue

                display_symbol = symbol.replace(".NS", "").replace(".BO", "")
                sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
                hit_ts = close.index[hit_idx]

                hits.append(
                    {
                        "symbol": display_symbol,
                        "price": round(float(close.iloc[hit_idx]), 2),
                        "change": round(float(pct.iloc[hit_idx]), 2),
                        "hits1d": hits1d,
                        "hits2d": hits2d,
                        "hits3d": hits3d,
                        "volRatio": round(float(vol_ratio.iloc[hit_idx]), 2),
                        "volumeShocker": round(float(vol_ratio.iloc[hit_idx]), 2),
                        "sector": sector_key.replace("NIFTY_", "").replace("_", " "),
                        "sectorKey": sector_key,
                        "tradeReady": hits2d or hits3d,
                        "asOf": str(hit_ts),
                        "isLatestSession": bool(hit_idx == len(close) - 1),
                    }
                )
            except Exception:
                # Symbol-level failure should not break the whole intelligence response.
                continue

        hits.sort(key=lambda row: (row["hits3d"], row["hits2d"], row["change"], row["volRatio"]), reverse=True)
        return hits
