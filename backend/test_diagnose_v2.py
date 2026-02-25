import pandas as pd
import yfinance as yf
from app.services.market_data import MarketDataService
from app.engine.sr import SREngine
from app.services.constituent_service import ConstituentService

def test_vol_ratio():
    print("Testing Volume Ratio for TCS...")
    df, _ = MarketDataService.get_ohlcv("TCS.NS", "1D")
    print(f"DF shape: {df.shape}")
    print(f"DF Columns: {df.columns.tolist()}")
    
    # Simulate SREngine logic
    vol_ratio = float(df['volume'].iloc[-1] / df['volume'].tail(20).mean())
    print(f"Calculated Vol Ratio: {vol_ratio}")

def test_batch_download():
    print("\nTesting Batch Download for Momentum Hits...")
    all_symbols = [s for symbols in ConstituentService.SECTOR_CONSTITUENTS.values() for s in symbols][:20]
    print(f"Tickers count: {len(all_symbols)}")
    
    stock_batch_df = yf.download(
        tickers=" ".join(all_symbols),
        period="1y",
        interval="1d",
        progress=False,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
    )
    print(f"Batch DF empty? {stock_batch_df.empty}")
    if not stock_batch_df.empty:
        print(f"Batch DF columns level 0: {stock_batch_df.columns.get_level_values(0).unique()[:5]}")

if __name__ == "__main__":
    test_vol_ratio()
    test_batch_download()
