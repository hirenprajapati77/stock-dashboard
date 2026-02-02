import yfinance as yf
import pandas as pd

def test_stock(sym):
    """Test a single stock against all conditions and show which ones fail"""
    try:
        ticker_sym = sym if "." in sym or sym.startswith("^") else f"{sym}.NS"
        ticker = yf.Ticker(ticker_sym)
        
        info = ticker.info
        qf = ticker.quarterly_financials
        
        if qf.empty or len(qf.columns) < 3:
            return None
        
        sales = qf.loc['Total Revenue']
        profit = qf.loc['Net Income']
        
        eps_key = 'Basic EPS' if 'Basic EPS' in qf.index else 'Diluted EPS' if 'Diluted EPS' in qf.index else None
        eps = qf.loc[eps_key] if eps_key else pd.Series()
        
        de_ratio = info.get('debtToEquity')
        if de_ratio is None: de_ratio = 50
        de_check = de_ratio < 1 or de_ratio < 100
        
        peg = info.get('pegRatio')
        rev_growth = info.get('revenueQuarterlyGrowth')
        
        if rev_growth is None and len(qf.columns) >= 5:
            latest_rev = qf.loc['Total Revenue'].iloc[0]
            year_ago_rev = qf.loc['Total Revenue'].iloc[4]
            if year_ago_rev > 0:
                rev_growth = (latest_rev - year_ago_rev) / year_ago_rev
        
        if rev_growth is None: rev_growth = 0
        
        # Test all conditions
        c1 = sales.iloc[0] >= sales.iloc[1]
        c2 = sales.iloc[1] >= sales.iloc[2]
        c3 = de_check
        c4 = profit.iloc[0] > profit.iloc[1]
        c5 = profit.iloc[1] > profit.iloc[2]
        c6 = profit.iloc[0] > 1e6
        c7 = rev_growth > 0.15
        c8 = eps.iloc[0] > eps.iloc[1] if not eps.empty and len(eps) > 1 else False
        
        pe = info.get('trailingPE')
        c9 = False
        if peg is not None:
            c9 = peg < 1.2
        elif pe and pe < 40 and rev_growth > 0.20:
            c9 = True
        
        result = {
            'symbol': sym,
            'pass': all([c1, c2, c3, c4, c5, c6, c7, c8, c9]),
            'c1_sales_0>=1': c1,
            'c2_sales_1>=2': c2,
            'c3_de<1': c3,
            'c4_profit_0>1': c4,
            'c5_profit_1>2': c5,
            'c6_profit>1M': c6,
            'c7_yoy>15%': c7,
            'c8_eps_growth': c8,
            'c9_peg<1.2': c9,
            'rev_growth': f"{rev_growth*100:.1f}%",
            'peg': peg
        }
        return result
    except Exception as e:
        return None

if __name__ == "__main__":
    # Test the stocks from Screener.in
    test_stocks = ["GRSE", "INDOTHAI", "IGIL", "MAHABANK", "KAYNES", "SYRMA", "DATAPATTNS", 
                   "HAL", "BEL", "RVNL", "IRFC", "IREDA"]
    
    print("Testing stocks from Screener.in:\n")
    for stock in test_stocks:
        result = test_stock(stock)
        if result:
            status = "✓ PASS" if result['pass'] else "✗ FAIL"
            print(f"{stock:12} {status}")
            if not result['pass']:
                # Show which conditions failed
                failed = [k for k, v in result.items() if k.startswith('c') and not v]
                print(f"             Failed: {', '.join(failed)}")
                print(f"             Rev Growth: {result['rev_growth']}, PEG: {result['peg']}")
        else:
            print(f"{stock:12} ✗ No data")
        print()
