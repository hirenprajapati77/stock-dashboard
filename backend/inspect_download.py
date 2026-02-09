import yfinance as yf
import pandas as pd

def inspect_download():
    benchmark = "^NSEI"
    sectors = ["^NSEBANK", "^CNXIT"]
    all_symbols = [benchmark] + sectors
    period = "1y"
    interval = "1d"
    
    print(f"Downloading {all_symbols}...")
    batch_df = yf.download(" ".join(all_symbols), period=period, interval=interval, progress=False)
    
    print("\nDataFrame Shape:", batch_df.shape)
    print("Available Columns:", batch_df.columns.levels[0] if hasattr(batch_df.columns, 'levels') else batch_df.columns)
    
    if 'Close' in batch_df:
        closes = batch_df['Close']
        print("\nCloses Head:")
        print(closes.head())
        print("\nCloses Tail:")
        print(closes.tail())
        
        for sym in all_symbols:
            if sym in closes:
                non_nan = closes[sym].dropna()
                print(f"{sym}: {len(non_nan)} non-NaN values")
            else:
                print(f"{sym}: MISSING in Close column")
    else:
        print("\n'Close' column MISSING from batch_df!")

if __name__ == "__main__":
    inspect_download()
