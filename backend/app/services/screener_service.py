import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.constituent_service import ConstituentService


class ScreenerService:
    @staticmethod
    def get_screener_data(timeframe: str = "1D"):
        """
        Intraday momentum + liquidity screener.

        For the selected timeframe, identifies stocks with:
        - Volume shocker (current volume vs 20-bar average)
        - Positive price impulse
        - Relative strength vs sector index

        Returns a ranked list used by the Intelligence panel.
        """
        from app.services.sector_service import SectorService

        # 0. Timeframe configuration
        tf_cfg = {
            "5m": {"interval": "5m", "period": "5d", "shocker_threshold": 2.0},
            "15m": {"interval": "15m", "period": "5d", "shocker_threshold": 1.8},
            "1D": {"interval": "1d", "period": "10d", "shocker_threshold": 1.5},
        }
        cfg = tf_cfg.get(timeframe, tf_cfg["1D"])

        # 1. Collect all stocks from constituents + their sector indices
        symbols: list[str] = []
        symbol_to_sector_key: dict[str, str] = {}
        symbol_to_sector_display: dict[str, str] = {}
        symbol_to_sector_index: dict[str, str] = {}
        sector_index_symbols: set[str] = set()

        from app.services.sector_service import SectorService

        for sector_key, stocks in ConstituentService.SECTOR_CONSTITUENTS.items():
            sector_index = SectorService.SECTORS.get(sector_key)
            if sector_index:
                sector_index_symbols.add(sector_index)

            for sym in stocks:
                symbols.append(sym)
                symbol_to_sector_key[sym] = sector_key
                symbol_to_sector_display[sym] = sector_key.replace("NIFTY_", "").title()
                symbol_to_sector_index[sym] = sector_index

        if not symbols:
            return []

        all_tickers = symbols + list(sector_index_symbols)

        # 2. Batch download data for stocks + sector indices
        try:
            tickers_str = " ".join(all_tickers)
            data = yf.download(
                tickers_str,
                period=cfg["period"],
                interval=cfg["interval"],
                progress=False,
                group_by="ticker",
            )
        except Exception as e:
            print(f"Screener Error fetching data: {e}")
            return []

        if data is None or len(data) == 0:
            print("Screener: empty data from yfinance")
            return []

        # 2b. Get sector rotation snapshot so we know SHINING sectors
        try:
            sector_snapshot, _ = SectorService.get_rotation_data(timeframe=timeframe)
        except Exception as e:
            print(f"Screener: failed to get sector rotation data: {e}")
            sector_snapshot = {}

        screener_data = []

        # Helper to get per-ticker DataFrame from multi-index
        def get_df(ticker: str):
            try:
                if len(all_tickers) == 1:
                    return data.dropna()
                return data[ticker].dropna()
            except Exception:
                return None

        # 3. Process each constituent
        for sym in symbols:
            try:
                df = get_df(sym)
                if df is None or len(df) < 25:
                    continue  # need enough bars for 20-bar average

                # Last and previous bar
                last = df.iloc[-1]
                prev = df.iloc[-2]

                close_col = "Close" if "Close" in df.columns else "close"
                vol_col = "Volume" if "Volume" in df.columns else "volume"

                price_last = float(last[close_col])
                price_prev = float(prev[close_col])
                if price_prev == 0:
                    continue

                price_change = ((price_last - price_prev) / price_prev) * 100.0

                # 20-bar avg volume excluding the current bar
                avg_vol = float(df[vol_col].iloc[-21:-1].mean())
                vol_ratio = float(last[vol_col]) / avg_vol if avg_vol > 0 else 1.0

                # Relative strength vs sector index
                sector_index_ticker = symbol_to_sector_index.get(sym)
                rs_sector = 1.0
                if sector_index_ticker:
                    sector_df = get_df(sector_index_ticker)
                    if sector_df is not None and len(sector_df) > 0:
                        sec_close_col = "Close" if "Close" in sector_df.columns else "close"
                        sec_last = float(sector_df[sec_close_col].iloc[-1])
                        if sec_last > 0:
                            rs_sector = price_last / sec_last

                # Simple hit flags reused by UI (3 most recent bars)
                def compute_hit(idx_offset: int):
                    if len(df) <= abs(idx_offset) + 1:
                        return False
                    row = df.iloc[idx_offset]
                    prev_row = df.iloc[idx_offset - 1]
                    r_price = ((row[close_col] - prev_row[close_col]) / prev_row[close_col]) * 100.0
                    r_avg_vol = df[vol_col].iloc[-21 + idx_offset : -1 + idx_offset].mean()
                    r_vol_ratio = row[vol_col] / r_avg_vol if r_avg_vol > 0 else 1.0
                    return r_price > 2.0 and r_vol_ratio >= cfg["shocker_threshold"]

                h1 = compute_hit(-1)
                h2 = compute_hit(-2)
                h3 = compute_hit(-3)

                hits1d = 1 if h1 else 0
                hits2d = 1 if h2 else 0
                hits3d = 1 if h3 else 0
                consecutive = hits1d + hits2d + hits3d

                # Sector SHINING state from rotation snapshot
                sector_key = symbol_to_sector_key.get(sym)
                sector_info = sector_snapshot.get(sector_key, {})
                metrics = sector_info.get("metrics", {})
                sector_state = metrics.get("state", "NEUTRAL")
                is_sector_shining = sector_state == "SHINING"

                # VWAP for the session
                typical_price = (df["High"] + df["Low"] + df[close_col]) / 3.0
                vwap = (typical_price * df[vol_col]).cumsum() / df[vol_col].cumsum()
                last_vwap = float(vwap.iloc[-1])
                price_above_vwap = price_last > last_vwap

                # Volume shocker thresholds are timeframe-specific
                shocker = vol_ratio
                shocker_thresh = cfg["shocker_threshold"]

                trade_ready = (
                    is_sector_shining
                    and shocker >= shocker_thresh
                    and rs_sector > 1.0
                    and price_above_vwap
                )

                screener_data.append(
                    {
                        "symbol": sym.replace(".NS", ""),
                        "sector": symbol_to_sector_display.get(sym, ""),
                        "sectorKey": sector_key,
                        "cap": "Large",
                        "hits1d": hits1d,
                        "hits2d": hits2d,
                        "hits3d": hits3d,
                        "consecutive": consecutive,
                        "price": round(price_last, 2),
                        "change": round(price_change, 2),
                        "volRatio": round(vol_ratio, 2),  # backward compatible
                        "volumeShocker": round(shocker, 2),
                        "rsSector": round(rs_sector, 2),
                        "tradeReady": bool(trade_ready),
                        "priceAboveVwap": bool(price_above_vwap),
                    }
                )

            except Exception as e:
                # Keep screener robust in case of individual symbol failures
                # print(f"Screener error for {sym}: {e}")
                continue

        # Rank: first by volume shocker, then by RS vs sector, then by price change
        screener_data.sort(
            key=lambda x: (x.get("volumeShocker", 0.0), x.get("rsSector", 1.0), x.get("change", 0.0)),
            reverse=True,
        )

        return screener_data
