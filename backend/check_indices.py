import yfinance as yf

SECTORS = {
    "BENCHMARK": "^NSEI",
    "NIFTY_BANK": "^NSEBANK",
    "NIFTY_IT": "^CNXIT",
    "NIFTY_FMCG": "^CNXFMCG",
    "NIFTY_METAL": "^CNXMETAL",
    "NIFTY_PHARMA": "^CNXPHARMA",
    "NIFTY_ENERGY": "^CNXENERGY",
    "NIFTY_AUTO": "^CNXAUTO",
    "NIFTY_REALTY": "^CNXREALTY",
    "NIFTY_PSU_BANK": "^CNXPSUBANK",
    "NIFTY_MEDIA": "^CNXMEDIA"
}

def check_symbols():
    for name, sym in SECTORS.items():
        try:
            print(f"Checking {name} ({sym})...")
            df = yf.Ticker(sym).history(period="5d")
            if df.empty:
                print(f"  [FAILED] {sym} returned EMPTY data")
            else:
                print(f"  [OK] {sym} returned {len(df)} rows")
        except Exception as e:
            print(f"  [ERROR] {sym}: {e}")

if __name__ == "__main__":
    check_symbols()
