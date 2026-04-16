import sys
sys.path.insert(0, '.')
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
import pandas as pd
import numpy as np

print("All imports: OK")

# Minimal synthetic df
np.random.seed(42)
n = 60
close = 100 + np.cumsum(np.random.randn(n) * 0.5)
df = pd.DataFrame({
    'open':   close - np.abs(np.random.randn(n) * 0.3),
    'high':   close + np.abs(np.random.randn(n) * 0.5),
    'low':    close - np.abs(np.random.randn(n) * 0.5),
    'close':  close,
    'volume': np.random.randint(500000, 2000000, n).astype(float)
})
df.index = pd.date_range('2024-01-01', periods=n)
cmp = float(close[-1])

# ── Zones: no zones at all ──────────────────────────────────────
r = ZoneEngine.runDemandSupplyStrategy(df, 'LEADING', zones=[])
print(f"zones (no zones)   -> side={r.get('side')}, status={r.get('entryStatus')}")
assert r.get('side') == 'NEUTRAL', "Expected NEUTRAL side"

# ── Zones: demand zone below CMP ────────────────────────────────
fake_demand = [{'type':'DEMAND','price':cmp*0.97,'price_low':cmp*0.96,
                'price_high':cmp*0.975,'strength':2,'touches':0,'creation_idx':10}]
r2 = ZoneEngine.runDemandSupplyStrategy(df, 'LEADING', zones=fake_demand)
print(f"zones (demand only) -> side={r2.get('side')}, status={r2.get('entryStatus')}, conf={r2.get('confidence')}")
assert r2.get('side') == 'LONG', "Expected LONG side for demand zone"

# ── Zones: supply zone above CMP only ───────────────────────────
fake_supply = [{'type':'SUPPLY','price':cmp*1.03,'price_low':cmp*1.025,
                'price_high':cmp*1.035,'strength':2,'touches':0,'creation_idx':10}]
r3 = ZoneEngine.runDemandSupplyStrategy(df, 'LEADING', zones=fake_supply)
print(f"zones (supply only) -> side={r3.get('side')}, status={r3.get('entryStatus')}, conf={r3.get('confidence')}")
assert r3.get('side') == 'SHORT', "Expected SHORT side for supply-only zones"

# ── Swing ────────────────────────────────────────────────────────
sups = [{'price': cmp * 0.96, 'visits': 2, 'timeframe': '1D'}]
res  = [{'price': cmp * 1.04, 'visits': 2, 'timeframe': '1D'}]
r4 = SwingEngine.runSwingStrategy(df, 'LEADING', htf_trend='BULLISH', supports=sups, resistances=res)
print(f"swing              -> side={r4.get('side')}, status={r4.get('entryStatus')}, conf={r4.get('confidence')}")
assert r4.get('side') in ('LONG', 'SHORT'), "Missing side in swing"
assert r4.get('entryStatus') != 'NONE', "Missing status in swing"

# ── SR ───────────────────────────────────────────────────────────
r5 = SREngine.runSRStrategy(df, 'LEADING', sups, res)
print(f"sr                 -> side={r5.get('side')}, status={r5.get('entryStatus')}, conf={r5.get('confidence')}")
assert r5.get('side') in ('LONG', 'SHORT'), "Missing side in sr"
assert r5.get('entryStatus') not in (None, ''), "Missing status in sr"

print("\nALL TESTS PASSED")
