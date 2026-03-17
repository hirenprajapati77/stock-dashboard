from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import os
import json
from pathlib import Path


@dataclass(frozen=True)
class EarlyBreakoutResult:
    signal: bool
    details: dict[str, Any]
    tooltip: str


def detect_early_breakout(df: pd.DataFrame) -> EarlyBreakoutResult:
    """
    Early Breakout Detection Engine (additive intelligence layer).

    Conditions (defaults; configurable via env/config):
    1) Tight range: (high - low) / close < 2.5%
    2) Volume build-up: 1.2 <= volRatio < 2.0 (todayVolume / avg20Volume)
    3) Higher low structure: 2 of 3 higher-low confirmations (configurable)
    4) Near resistance: close within X% of 20-day high (configurable)
    """
    if df is None or df.empty:
        return EarlyBreakoutResult(False, {}, "No data available")

    # Normalize columns
    cols = {c.lower(): c for c in df.columns}
    h_col = cols.get("high")
    l_col = cols.get("low")
    c_col = cols.get("close")
    v_col = cols.get("volume")
    if not (h_col and l_col and c_col and v_col):
        return EarlyBreakoutResult(False, {}, "Missing OHLCV fields")

    sdf = df[[h_col, l_col, c_col, v_col]].copy()
    sdf.columns = ["high", "low", "close", "volume"]
    sdf = sdf.dropna(subset=["high", "low", "close", "volume"])
    if len(sdf) < 25:
        return EarlyBreakoutResult(False, {}, "Insufficient history")

    # Use last fully-formed bar (handles occasional trailing 0 volume bars)
    last_idx = len(sdf) - 1
    while last_idx >= 0 and float(sdf["volume"].iloc[last_idx]) == 0:
        last_idx -= 1
    if last_idx < 22:
        return EarlyBreakoutResult(False, {}, "Insufficient valid volume bars")

    high = float(sdf["high"].iloc[last_idx])
    low = float(sdf["low"].iloc[last_idx])
    close = float(sdf["close"].iloc[last_idx])
    if close <= 0:
        return EarlyBreakoutResult(False, {}, "Bad close price")

    # Config (env overrides config file; both optional)
    # Env vars use percentages for range threshold.
    cfg = {
        "EARLY_RANGE_THRESHOLD": 2.5,  # percent
        "EARLY_VOLUME_MIN": 1.2,
        "EARLY_VOLUME_MAX": 2.0,
        "EARLY_RESISTANCE_PROXIMITY": 5.0,  # percent from 20D high
        "EARLY_MIN_HIGHER_LOWS": 2,  # out of 3 confirmations
    }
    try:
        cfg_path = Path(__file__).resolve().parents[1] / "config" / "early_breakout.json"
        if cfg_path.exists():
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update({k: loaded.get(k, v) for k, v in cfg.items()})
    except Exception:
        pass

    def _env_float(key: str, fallback: float) -> float:
        raw = os.getenv(key)
        if raw is None or raw == "":
            return float(fallback)
        try:
            return float(raw)
        except ValueError:
            return float(fallback)

    range_threshold_pct = _env_float("EARLY_RANGE_THRESHOLD", float(cfg["EARLY_RANGE_THRESHOLD"]))
    vol_min = _env_float("EARLY_VOLUME_MIN", float(cfg["EARLY_VOLUME_MIN"]))
    vol_max = _env_float("EARLY_VOLUME_MAX", float(cfg["EARLY_VOLUME_MAX"]))
    resistance_proximity_pct = _env_float("EARLY_RESISTANCE_PROXIMITY", float(cfg["EARLY_RESISTANCE_PROXIMITY"]))
    min_higher_lows = int(_env_float("EARLY_MIN_HIGHER_LOWS", float(cfg["EARLY_MIN_HIGHER_LOWS"])))
    if vol_max <= vol_min:
        vol_max = max(vol_min + 0.1, vol_max)
    if min_higher_lows < 1:
        min_higher_lows = 1
    if min_higher_lows > 3:
        min_higher_lows = 3

    # 1) Tight range
    range_pct = (high - low) / close
    tight_range = range_pct < (range_threshold_pct / 100.0)

    # 2) Volume build-up
    avg20 = sdf["volume"].rolling(20, min_periods=20).mean()
    vol_ratio = float(sdf["volume"].iloc[last_idx] / float(avg20.iloc[last_idx])) if float(avg20.iloc[last_idx]) > 0 else 0.0
    vol_buildup = (vol_ratio >= vol_min) and (vol_ratio < vol_max)

    # 3) Higher lows (controlled relaxation; still requires structure)
    l0 = float(sdf["low"].iloc[last_idx])
    l1 = float(sdf["low"].iloc[last_idx - 1])
    l2 = float(sdf["low"].iloc[last_idx - 2])
    confirmations = 0
    if l1 > l2:
        confirmations += 1
    if l0 > l1:
        confirmations += 1
    if l0 > l2:
        confirmations += 1
    higher_lows = confirmations >= min_higher_lows

    # 4) Near 20D high
    high20 = float(sdf["high"].iloc[max(0, last_idx - 19): last_idx + 1].max())
    near_resistance = close >= ((1.0 - (resistance_proximity_pct / 100.0)) * high20)

    signal = bool(tight_range and vol_buildup and higher_lows and near_resistance)
    tooltip = (
        "Stock showing early accumulation with tight range and volume build-up. Potential breakout candidate."
        if signal
        else "Early breakout conditions not fully met"
    )

    details = {
        "rangePct": round(range_pct * 100, 2),
        "volRatio20": round(vol_ratio, 2),
        "higherLows3": bool(higher_lows),
        "higherLowConfirmations": int(confirmations),
        "near20dHigh": bool(near_resistance),
        "tightRange": bool(tight_range),
        "volumeBuildup": bool(vol_buildup),
        "high20": round(high20, 2),
        "config": {
            "rangeThresholdPct": float(range_threshold_pct),
            "volumeMin": float(vol_min),
            "volumeMax": float(vol_max),
            "resistanceProximityPct": float(resistance_proximity_pct),
            "minHigherLows": int(min_higher_lows),
        },
    }
    return EarlyBreakoutResult(signal=signal, details=details, tooltip=tooltip)

