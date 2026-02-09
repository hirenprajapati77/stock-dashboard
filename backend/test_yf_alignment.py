import yfinance as yf
import pandas as pd

def test_alignment():
    benchmark = "^NSEI"
    sector = "^NSEBANK"
    period = "1y"
    interval = "1d"
    
    print(f"Testing alignment for {benchmark} and {sector}...")
    
    b_df = yf.Ticker(benchmark).history(period=period, interval=interval)
    s_df = yf.Ticker(sector).history(period=period, interval=interval)
    
    print(f"Benchmark index: {b_df.index.dtype}, TZ: {b_df.index.tz}")
    print(f"Sector index:    {s_df.index.dtype}, TZ: {s_df.index.tz}")
    
    combined = pd.DataFrame({
        'sector': s_df['Close'],
        'benchmark': b_df['Close']
    })
    print(f"Combined size (before dropna): {len(combined)}")
    
    clean = combined.dropna()
    print(f"Combined size (after dropna):  {len(clean)}")
    
    if clean.empty:
        print("WARNING: Dataframes did not align! Checking index head...")
        print("Benchmark head:\n", b_df.index[:3])
        print("Sector head:\n", s_df.index[:3])
        
        # Try localizing/normalizing
        b_df.index = b_df.index.tz_localize(None)
        s_df.index = s_df.index.tz_localize(None)
        print("Trying with TZ removed...")
        combined_v2 = pd.DataFrame({
            'sector': s_df['Close'],
            'benchmark': b_df['Close']
        }).dropna()
        print(f"Combined size (v2): {len(combined_v2)}")

if __name__ == "__main__":
    test_alignment()
