"""
Integration test for MarketRegimeEngine + all 3 strategy engines.
Verifies:
  - regime.py imports and detect_regime() works
  - get_grade() maps correctly
  - SR, Swing, D/S all return 'grade' key without crashing
"""
import sys
sys.path.insert(0, 'backend')

import pandas as pd
import numpy as np

# ── Build synthetic OHLCV ──────────────────────────────────────────────────
np.random.seed(42)
n = 100
dates = pd.date_range('2024-01-01', periods=n, freq='D')
closes = pd.Series(500 + np.cumsum(np.random.randn(n) * 2))
df = pd.DataFrame({
    'open':   closes.shift(1).fillna(closes[0]),
    'close':  closes,
    'high':   closes + np.abs(np.random.randn(n)),
    'low':    closes - np.abs(np.random.randn(n)),
    'volume': np.random.randint(300_000, 1_000_000, n)
}, index=dates)

# ── 1. Regime Engine ──────────────────────────────────────────────────────
from app.engine.regime import MarketRegimeEngine

regime = MarketRegimeEngine.detect_regime(df)
print(f"Regime detected : {regime}")
assert regime in ["STRONG_UPTREND", "STRONG_DOWNTREND", "TRENDING", "WEAK_TREND", "RANGE"]

for conf, expected_grade in [(90, "A+"), (78, "A"), (67, "B"), (56, "C"), (40, "D")]:
    g = MarketRegimeEngine.get_grade(conf)
    assert g == expected_grade, f"grade({conf}) = {g}, expected {expected_grade}"
print("Grade mapping    : OK")

# ── 2. SR Engine ──────────────────────────────────────────────────────────
from app.engine.sr import SREngine

sup, res = SREngine.calculate_sr_levels(df)
result_sr = SREngine.runSRStrategy(df, "LEADING", sup, res)
assert "grade" in result_sr, "SR missing 'grade'"
assert "regime" in result_sr["additionalMetrics"], "SR missing regime in metrics"
assert "falseBreak" in result_sr["additionalMetrics"], "SR missing falseBreak"
print(f"SR Engine        : grade={result_sr['grade']}  status={result_sr['entryStatus']}  regime={result_sr['additionalMetrics']['regime']}")

# ── 3. Swing Engine ───────────────────────────────────────────────────────
from app.engine.swing import SwingEngine

s_sup, s_res = SwingEngine.calculate_swing_levels(df)
result_sw = SwingEngine.runSwingStrategy(df, "IMPROVING", "BULLISH", s_sup, s_res)
assert "grade" in result_sw, "Swing missing 'grade'"
assert "regime" in result_sw["additionalMetrics"], "Swing missing regime in metrics"
print(f"Swing Engine     : grade={result_sw['grade']}  status={result_sw['entryStatus']}  regime={result_sw['additionalMetrics']['regime']}")

# ── 4. Demand/Supply Engine ───────────────────────────────────────────────
from app.engine.zones import ZoneEngine

zones = ZoneEngine.calculate_demand_supply_zones(df)
result_ds = ZoneEngine.runDemandSupplyStrategy(df, "NEUTRAL", zones)
assert "grade" in result_ds, "D/S missing 'grade'"
assert "regime" in result_ds["additionalMetrics"], "D/S missing regime in metrics"
print(f"D/S Engine       : grade={result_ds['grade']}  status={result_ds['entryStatus']}  zones={len(zones)}")

print()
print("✅ ALL TESTS PASSED — regime + grade integrated across all 3 engines")
