import pandas as pd
from app.services.market_data import MarketDataService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.confidence import ConfidenceEngine

def test_engine():
    print("1. Fetching Real Data (RELIANCE)...")
    df = MarketDataService.get_ohlcv("RELIANCE", "1D", 200)
    print(f"   Data Shape: {df.shape}")
    
    print("\n2. Testing SwingEngine...")
    sh, sl = SwingEngine.get_swings(df)
    print(f"   Swing Highs: {len(sh)}")
    print(f"   Swing Lows: {len(sl)}")
    if sh: print(f"   Sample High: {sh[0]}")
    
    print("\n3. Testing ZoneEngine...")
    atr = ZoneEngine.calculate_atr(df).iloc[-1]
    print(f"   ATR: {atr:.2f}")
    all_swings = sh + sl
    zones = ZoneEngine.cluster_swings(all_swings, atr)
    print(f"   Zones Found: {len(zones)}")
    if zones: print(f"   Sample Zone: {zones[0]}")
    
    print("\n4. Testing SREngine...")
    cmp = df['close'].iloc[-1]
    supports, resistances = SREngine.classify_levels(zones, cmp)
    print(f"   Supports: {len(supports)}")
    print(f"   Resistances: {len(resistances)}")
    
    print("\n5. Testing ConfidenceEngine...")
    if supports:
        s = supports[0]
        score = ConfidenceEngine.calculate_score(s, "1D", atr, df.index[-1])
        print(f"   Support Score: {score} ({ConfidenceEngine.get_label(score)})")

if __name__ == "__main__":
    test_engine()
