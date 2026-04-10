import yfinance as yf
from functools import lru_cache
import time

class FundamentalService:
    # Minimal in-memory cache to avoid heavy info calls
    _cache = {}
    CACHE_TTL = 3600 # 1 hour for fundamentals
    ERROR_CACHE_TTL = 600 # 10 minutes for rate limit failures / empty responses

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
            # Use shorter TTL for error/empty states
            ttl = cls.CACHE_TTL if not entry.get('is_error') else cls.ERROR_CACHE_TTL
            if (now - entry['timestamp']) < ttl:
                return entry['data']

        try:
            from app.services.market_data import MarketDataService
            stats = MarketDataService.get_yahoo_stats_via_proxy(symbol)
            
            if not stats or not stats.get('info'):
                # Fallback check for very simple info if proxy fails
                old_data = cls._cache[symbol]['data'] if symbol in cls._cache else None
                cls._cache[symbol] = {
                    'timestamp': now,
                    'data': old_data,
                    'is_error': True
                }
                return old_data

            info = stats['info']

            # Robust Market Cap Formatting
            mcap = info.get('marketCap')
            formatted_mcap = "—"
            if mcap:
                if mcap >= 1e12: formatted_mcap = f"{mcap/1e12:.2f}T"
                elif mcap >= 1e9: formatted_mcap = f"{mcap/1e9:.2f}B"
                elif mcap >= 1e7: formatted_mcap = f"{mcap/1e7:.2f}Cr"
                elif mcap >= 1e5: formatted_mcap = f"{mcap/1e5:.2f}L"
                else: formatted_mcap = f"{mcap:.0f}"

            data = {
                "market_cap": formatted_mcap,
                "pe_ratio": float(round(info.get('trailingPE', 0), 2)) if info.get('trailingPE') else None,
                "forward_pe": float(round(info.get('forwardPE', 0), 2)) if info.get('forwardPE') else None,
                "book_value": float(round(info.get('bookValue', 0), 2)) if info.get('bookValue') else None,
                "pb_ratio": float(round(info.get('priceToBook', 0), 2)) if info.get('priceToBook') else None,
                "dividend_yield": float(round(info.get('dividendYield', 0) * 100, 2)) if info.get('dividendYield') else None,
                "roe": float(round(info.get('returnOnEquity', 0) * 100, 2)) if info.get('returnOnEquity') else None,
                "profit_margin": float(round(info.get('profitMargins', 0) * 100, 2)) if info.get('profitMargins') else None,
                "52w_high": float(info.get('fiftyTwoWeekHigh')) if info.get('fiftyTwoWeekHigh') else None,
                "52w_low": float(info.get('fiftyTwoWeekLow')) if info.get('fiftyTwoWeekLow') else None,
                "sector": str(info.get('sector', '—')),
                "industry": str(info.get('industry', '—')),
                "website": str(info.get('website', '')),
                "long_name": str(info.get('longName', symbol))
            }
            
            # Simple health check
            pe = data.get('pe_ratio')
            pb = data.get('pb_ratio')
            is_undervalued = False
            if pe is not None and 0 < pe < 25 and pb is not None and 0 < pb < 2.5:
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
            # Cache exception as error state to avoid immediate retry
            old_data = cls._cache[symbol]['data'] if symbol in cls._cache else None
            cls._cache[symbol] = {
                'timestamp': now,
                'data': old_data,
                'is_error': True
            }
            return old_data
