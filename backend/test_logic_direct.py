import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# Add the current directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.engine.zones import ZoneEngine

def test_zones():
    # Create dummy data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    df = pd.DataFrame({
        'open': np.linspace(100, 150, 100),
        'high': np.linspace(105, 155, 100),
        'low': np.linspace(95, 145, 100),
        'close': np.linspace(103, 153, 100),
        'volume': np.random.randint(1000, 5000, 100)
    }, index=dates)
    
    # Force a "Demand Zone" pattern
    df.iloc[50] = [120, 140, 115, 138, 10000] # Large green candle
    
    print("Calculating Zones...")
    zones = ZoneEngine.calculate_demand_supply_zones(df)
    
    print("Running Strategy...")
    result = ZoneEngine.runDemandSupplyStrategy(df, "LEADING", zones)
    
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    test_zones()
