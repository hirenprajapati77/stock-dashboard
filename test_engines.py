import pandas as pd
import numpy as np

# Create mock data
dates = pd.date_range(end=pd.Timestamp.now(), periods=200, freq='D')
np.random.seed(42)
base_price = 1000
close = base_price + np.random.randn(200).cumsum() * 10
high = close + np.random.rand(200) * 5
low = close - np.random.rand(200) * 5
open_price = close - np.random.randn(200) * 2
volume = np.random.randint(100000, 1000000, 200)

df = pd.DataFrame({
    'open': open_price,
    'high': high,
    'low': low,
    'close': close,
    'volume': volume
}, index=dates)

# Test Engines
from backend.app.engine.sr import SREngine
from backend.app.engine.zones import ZoneEngine
from backend.app.engine.fibonacci import FibonacciEngine

print("--- SR LEVELS ---")
supports, resistances = SREngine.calculate_sr_levels(df)
print("Supports:", len(supports))
print("Resistances:", len(resistances))

print("\n--- DEMAND SUPPLY ZONES ---")
zones = ZoneEngine.calculate_demand_supply_zones(df)
print("Zones:", len(zones))
for z in zones[:2]: print(z)

print("\n--- FIBONACCI ---")
fib = FibonacciEngine.calculate_fib_levels(df)
print("FIB Supports:", len(fib.get('supports', [])))
print("FIB Resistances:", len(fib.get('resistances', [])))
