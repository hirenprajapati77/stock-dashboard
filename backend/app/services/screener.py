import yfinance as yf
import pandas as pd
import concurrent.futures
from typing import List, Dict

class ScreenerService:
    @staticmethod
    def _screen_single(sym: str) -> Dict:
        try:
            # Add .NS if not present for Indian symbols
            ticker_sym = sym if "." in sym or sym.startswith("^") else f"{sym}.NS"
            ticker = yf.Ticker(ticker_sym)
            
            # Use fast info retrieval if possible, but we need quarterly financials too
            info = ticker.info
            qf = ticker.quarterly_financials
            
            if qf.empty or len(qf.columns) < 3:
                return None
            
            # Extract Data
            sales = qf.loc['Total Revenue']
            profit = qf.loc['Net Income']
            
            eps_key = 'Basic EPS' if 'Basic EPS' in qf.index else 'Diluted EPS' if 'Diluted EPS' in qf.index else None
            eps = qf.loc[eps_key] if eps_key else pd.Series()
            
            # PEG and Debt/Equity
            de_ratio = info.get('debtToEquity')
            if de_ratio is None: de_ratio = 50 # Default safe assumption
            
            # Strict D/E Check: < 1 (which is 100 in yfinance percentage terms)
            de_check = de_ratio < 100 
            
            peg = info.get('pegRatio')
            
            # Revenue Growth
            rev_growth = info.get('revenueQuarterlyGrowth')
            if rev_growth is None:
                if len(qf.columns) >= 5:
                    latest = qf.loc['Total Revenue'].iloc[0]
                    prev = qf.loc['Total Revenue'].iloc[4]
                    if prev > 0:
                        rev_growth = (latest - prev) / prev
            if rev_growth is None: rev_growth = 0
            
            # Fundamentals
            market_cap = info.get('marketCap')
            pe_ratio = info.get('trailingPE')
            roce = info.get('returnOnCapitalEmployed')
            roe = info.get('returnOnEquity')
            
            effective_roce = roce if roce is not None else roe
            
            # Conditions
            # 1. Market Cap > 500 Cr (5e9)
            cond_mcap = market_cap and market_cap > 5e9
            
            # 2. PE < 15 OR (PE < 50 and High Growth)
            cond_pe = False
            if pe_ratio and pe_ratio < 15:
                cond_pe = True
            elif pe_ratio and pe_ratio < 50 and rev_growth > 0.15: # Relaxed for high growth
                cond_pe = True
            elif pe_ratio is None: # If PE is missing but profitable, maybe ok? Let's check profit.
                 # If we have strong profit growth, ignore missing PE
                 cond_pe = True if rev_growth > 0.2 else False

            # 3. ROCE/ROE > 20%
            cond_roce = effective_roce and effective_roce > 0.20
            
            # 4. Financial Trends (Last 3 Quarters)
            cond_sales_growth = sales.iloc[0] >= sales.iloc[1]
            cond_profit_growth = profit.iloc[0] > profit.iloc[1]
            cond_profit_pos = profit.iloc[0] > 0
            
            cond_hight_growth = rev_growth > 0.10
            
            # PEG Check
            cond_peg = False
            if peg is not None and peg < 1.5:
                cond_peg = True
            elif peg is None and cond_hight_growth:
                cond_peg = True # Allow if growth is high but PEG undefined
            elif pe_ratio and pe_ratio < 25:
                 cond_peg = True # Acceptable PE substitute
            
            # Master Check
            # We require: Positive Profit, MCAP check, D/E check, and (Sales OR Profit Growth)
            # Plus reasonable valuation (PE or PEG) and Efficiency (ROCE/ROE)
            
            if (cond_mcap and de_check and cond_profit_pos and 
               (cond_roce or cond_hight_growth) and # Efficiency OR Growth
               (cond_pe or cond_peg) and            # Valuation
               (cond_sales_growth or cond_profit_growth)): # Recent Trend
                
                return {
                    "symbol": sym,
                    "name": info.get('longName', sym),
                    "cmp": info.get('currentPrice', 0),
                    "sales_growth": f"{rev_growth*100:.1f}%",
                    "peg": round(peg, 2) if peg is not None else "N/A",
                    "debt_equity": round(de_ratio/100 if de_ratio > 2 else de_ratio, 2)
                }
                
        except Exception as e:
            # print(f"Error screening {sym}: {e}")
            return None
        return None

    @staticmethod
    def screen_symbols(symbols: List[str]) -> List[Dict]:
        """
        Screens a list of symbols concurrently.
        """
        results = []
        # Use 10 threads for balance between speed and rate limits
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_sym = {executor.submit(ScreenerService._screen_single, sym): sym for sym in symbols}
            
            for future in concurrent.futures.as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    data = future.result()
                    if data:
                        results.append(data)
                except Exception as exc:
                    print(f'{sym} generated an exception: {exc}')
                    
        return results
