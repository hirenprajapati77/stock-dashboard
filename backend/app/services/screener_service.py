import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.constituent_service import ConstituentService

class ScreenerService:
    @staticmethod
    def get_screener_data(timeframe="1D"):
        """
        Identifies stocks with momentum hits (Price > 2%, Volume > 1.5x Avg).
        Checks for consecutive hits over the last 3 trading days.
        """
        # 1. Collect all stocks from constituents
        symbols = []
        symbol_to_sector = {}
        for sector, stocks in ConstituentService.SECTOR_CONSTITUENTS.items():
            for sym in stocks:
                symbols.append(sym)
                symbol_to_sector[sym] = sector.replace("NIFTY_", "").title()

        if not symbols:
            return []

        # 2. Batch download data
        try:
            tickers_str = " ".join(symbols)
            # Use 1d interval to get daily bars; let yfinance manage its own session
            data = yf.download(
                tickers_str,
                period="10d",
                interval="1d",
                progress=False,
                group_by='ticker'
            )
        except Exception as e:
            print(f"Screener Error fetching data: {e}")
            return []

        screener_data = []

        # 3. Process each ticker
        for sym in symbols:
            try:
                if len(symbols) == 1:
                    df = data
                else:
                    df = data[sym]

                df = df.dropna()
                if len(df) < 6: continue # Need enough data for 5-day avg

                # Calculate metrics for the last 3 days
                # Hits are calculated based on:
                # 1. Price Change > 2%
                # 2. Volume > 1.5 * Average Volume (5-day)
                
                def check_hit(idx):
                    row = df.iloc[idx]
                    prev_row = df.iloc[idx-1]
                    
                    price_change = ((row['Close'] - prev_row['Close']) / prev_row['Close']) * 100
                    
                    # 5-day avg volume excluding the current day
                    avg_vol = df['Volume'].iloc[idx-5:idx].mean()
                    vol_ratio = row['Volume'] / avg_vol if avg_vol > 0 else 1.0
                    
                    is_hit = price_change > 2.0 and vol_ratio > 1.5
                    return is_hit, round(price_change, 2), round(vol_ratio, 2)

                hits = []
                # Check last 3 days for hits
                # -1 (Today), -2 (Yesterday), -3 (Day before)
                h1, pc1, vr1 = check_hit(-1)
                h2, pc2, vr2 = check_hit(-2)
                h3, pc3, vr3 = check_hit(-3)

                hits1d = 1 if h1 else 0
                hits2d = 1 if h2 else 0
                hits3d = 1 if h3 else 0

                consecutive = 0
                if h1:
                    consecutive = 1
                    if h2:
                        consecutive = 2
                        if h3:
                            consecutive = 3
                
                # We show stocks that are EITHER current hits OR were hits recently
                # Or just show all components but sorted by strength?
                # For "Market Intelligence", we want the "Hits" primarily.
                if h1 or h2 or h3 or consecutive > 0:
                    screener_data.append({
                        "symbol": sym.replace(".NS", ""),
                        "sector": symbol_to_sector[sym],
                        "cap": "Large",
                        "hits1d": hits1d,
                        "hits2d": hits2d,
                        "hits3d": hits3d,
                        "consecutive": consecutive,
                        "price": round(float(df.iloc[-1]['Close']), 2),
                        "change": pc1,
                        "volRatio": vr1
                    })

            except Exception as e:
                # print(f"Error processing {sym}: {e}")
                continue

        # Sort by Consecutive desc, then current price change desc
        screener_data.sort(key=lambda x: (x['consecutive'], x['hits1d'], x['change']), reverse=True)
        
        return screener_data
