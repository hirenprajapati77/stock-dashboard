import yfinance as yf
import pandas as pd

symbols = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXFMCG"]

def test_history():
    print("Testing .history(period='1y', interval='1d'):")
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            df = t.history(period="1y", interval="1d")
            print(f"  {sym}: {'SUCCESS' if not df.empty else 'EMPTY'} (Rows: {len(df)})")
        except Exception as e:
            print(f"  {sym}: ERROR - {e}")

def test_download():
    print("\nTesting yf.download(period='1y', interval='1d'):")
    try:
        data = yf.download(" ".join(symbols), period="1y", interval="1d", progress=False)
        print(f"  Batch download: {'SUCCESS' if not data.empty else 'EMPTY'} (Rows: {len(data)})")
        if not data.empty:
            print(f"  Available Closecodes: {data.get('Close', pd.DataFrame()).columns.tolist()}")
    except Exception as e:
        print(f"  Batch download: ERROR - {e}")

if __name__ == "__main__":
    test_history()
    test_download()
