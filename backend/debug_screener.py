import yfinance as yf
import pandas as pd

def debug_stock(sym):
    print(f"\n--- DEBUGGING {sym} ---")
    ticker_sym = sym if "." in sym or sym.startswith("^") else f"{sym}.NS"
    ticker = yf.Ticker(ticker_sym)
    
    try:
        info = ticker.info
        qf = ticker.quarterly_financials
        
        if qf.empty or len(qf.columns) < 3:
            print("❌ Not enough quarterly data")
            return
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return

    # Extract Data
    sales = qf.loc['Total Revenue']
    profit = qf.loc['Net Income']
    
    eps_key = 'Basic EPS' if 'Basic EPS' in qf.index else 'Diluted EPS' if 'Diluted EPS' in qf.index else None
    eps = qf.loc[eps_key] if eps_key else pd.Series()
    
    de_ratio = info.get('debtToEquity')
    if de_ratio is None: de_ratio = 50 
    
    peg = info.get('pegRatio')
    
    rev_growth = info.get('revenueQuarterlyGrowth')
    if rev_growth is None:
        if len(qf.columns) >= 5:
            latest = qf.loc['Total Revenue'].iloc[0]
            prev = qf.loc['Total Revenue'].iloc[4]
            if prev > 0:
                rev_growth = (latest - prev) / prev
    if rev_growth is None: rev_growth = 0
    
    market_cap = info.get('marketCap')
    pe_ratio = info.get('trailingPE')
    roce = info.get('returnOnCapitalEmployed')
    roe = info.get('returnOnEquity')
    
    # Use ROE as fallback for ROCE
    effective_roce = roce if roce is not None else roe

    print(f"Sales (Latest 3): {[float(x) for x in sales.iloc[:3]]}")
    print(f"Profit (Latest 3): {[float(x) for x in profit.iloc[:3]]}")
    print(f"Market Cap: {market_cap}")
    print(f"PE: {pe_ratio}")
    print(f"ROCE: {roce}, ROE: {roe}, Effective: {effective_roce}")
    print(f"D/E: {de_ratio}")
    print(f"PEG: {peg}")
    print(f"YoY Rev Growth: {rev_growth}")

    # Conditions
    cond_mcap = market_cap and market_cap > 5e9
    cond_pe = pe_ratio and pe_ratio < 15
    cond_roce = effective_roce and effective_roce > 0.22
    
    cond1 = sales.iloc[0] >= sales.iloc[1]
    cond2 = sales.iloc[1] >= sales.iloc[2]
    cond3 = (de_ratio < 1 or de_ratio < 100) # This looks like a bug in service, checking logic
    # In service: de_check = de_ratio < 1 or de_ratio < 100 
    # Wait, de_ratio from yfinance is typically returns as percentage? No, it's usually Ratio * 100 or just Ratio.
    # Usually 0.5 means 50%. yfinance returns debtToEquity as a number like 50.4 (meaning 0.504) or 50 (meaning 50%)?
    # yfinance 'debtToEquity' is usually a percentage, e.g. 50.
    
    cond4 = profit.iloc[0] > profit.iloc[1]
    cond5 = profit.iloc[1] > profit.iloc[2]
    cond6 = profit.iloc[0] > 1e6
    cond7 = rev_growth > 0.10
    
    cond8 = True 
    if not eps.empty and len(eps) > 1:
        if eps.iloc[0] > eps.iloc[1]:
            pass

    cond9 = False
    if peg is not None and peg < 2.0:
        cond9 = True
    elif pe_ratio and pe_ratio < 50 and rev_growth > 0.15:
        cond9 = True
    elif peg is None and all([cond1, cond2, cond4, cond5, cond7]):
        cond9 = True

    print(f"C1 (Sales 0>=1): {cond1}")
    print(f"C2 (Sales 1>=2): {cond2}")
    print(f"C3 (D/E Check): {cond3}")
    print(f"C4 (Profit 0>1): {cond4}")
    print(f"C5 (Profit 1>2): {cond5}")
    print(f"C6 (Profit > 10L): {cond6}")
    print(f"C7 (YoY Sales > 10%): {cond7}")
    print(f"C9 (PEG/Valuation): {cond9}")
    print(f"C_MCAP (>500Cr): {cond_mcap}")
    print(f"C_PE (<15): {cond_pe}")
    print(f"C_ROCE (>22%): {cond_roce}")
    
    final = all([cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond8, cond9, cond_mcap, cond_pe, cond_roce])
    print(f"FINAL RESULT: {'PASS' if final else 'FAIL'}")

if __name__ == "__main__":
    debug_stock("COALINDIA")
    debug_stock("ONGC")
    debug_stock("ITC")
