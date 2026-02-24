
import pandas as pd
import numpy as np
from app.engine.sr import SREngine
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine

def test_sr_levels():
    print("\n--- Testing SREngine (Reaction Levels) ---")
    # specific test data
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    prices = [100, 102, 105, 103, 108, 107, 110, 109, 112, 115] * 10 
    df = pd.DataFrame({'high': prices, 'low': [p-2 for p in prices], 'close': prices, 'volume': [1000]*100}, index=dates)
    
    # We expect this to fail if the method doesn't exist yet, which is what we want to verify
    try:
        levels = SREngine.calculate_sr_levels(df)
        print(f"SR Levels found: {len(levels)}")
        for l in levels[:3]: print(l)
    except AttributeError:
        print("SREngine.calculate_sr_levels not implemented yet.")

def test_swing_levels():
    print("\n--- Testing SwingEngine (Structural Levels) ---")
    dates = pd.date_range(start='2023-01-01', periods=200, freq='D')
    # Generate a trend
    prices = np.linspace(100, 200, 200) + np.sin(np.linspace(0, 20, 200)) * 10
    df = pd.DataFrame({'high': prices+1, 'low': prices-1, 'close': prices, 'volume': [1000]*200}, index=dates)
    
    try:
        levels = SwingEngine.calculate_swing_levels(df)
        print(f"Swing Levels found: {len(levels)}")
        for l in levels[:3]: print(l)
    except AttributeError:
        print("SwingEngine.calculate_swing_levels not implemented yet.")

def test_zones():
    print("\n--- Testing ZoneEngine (Demand/Supply) ---")
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    
    # Initialize with neutral candles
    highs = [100.5] * 100
    lows = [99.5] * 100
    closes = [100.0] * 100
    opens = [100.0] * 100
    volumes = [1000] * 100
    
    # 1. Create Strict Base (2 candles < 0.6 ATR) at index 78, 79
    # Assume ATR approx 1.0 (High-Low = 1.0)
    # Candle Body should be < 0.6
    
    # Index 78: Base 1
    opens[78] = 100.0
    closes[78] = 100.2 # Body 0.2 < 0.6
    highs[78] = 100.3
    lows[78] = 99.7
    volumes[78] = 1000 # Normal Vol
    
    # Index 79: Base 2
    opens[79] = 100.2
    closes[79] = 100.0 # Body 0.2 < 0.6
    highs[79] = 100.3
    lows[79] = 99.7
    volumes[79] = 1000 # Normal Vol

    # Index 80: Impulse (Body > 1.5 ATR + Volume > 1.5x Avg)
    # Needs body > 1.5
    opens[80] = 100.0
    closes[80] = 102.0 # Body 2.0 > 1.5
    highs[80] = 102.1 # Close near high (strong close)
    lows[80] = 99.9
    volumes[80] = 2000 # Vol > 1.5 * 1000
    
    df = pd.DataFrame({'high': highs, 'low': lows, 'close': closes, 'open': opens, 'volume': volumes}, index=dates)
    
    try:
        zones = ZoneEngine.calculate_demand_supply_zones(df)
        print(f"Zones found: {len(zones)}")
        for z in zones[:3]: print(z)
    except AttributeError:
        print("ZoneEngine.calculate_demand_supply_zones not implemented yet.")

if __name__ == "__main__":
    test_sr_levels()
    test_swing_levels()
    test_zones()
