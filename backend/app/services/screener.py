import yfinance as yf
import pandas as pd
import concurrent.futures
import time
import datetime
import pytz
from typing import List, Dict, Optional

# ── Server-side in-memory cache ────────────────────────────────────────────────
_SCREENER_CACHE: Optional[List[Dict]] = None
_SCREENER_CACHE_TIME: float = 0.0
_SCREENER_TTL_MARKET    = 60 * 60       # 60 min during market hours
_SCREENER_TTL_OFFMARKET = 6 * 60 * 60  # 6 hours off-market / overnight

def _is_market_open() -> bool:
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(ist)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return datetime.time(9, 15) <= t <= datetime.time(15, 30)

def _cache_ttl() -> float:
    return _SCREENER_TTL_MARKET if _is_market_open() else _SCREENER_TTL_OFFMARKET

# ──────────────────────────────────────────────────────────────────────────────

class ScreenerService:
    @staticmethod
    def _screen_single(sym: str) -> Optional[Dict]:
        try:
            from app.services.market_data import MarketDataService
            import os
            
            # --- PHASE 1: Fetch Stats (Proxy-Aware) ---
            # On Render, yfinance .info/.quarterly_financials is almost always blocked.
            # Use our proxy-based stats fetcher as primary on Render, or as fallback.
            stats = None
            is_render = os.getenv("RENDER") is not None
            
            if is_render:
                stats = MarketDataService.get_yahoo_stats_via_proxy(sym)
                
            ticker_sym = MarketDataService.normalize_symbol(sym)
            ticker = yf.Ticker(ticker_sym)
            
            if not stats:
                # Fallback to standard yf (works locally usually)
                try:
                    info = ticker.info
                    qf = ticker.quarterly_financials
                    if not qf.empty:
                        stats = {'info': info, 'quarterly_financials': qf}
                except Exception:
                    pass
            
            if not stats:
                # Final attempt with proxy if not already tried
                if not is_render:
                    stats = MarketDataService.get_yahoo_stats_via_proxy(sym)
            
            if not stats or stats['quarterly_financials'] is None or stats['quarterly_financials'].empty:
                return None
                
            info = stats['info']
            qf = stats['quarterly_financials']

            # --- PHASE 2: Data Extraction ---
            # Use prioritized OHLCV for 'currentPrice' if possible
            df, _, _ = MarketDataService.get_ohlcv(ticker_sym, "1D")
            latest_price = 0
            if df is not None and not df.empty:
                latest_price = float(df['close'].iloc[-1])

            if latest_price:
                info['currentPrice'] = latest_price
            
            if qf.empty or len(qf.columns) < 3:
                return None

            sales = qf.loc['Total Revenue'] if 'Total Revenue' in qf.index else None
            profit = qf.loc['Net Income'] if 'Net Income' in qf.index else None
            if sales is None or profit is None:
                return None

            eps_key = 'Basic EPS' if 'Basic EPS' in qf.index else 'Diluted EPS' if 'Diluted EPS' in qf.index else None
            eps = qf.loc[eps_key] if eps_key else pd.Series()

            de_ratio = info.get('debtToEquity') or 50
            de_check = de_ratio < 100

            peg = info.get('pegRatio')
            rev_growth = info.get('revenueQuarterlyGrowth')
            if rev_growth is None:
                if len(qf.columns) >= 5:
                    latest = sales.iloc[0]
                    prev = sales.iloc[4]
                    if prev > 0:
                        rev_growth = (latest - prev) / prev
            if rev_growth is None:
                rev_growth = 0

            market_cap = info.get('marketCap')
            pe_ratio = info.get('trailingPE')
            roce = info.get('returnOnCapitalEmployed')
            roe = info.get('returnOnEquity')
            effective_roce = roce if roce is not None else roe

            cond_mcap = market_cap and market_cap > 5e9
            cond_pe = False
            if pe_ratio and pe_ratio < 15:
                cond_pe = True
            elif pe_ratio and pe_ratio < 50 and rev_growth > 0.15:
                cond_pe = True
            elif pe_ratio is None:
                cond_pe = True if rev_growth > 0.2 else False

            cond_roce = effective_roce and effective_roce > 0.20
            cond_sales_growth = sales.iloc[0] >= sales.iloc[1]
            cond_profit_growth = profit.iloc[0] > profit.iloc[1]
            cond_profit_pos = profit.iloc[0] > 0
            cond_high_growth = rev_growth > 0.10

            cond_peg = False
            if peg is not None and peg < 1.5:
                cond_peg = True
            elif peg is None and cond_high_growth:
                cond_peg = True
            elif pe_ratio and pe_ratio < 25:
                cond_peg = True

            if (cond_mcap and de_check and cond_profit_pos and
               (cond_roce or cond_high_growth) and
               (cond_pe or cond_peg) and
               (cond_sales_growth or cond_profit_growth)):
                return {
                    "symbol": sym,
                    "name": info.get('longName', sym),
                    "cmp": info.get('currentPrice', 0),
                    "sales_growth": f"{rev_growth*100:.1f}%",
                    "peg": round(peg, 2) if peg is not None else "N/A",
                    "debt_equity": round(de_ratio/100 if de_ratio > 2 else de_ratio, 2)
                }

        except Exception:
            pass
        return None

    @staticmethod
    def screen_symbols(symbols: List[str]) -> List[Dict]:
        """
        Screens a list of symbols concurrently with in-memory caching.
        Cache TTL: 60 min during market hours, 6 hours off-market.
        """
        global _SCREENER_CACHE, _SCREENER_CACHE_TIME

        # ── Return cached result if still fresh ──
        age = time.time() - _SCREENER_CACHE_TIME
        if _SCREENER_CACHE is not None and age < _cache_ttl():
            print(f"[Screener] Returning cached results ({int(age)}s old, TTL={int(_cache_ttl())}s)")
            return _SCREENER_CACHE

        print(f"[Screener] Running fresh screen on {len(symbols)} symbols...")
        results = []

        # 15 workers + 6s per-symbol timeout to avoid hanging on Render
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            future_to_sym = {
                executor.submit(ScreenerService._screen_single, sym): sym
                for sym in symbols
            }
            for future in concurrent.futures.as_completed(future_to_sym, timeout=90):
                sym = future_to_sym[future]
                try:
                    data = future.result(timeout=6)
                    if data:
                        results.append(data)
                except concurrent.futures.TimeoutError:
                    print(f"[Screener] Timeout: {sym}")
                except Exception as exc:
                    print(f"[Screener] Error {sym}: {exc}")

        # ── Cache the results ──
        _SCREENER_CACHE = results
        _SCREENER_CACHE_TIME = time.time()
        print(f"[Screener] Done. {len(results)} stocks passed. Cached for {int(_cache_ttl()/60)} min.")
        return results
