import pandas as pd
import yfinance as yf

def debug_hit_logic(symbol):
    print(f"\n--- Debugging Hit Logic for {symbol} ---")
    df = yf.download(symbol, period="1y", interval="1d", progress=False)
    if df.empty:
        print("Data empty!")
        return
        
    # Handle possible MultiIndex from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df.columns = [c.lower() for c in df.columns]
    close = df['close']
    volume = df['volume']
    
    pct = close.pct_change() * 100
    avg_vol = volume.rolling(20, min_periods=5).mean()
    vol_ratio = volume / avg_vol
    
    cond = (pct > 1.5) & (vol_ratio > 1.2) # Relaxed temporarily for debugging
    
    print(f"Recent Pct Change: {pct.tail(5).tolist()}")
    print(f"Recent Vol Ratio: {vol_ratio.tail(5).tolist()}")
    print(f"Recent Cond: {cond.tail(5).tolist()}")
    
    last_hit_idx = -1
    for i in range(1, 11):
        if cond.iloc[-i]:
            print(f"MATCH FOUND at index -{i} (Date: {cond.index[-i]}) | Pct: {pct.iloc[-i]:.2f} | VolR: {vol_ratio.iloc[-i]:.2f}")
            last_hit_idx = -i
            # break # Don't break, see all matches in last 10
            
    if last_hit_idx == -1:
        print("NO MATCH in last 10 days.")

if __name__ == "__main__":
    debug_hit_logic("RELIANCE.NS")
    debug_hit_logic("TCS.NS")
    debug_hit_logic("HDFCBANK.NS")
