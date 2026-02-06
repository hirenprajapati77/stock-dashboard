from app.services.market_data import MarketDataService
import pandas as pd

def test_proxies():
    proxies = ["GOLD", "SILVER", "NIFTYIT", "NIFTYPHARMA", "USDINR"]
    print(f"{'Symbol':<15} | {'Mapped':<15} | {'Status':<10} | {'Price':<10}")
    print("-" * 55)
    
    for p in proxies:
        try:
            norm = MarketDataService.normalize_symbol(p)
            df = MarketDataService.get_ohlcv(norm, "1D", count=5)
            if not df.empty:
                last_price = df['close'].iloc[-1]
                print(f"{p:<15} | {norm:<15} | SUCCESS    | {last_price:.2f}")
            else:
                print(f"{p:<15} | {norm:<15} | EMPTY      | -")
        except Exception as e:
            print(f"{p:<15} | {norm:<15} | ERROR      | {str(e)[:10]}")

if __name__ == "__main__":
    test_proxies()
