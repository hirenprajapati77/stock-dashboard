import asyncio
import pandas as pd
from app.services.market_data import MarketDataService
from app.services.sector_service import SectorService
from app.services.constituent_service import ConstituentService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.insights import InsightEngine
from app.ai.engine import AIEngine
from app.main import detect_levels_for_df

async def test():
    symbol = "RELIANCE"
    tf = "1D"
    strategy = "DEMAND_SUPPLY"
    norm_symbol = MarketDataService.normalize_symbol(symbol)
    df, currency = MarketDataService.get_ohlcv(norm_symbol, tf)
    cmp = float(df['close'].iloc[-1])
    
    supports, resistances = detect_levels_for_df(df, tf)
    
    ai_engine = AIEngine()
    strategy_result = {}
    
    sh, sl = SwingEngine.get_swings(df)
    atr_ser = ZoneEngine.calculate_atr(df)
    atr = float(atr_ser.iloc[-1])
    zones = ZoneEngine.cluster_swings(sh+sl, atr)
    strategy_result = ZoneEngine.runDemandSupplyStrategy(df, "NEUTRAL", zones)
    
    print("Success for Demand Supply")
    
    strategy_result_swing = SwingEngine.runSwingStrategy(df, "NEUTRAL", "BULLISH", supports)
    print("Success for Swing")

if __name__ == "__main__":
    asyncio.run(test())
