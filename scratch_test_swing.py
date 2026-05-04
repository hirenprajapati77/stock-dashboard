import asyncio
import pandas as pd
from app.services.market_data import MarketDataService
from app.engine.swing import SwingEngine

async def test_swing():
    df, cur, err, src = MarketDataService.get_ohlcv("TCS", "15m")
    if df is None:
        print("Failed to get data")
        return
        
    supports, resistances = SwingEngine.calculate_swing_levels(df, "15m")
    print(f"Supports: {supports}")
    print(f"Resistances: {resistances}")
    
    res = SwingEngine.runSwingStrategy(df, "NEUTRAL", "NEUTRAL", supports, resistances)
    print(f"Swing Strategy: {res}")

asyncio.run(test_swing())
