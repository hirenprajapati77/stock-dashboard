
import yfinance as yf
import pandas as pd
import numpy as np
from app.engine.zones import ZoneEngine

def debug_zones():
    print("Fetching data for BHARATFORG.NS...")
    df = yf.download("BHARATFORG.NS", period="100d", interval="1d")
    if df.empty:
        print("Failed to fetch data")
        return

    # Flatten columns if MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df.columns = [c.lower() for c in df.columns]
    
    print(f"Data rows: {len(df)}")
    
    # Run zone calculation logic manually for debugging
    df_slice = df.tail(200).copy()
    atr_series = ZoneEngine.calculate_atr(df_slice)
    
    print(f"ATR first 20: {atr_series.head(20).values}")
    
    closes = df_slice['close'].values
    opens = df_slice['open'].values
    highs = df_slice['high'].values
    lows = df_slice['low'].values
    
    potential_impulses = 0
    for i in range(3, len(df_slice)):
        current_atr = atr_series.iloc[i]
        body_size = abs(closes[i] - opens[i])
        
        is_impulse = body_size > 1.0 * current_atr
        avg_vol = df_slice['volume'].iloc[i-20:i].mean() if i > 20 else df_slice['volume'].iloc[:i].mean()
        vol_valid = df_slice['volume'].iloc[i] > 1.0 * avg_vol
        
        if is_impulse and vol_valid:
            potential_impulses += 1
            # Check strong close
            range_len = highs[i] - lows[i]
            strong_close = False
            is_bullish = closes[i] > opens[i]
            if is_bullish:
                strong_close = (highs[i] - closes[i]) <= (0.3 * range_len)
                break_prev = closes[i] > highs[i-1]
            else:
                strong_close = (closes[i] - lows[i]) <= (0.3 * range_len)
                break_prev = closes[i] < lows[i-1]
            
            if not strong_close:
                print(f"Index {i}: Impulse found but weak close.")
            elif not break_prev:
                print(f"Index {i}: Impulse found but didn't break previous candle.")
            else:
                # Base check
                c1_body = abs(closes[i-1] - opens[i-1])
                c2_body = abs(closes[i-2] - opens[i-2])
                atr_prev = atr_series.iloc[i-1]
                if c1_body < 1.0 * atr_prev and c2_body < 1.0 * atr_prev:
                    print(f"Index {i}: ZONE FOUND! Type: {'DEMAND' if is_bullish else 'SUPPLY'}")
                else:
                    print(f"Index {i}: Impulse OK but Base weak (C1: {c1_body/atr_prev:.2f}, C2: {c2_body/atr_prev:.2f})")

    print(f"\nPotential Pulses (Size & Vol alone): {potential_impulses}")
    
    # Summary stats
    ratios = []
    vols = []
    for i in range(20, len(df_slice)):
        ratios.append(abs(closes[i]-opens[i]) / atr_series.iloc[i])
        avg_v = df_slice['volume'].iloc[i-20:i].mean()
        vols.append(df_slice['volume'].iloc[i] / avg_v)
    
    print(f"Avg Body/ATR Ratio: {np.mean(ratios):.2f}, Max: {max(ratios):.2f}")
    print(f"Avg Vol/AvgVol Ratio: {np.mean(vols):.2f}, Max: {max(vols):.2f}")

    # Let's see some candle stats
    df['body'] = abs(df['close'] - df['open'])
    df['tr'] = np.maximum(df['high'] - df['low'], 
                         np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                  abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(14).mean()
    
    print("\nLast 5 Candle Stats:")
    last_5 = df.tail(5)
    for idx, row in last_5.iterrows():
        body = row['body']
        atr = row['atr']
        ratio = body/atr if atr > 0 else 0
        
        # Volume check
        avg_vol = df['volume'].rolling(20).mean().shift(1).loc[idx]
        vol_ratio = row['volume'] / avg_vol if avg_vol > 0 else 0
        
        is_impulse = ratio > 1.2
        vol_valid = vol_ratio > 1.2
        
        print(f"Date: {idx}, Ratio: {ratio:.2f} {'[IMPULSE]' if is_impulse else ''}, VolRatio: {vol_ratio:.2f} {'[VOL]' if vol_valid else ''}")

if __name__ == "__main__":
    debug_zones()
