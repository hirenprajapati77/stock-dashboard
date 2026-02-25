import pandas as pd
import yfinance as yf
from app.services.screener_service import ScreenerService, ScreenerRule
from app.services.sector_service import SectorService
from app.services.constituent_service import ConstituentService

def debug_screener_internal():
    print("--- Internal Screener Debug ---")
    tf = "1D"
    rule = ScreenerService.RULES_BY_TF[tf]
    print(f"Rules: {rule}")
    
    sector_map = ConstituentService.SECTOR_CONSTITUENTS
    all_symbols = [s for symbols in sector_map.values() for s in symbols]
    print(f"Total Symbols in universe: {len(all_symbols)}")
    
    # Simulate get_screener_data steps
    sector_data, _ = SectorService.get_rotation_data(timeframe=tf, include_constituents=False)
    print(f"Sectors in rotation: {list(sector_data.keys())}")
    
    all_sector_states = {info.get("metrics", {}).get("state", "NEUTRAL") for info in sector_data.values()}
    print(f"All Sector States: {all_sector_states}")
    
    gate_states = ["LEADING", "IMPROVING"]
    if sum(1 for s in all_sector_states if s in gate_states) == 0:
        gate_states = ["LEADING", "IMPROVING", "NEUTRAL"]
    print(f"Gate States: {gate_states}")
    
    # Tickers in LEADING/IMPROVING sectors
    target_symbols = []
    for sector, symbols in sector_map.items():
        state = sector_data.get(sector, {}).get("metrics", {}).get("state", "NEUTRAL")
        if state in gate_states:
            target_symbols.extend(symbols)
    
    print(f"Symbols in LEADING/IMPROVING sectors: {len(target_symbols)}")
    
    # Fetch data for a subset to see why they miss
    test_subset = target_symbols[:20]
    print(f"Testing subset of 20 symbols...")
    
    batch_df = yf.download(tickers=" ".join(test_subset), period="1y", interval="1d", progress=False, group_by="ticker")
    
    total_cond_matches = 0
    symbols_tried = 0
    
    for symbol in test_subset:
        try:
            df = batch_df[symbol]
            if df.empty: continue
            symbols_tried += 1
            
            df.columns = [c.lower() for c in df.columns]
            close = df['close'].dropna()
            volume = df['volume'].dropna()
            
            if len(close) < 20: continue
            
            pct = close.pct_change() * 100
            avg_vol = volume.rolling(20, min_periods=5).mean()
            vol_ratio = (volume / avg_vol).fillna(0)
            
            # Use same rule as ScreenerService
            cond = (pct > rule.change_threshold) & (vol_ratio > rule.volume_threshold)
            
            # Check last 15 bars
            has_hit = False
            for i in range(1, 16):
                if cond.iloc[-i]:
                    has_hit = True
                    # print(f"MATCH: {symbol} hit on index -{i} (Date: {cond.index[-i]}) | Pct: {pct.iloc[-i]:.2f}% | VolR: {vol_ratio.iloc[-i]:.2f}x")
                    total_cond_matches += 1
                    break
        except Exception as e:
            pass
            
    print(f"Symbols passing Price/Vol condition in subset: {total_cond_matches} / {symbols_tried}")

if __name__ == "__main__":
    debug_screener_internal()
