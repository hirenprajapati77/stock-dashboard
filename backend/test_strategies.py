import pandas as pd
import numpy as np
from app.engine.sr import SREngine
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.insights import InsightEngine

def create_mock_df(count=100, trend="BULLISH", volatility=0.01):
    dates = pd.date_range(start="2024-01-01", periods=count, freq="15min")
    close = [100.0]
    for _ in range(count - 1):
        change = np.random.normal(0, volatility)
        if trend == "BULLISH": change += 0.001
        elif trend == "BEARISH": change -= 0.001
        close.append(close[-1] * (1 + change))
        
    df = pd.DataFrame({
        "open": [c * (1 + np.random.normal(0, 0.001)) for c in close],
        "high": [c * (1 + abs(np.random.normal(0, 0.002))) for c in close],
        "low": [c * (1 - abs(np.random.normal(0, 0.002))) for c in close],
        "close": close,
        "volume": [np.random.randint(1000, 5000) for _ in range(count)]
    }, index=dates)
    return df

def test_sr_strategy():
    print("\n--- Testing SR Strategy ---")
    df = create_mock_df()
    cmp = df['close'].iloc[-1]
    supports = [{"price": cmp * 0.95, "touches": 3, "last_touched": str(df.index[-10])}]
    resistances = [{"price": cmp * 0.98, "touches": 2, "last_touched": str(df.index[-5])}] # Price is already above this
    
    # 1. Breakout Case
    result = SREngine.runSRStrategy(df, "LEADING", supports, resistances)
    print(f"SR (LEADING, Breakout): Status={result['entryStatus']}, Confidence={result['confidence']}, ADX={result['additionalMetrics']['adx']}")
    
    # 2. ADX guard
    # Mock ADX low (can't easily mock within the class without dependency injection, but we can check if it returns WAIT)
    # Since we use real InsightEngine, we'll just check the result with the mock DF
    
    # 3. LAGGING sector guard
    result_lagging = SREngine.runSRStrategy(df, "LAGGING", supports, resistances)
    print(f"SR (LAGGING Guard): Status={result_lagging['entryStatus']} (Expected: WAIT)")

def test_swing_strategy():
    print("\n--- Testing Swing Strategy ---")
    df = create_mock_df(trend="BULLISH")
    cmp = df['close'].iloc[-1]
    supports = [{"price": cmp * 0.995}] # CMP very close to support
    
    result = SwingEngine.runSwingStrategy(df, "LEADING", "BULLISH", supports)
    print(f"Swing (Bullish, Pullback): Status={result['entryStatus']}, Confidence={result['confidence']}, Structure={result['additionalMetrics']['structure']}")
    
    result_lagging = SwingEngine.runSwingStrategy(df, "LAGGING", "BULLISH", supports)
    print(f"Swing (LAGGING Guard): Status={result_lagging['entryStatus']} (Expected: WAIT)")

def test_demand_supply_strategy():
    print("\n--- Testing Demand/Supply Strategy ---")
    df = create_mock_df()
    cmp = df['close'].iloc[-1]
    # Create a fresh zone
    zones = [{
        "price": cmp * 0.99,
        "price_low": cmp * 0.985,
        "price_high": cmp * 0.995,
        "touches": 1,
        "last_touched": str(df.index[-2])
    }]
    
    result = ZoneEngine.runDemandSupplyStrategy(df, "LEADING", zones)
    print(f"DemandSupply (Fresh Zone): Status={result['entryStatus']}, Confidence={result['confidence']}, Freshness={result['additionalMetrics']['freshness']}")

if __name__ == "__main__":
    test_sr_strategy()
    test_swing_strategy()
    test_demand_supply_strategy()
