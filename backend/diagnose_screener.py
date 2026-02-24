"""
Momentum Hits Diagnostic Script
Prints exactly why each stock is being rejected.
"""
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
import yfinance as yf
import time
from backend.app.services.constituent_service import ConstituentService
from backend.app.services.sector_service import SectorService

TIMEFRAME = "1D"
config = {"period": "6mo", "interval": "1d"}

# ─────────── thresholds ───────────
CHANGE_THRESHOLD = 2.0
VOL_THRESHOLD = 1.5
LOOKBACK_BARS = 10

SECTOR_INDEX_BY_KEY = {
    "NIFTY_BANK": "^NSEBANK", "NIFTY_IT": "^CNXIT", "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_METAL": "^CNXMETAL", "NIFTY_PHARMA": "^CNXPHARMA", "NIFTY_ENERGY": "^CNXENERGY",
    "NIFTY_AUTO": "^CNXAUTO", "NIFTY_REALTY": "^CNXREALTY", "NIFTY_PSU_BANK": "^CNXPSUBANK",
}

sector_map = {k: v for k, v in ConstituentService.SECTOR_CONSTITUENTS.items() if v}
all_symbols = sorted({s for syms in sector_map.values() for s in syms})
sector_by_symbol = {s: k for k, syms in sector_map.items() for s in syms}
sector_indices = list(set(SECTOR_INDEX_BY_KEY[k] for k in sector_map if k in SECTOR_INDEX_BY_KEY))

print(f"Downloading {len(all_symbols)} stock symbols...")
stock_df = yf.download(" ".join(all_symbols), period=config["period"], interval=config["interval"],
                       progress=False, group_by="ticker", auto_adjust=False, threads=True)
print("Downloading sector indices...")
sector_df = yf.download(" ".join(sector_indices), period=config["period"], interval=config["interval"],
                        progress=False, group_by="ticker", auto_adjust=False, threads=True)

sector_data, _ = SectorService.get_rotation_data(timeframe=TIMEFRAME, include_constituents=False)

# Counters
counters = {
    "no_data": 0, "insufficient_bars": 0, "no_hit": 0,
    "sector_gate": 0, "rs_gate": 0, "passed": 0
}

for symbol in all_symbols[:60]:  # sample first 60 for speed
    try:
        sym_df = stock_df[symbol] if isinstance(stock_df.columns, pd.MultiIndex) else stock_df
        if sym_df is None or sym_df.empty: counters["no_data"] += 1; continue

        close_col = "Close" if "Close" in sym_df.columns else "close"
        vol_col = "Volume" if "Volume" in sym_df.columns else "volume"
        if close_col not in sym_df.columns: counters["no_data"] += 1; continue

        close = sym_df[close_col].dropna()
        volume = sym_df[vol_col].dropna()
        if len(close) < 6: counters["insufficient_bars"] += 1; continue

        pct = close.pct_change() * 100
        avg_vol = volume.rolling(20, min_periods=5).mean()
        vol_ratio = (volume / avg_vol).fillna(0)
        volume_expansion = vol_ratio > VOL_THRESHOLD
        cond = (pct > CHANGE_THRESHOLD) & volume_expansion

        # Find last hit
        hit_idx = None
        for pos in range(len(cond) - 1, max(0, len(cond) - LOOKBACK_BARS) - 1, -1):
            if bool(cond.iloc[pos]): hit_idx = pos; break
        if hit_idx is None: counters["no_hit"] += 1; continue

        sector_key = sector_by_symbol.get(symbol, "UNKNOWN")
        sector_info = sector_data.get(sector_key, {})
        sector_state = sector_info.get("metrics", {}).get("state", "NEUTRAL")
        if sector_state not in ["LEADING", "IMPROVING"]:
            counters["sector_gate"] += 1; continue

        # RS gate
        sector_return = 0.0
        if sector_key in SECTOR_INDEX_BY_KEY and not sector_df.empty:
            s_sym = SECTOR_INDEX_BY_KEY[sector_key]
            s_df = sector_df[s_sym] if isinstance(sector_df.columns, pd.MultiIndex) else sector_df
            if s_df is not None and not s_df.empty:
                sc = s_df["Close"].dropna() if "Close" in s_df else s_df["close"].dropna()
                if len(sc) > hit_idx: sector_return = float((sc.pct_change()*100).iloc[hit_idx])
        stock_return = float(pct.iloc[hit_idx])
        rs_sector = stock_return - sector_return
        if rs_sector <= 0:
            counters["rs_gate"] += 1; continue

        counters["passed"] += 1
        print(f"  PASS: {symbol.replace('.NS','')} | pct={stock_return:.2f}% | vol={vol_ratio.iloc[hit_idx]:.1f}x | sector={sector_state} | rs={rs_sector:.2f}")

    except Exception as e:
        counters["no_data"] += 1

print("\n─── Filter Summary (first 60 symbols) ───")
for k, v in counters.items():
    print(f"  {k:20s}: {v}")
print(f"\n  Sector states:")
for name, info in sector_data.items():
    print(f"    {name.replace('NIFTY_',''):15s}: {info.get('metrics',{}).get('state','?')}")
