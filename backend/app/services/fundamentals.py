import yfinance as yf
from functools import lru_cache

class FundamentalService:
    @staticmethod
    @lru_cache(maxsize=32)
    def get_fundamentals(symbol: str):
        """
        Fetches key fundamental metrics for a given symbol.
        Returns a simplified dictionary.
        """
        try:
            # Re-use normalization logic logic or trust incoming symbol from MarketDataService?
            # Ideally main.py passes the normalized symbol.
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Helper to safely get value or None
            def get_val(key, default=None):
                return info.get(key, default)

            # Robust Market Cap Formatting
            mcap = get_val('marketCap')
            formatted_mcap = "—"
            if mcap:
                if mcap > 1e12: formatted_mcap = f"{mcap/1e12:.2f}T"
                elif mcap > 1e9: formatted_mcap = f"{mcap/1e9:.2f}B"
                elif mcap > 1e7: formatted_mcap = f"{mcap/1e7:.2f}Cr" # Special handling for clarity? sticking to B/M usually standard
                elif mcap > 1e6: formatted_mcap = f"{mcap/1e6:.2f}M"
                else: formatted_mcap = f"{mcap:.0f}"

            data = {
                "market_cap": formatted_mcap,
                "pe_ratio": round(get_val('trailingPE', 0), 2) if get_val('trailingPE') else None,
                "forward_pe": round(get_val('forwardPE', 0), 2) if get_val('forwardPE') else None,
                "book_value": round(get_val('bookValue', 0), 2) if get_val('bookValue') else None,
                "pb_ratio": round(get_val('priceToBook', 0), 2) if get_val('priceToBook') else None,
                "dividend_yield": round(get_val('dividendYield', 0) * 100, 2) if get_val('dividendYield') else None,
                "roe": round(get_val('returnOnEquity', 0) * 100, 2) if get_val('returnOnEquity') else None,
                "profit_margin": round(get_val('profitMargins', 0) * 100, 2) if get_val('profitMargins') else None,
                "52w_high": get_val('fiftyTwoWeekHigh'),
                "52w_low": get_val('fiftyTwoWeekLow'),
                "sector": get_val('sector', '—'),
                "industry": get_val('industry', '—'),
                "website": get_val('website'),
                "long_name": get_val('longName', symbol)
            }
            
            # Simple health check
            # Undervalued? (Simplified heuristic)
            is_undervalued = False
            if data['pe_ratio'] and data['pe_ratio'] < 20 and data['pb_ratio'] and data['pb_ratio'] < 1.5:
                is_undervalued = True
            data['is_undervalued'] = is_undervalued
            
            return data

        except Exception as e:
            print(f"Error fetching fundamentals for {symbol}: {e}")
            return None
