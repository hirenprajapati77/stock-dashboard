import sys
sys.path.insert(0, 'backend')

import pandas as pd
import numpy as np
from app.engine.zones import ZoneEngine

# Build synthetic data that mimics an impulse + base pattern
np.random.seed(42)
n = 100
dates = pd.date_range('2024-01-01', periods=n, freq='D')
price = 500.0
prices, volumes = [], []

for i in range(n):
    if i in [30, 31]:  # small base candles
        price += np.random.uniform(-2, 2)
    elif i == 32:       # strong bullish impulse
        price += 40
    else:
        price += np.random.uniform(-5, 5)
    prices.append(price)
    volumes.append(int(np.random.uniform(1e6, 2e6)))

closes = pd.Series(prices)
df = pd.DataFrame({
    'open':   closes.shift(1).fillna(closes),
    'close':  closes,
    'high':   closes + np.random.uniform(0, 5, n),
    'low':    closes - np.random.uniform(0, 5, n),
    'volume': volumes
}, index=dates)

# Make impulse candle have very high volume
df.iloc[32, df.columns.get_loc('volume')] = 5_000_000

zones = ZoneEngine.calculate_demand_supply_zones(df)
print(f'Zones found: {len(zones)}')

# Test runDemandSupplyStrategy - this used to crash with NameError
result = ZoneEngine.runDemandSupplyStrategy(df, 'NEUTRAL', zones)
print('runDemandSupplyStrategy result:')
for k, v in result.items():
    if k != 'zones':
        print(f'  {k}: {v}')
print(f'  zones count: {len(result.get("zones", []))}')
print()
print('SUCCESS - no crash!')
