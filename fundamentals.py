import yfinance as yf
from functools import lru_cache
import time

class FundamentalService:
    # Minimal in-memory cache to avoid heavy info calls
    _cache = {}
    CACHE_TTL = 3600 # 1 hour for fundamentals

    @classmethod
    def get_fundamentals(cls, symbol: str):
        """
        Fetches key fundamental metrics for a given symbol.
        Returns a simplified dictionary.
        """
        # 0. Check Cache
        now = time.time()
        if symbol in cls._cache:
            entry = cls._cache[symbol]
            if (now - entry['timestamp']) < cls.CACHE_TTL:
                return entry['data']

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or len(info) < 5:
                # If info is mostly empty (common during rate limits), try to return old cache if exists
                if symbol in cls._cache:
                    return cls._cache[symbol]['data']
                return None

            # Helper to safely get value or None
            def get_val(key, default=None):
                return info.get(key, default)

            # Robust Market Cap Formatting
            mcap = get_val('marketCap')
            formatted_mcap = "—"
            if mcap:
                if mcap > 1e12: formatted_mcap = f"{mcap/1e12:.2f}T"
                elif mcap > 1e9: formatted_mcap = f"{mcap/1e9:.2f}B"
                elif mcap > 1e7: formatted_mcap = f"{mcap/1e7:.2f}Cr"
                elif mcap > 1e6: formatted_mcap = f"{mcap/1e6:.2f}M"
                else: formatted_mcap = f"{mcap:.0f}"

            data = {
                "market_cap": formatted_mcap,
                "pe_ratio": float(round(get_val('trailingPE', 0), 2)) if get_val('trailingPE') else None,
                "forward_pe": float(round(get_val('forwardPE', 0), 2)) if get_val('forwardPE') else None,
                "book_value": float(round(get_val('bookValue', 0), 2)) if get_val('bookValue') else None,
                "pb_ratio": float(round(get_val('priceToBook', 0), 2)) if get_val('priceToBook') else None,
                "dividend_yield": float(round(get_val('dividendYield', 0) * 100, 2)) if get_val('dividendYield') else None,
                "roe": float(round(get_val('returnOnEquity', 0) * 100, 2)) if get_val('returnOnEquity') else None,
                "profit_margin": float(round(get_val('profitMargins', 0) * 100, 2)) if get_val('profitMargins') else None,
                "52w_high": float(get_val('fiftyTwoWeekHigh')) if get_val('fiftyTwoWeekHigh') else None,
                "52w_low": float(get_val('fiftyTwoWeekLow')) if get_val('fiftyTwoWeekLow') else None,
                "sector": str(get_val('sector', '—')),
                "industry": str(get_val('industry', '—')),
                "website": str(get_val('website', '')),
                "long_name": str(get_val('longName', symbol))
            }
            
            # Simple health check
            is_undervalued = False
            if data['pe_ratio'] and data['pe_ratio'] < 20 and data['pb_ratio'] and data['pb_ratio'] < 1.5:
                is_undervalued = True
            data['is_undervalued'] = bool(is_undervalued)
            
            # Update Cache
            cls._cache[symbol] = {
                'timestamp': now,
                'data': data
            }
            
            return data

        except Exception as e:
            print(f"Error fetching fundamentals for {symbol}: {e}")
            # Fallback to expired cache if available
            if symbol in cls._cache:
                return cls._cache[symbol]['data']
            return None
