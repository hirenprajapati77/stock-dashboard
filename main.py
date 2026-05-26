import sys
from pathlib import Path

# Add backend to path so 'app' module is discoverable
curr_dir = Path(__file__).resolve().parent
if str(curr_dir / "backend") not in sys.path:
    sys.path.append(str(curr_dir / "backend"))

import asyncio
import pandas as pd
import requests
import uvicorn
import os
import collections
from datetime import timedelta
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any

# Simple Memory Logger for Auditing (Auto-clears every 1 hour)
_original_stdout = sys.stdout  # Capture BEFORE any override

class TailLogHandler:
    def __init__(self, maxlen=1000):
        self.logs = collections.deque(maxlen=maxlen)
        self.last_clear = datetime.now()
        self._orig = _original_stdout
        
    def write(self, message):
        try:
            now = datetime.now()
            if (now - self.last_clear).total_seconds() > 3600:
                self.logs.clear()
                self.last_clear = now
                
            if message and message.strip():
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                self.logs.append(f"[{timestamp}] {message.strip()}")
        except Exception:
            pass
        
        # Always write to original stdout
        try:
            self._orig.write(message)
        except Exception:
            pass
    
    def flush(self):
        try:
            self._orig.flush()
        except Exception:
            pass

    def isatty(self):
        return getattr(self._orig, 'isatty', lambda: False)()
        
    def fileno(self):
        return self._orig.fileno()
    
    # Delegate any unknown attribute to the original stdout
    def __getattr__(self, name):
        return getattr(self._orig, name)

# Inject the audit logger into global stdout
audit_tail = TailLogHandler(maxlen=2000)
sys.stdout = audit_tail

# Startup modules
from fastapi import FastAPI, Query, Response, Request, Depends, HTTPException, status, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse, HTMLResponse

from app.services.market_data import MarketDataService
from app.services.fundamentals import FundamentalService
from app.services.fundamental_screener_service import FundamentalScreener
from app.services.sector_service import SectorService
from app.services.constituent_service import ConstituentService
from app.services.market_status_service import MarketStatusService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.fibonacci import FibonacciEngine
from app.engine.cpr import CPREngine
from app.engine.insights import InsightEngine
from app.engine.confidence import ConfidenceEngine
from app.ai.engine import AIEngine

from app.services.fyers_service import FyersService
from app.services.fyers_socket_service import FyersSocketService
from app.utils.market_calendar import MarketCalendar
from app.config import fyers_config

# Trade Decision Engine Imports
from app.trade_engine.models import MarketContext, TradeDecision
from app.trade_engine.trade_decision_service import TradeDecisionService as V5TradeEngine
from app.trade_engine.trade_builder import TradeBuilder


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _warmup():
        try:
            import time

            print("[Warmup] Pre-warming screener cache in background...")
            t0 = time.time()

            def _sync_warmup():
                from app.services.screener_service import ScreenerService
                from app.services.constituent_service import ConstituentService
                from app.services.fyers_service import FyersService
                
                # 0. Load existing token
                FyersService.load_token()
                
                # 1. Warm up symbol master for search (NSE symbols)
                print("[Warmup] Syncing Fyers symbol master...", flush=True)
                FyersService.update_symbol_master()
                
                # 2. Warm up screener cache
                print("[Warmup] Pre-warming screener cache...", flush=True)
                ScreenerService.get_screener_data()

            # Throttled Warmup: Wait 60s for server to stabilize on Render before heavy data fetch
            if os.getenv("RENDER"):
                print("[Warmup] Render environment detected. Sleeping 60s for stabilization...", flush=True)
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(5) # Small local delay

            await asyncio.to_thread(_sync_warmup)
            print(f"[Warmup] Done in {time.time() - t0:.1f}s")
        except Exception as e:
            print(f"[Warmup] Error: {e}")

    # --- SAFETY SYNC LOOP (60s — corrects drift, populates OHLCV buffers) ---
    async def safety_sync_loop():
        """
        Runs every 60s. Performs a full intelligence cycle to:
        1. Populate _realtime_buffers for new symbols (so WebSocket can update them).
        2. Correct any drift from missed WebSocket ticks.
        3. Acts as the sole data source when WebSocket is disconnected.
        Does NOT overwrite valid real-time data if it is more recent than the sync.
        """
        SYNC_INTERVAL = 120.0  # Increased from 60s — reduces YF fetch frequency
        from app.services.screener_service import ScreenerService
        import time
        print("[SafetySync] Safety sync loop started (120s interval).", flush=True)
        while True:
            try:
                if MarketCalendar.is_market_open():
                    last_rt = ScreenerService._intelligence_cache.get("last_updated")
                    if last_rt:
                        age = (datetime.now() - last_rt).total_seconds()
                        # Only run full scan if last real-time update was > 90s ago
                        # (meaning WebSocket is inactive or stale for >1.5 cycles)
                        if age < 90:
                            await asyncio.sleep(SYNC_INTERVAL)
                            continue
                    await asyncio.to_thread(ScreenerService.update_intelligence_cycle, timeframe="1D")
                    # Populate realtime buffers from latest batch data
                    _populate_realtime_buffers(ScreenerService)
                else:
                    print("[SafetySync] Market closed. Serving stale cache if available.", flush=True)
                    # Cause 2 Fix: If cache is empty (e.g. first weekend load), trigger ONE background scan
                    from app.services.screener_service import ScreenerService as _SC
                    if not _SC._intelligence_cache.get("data"):
                        print("[SafetySync] Cache empty on market-closed — triggering one-time background scan.", flush=True)
                        try:
                            await asyncio.to_thread(_SC.update_intelligence_cycle, timeframe="1D")
                        except Exception as _e:
                            print(f"[SafetySync] Weekend scan error: {_e}", flush=True)
            except Exception as e:
                print(f"[SafetySync] Error: {e}", flush=True)
            await asyncio.sleep(SYNC_INTERVAL)

    def _populate_realtime_buffers(ScreenerService):
        """Seeds the real-time OHLCV buffers from latest screener batch data."""
        try:
            from app.services.market_data import MarketDataService
            for sym_data in ScreenerService._intelligence_cache.get("data", []):
                symbol = sym_data.get("symbol", "")
                if not symbol or symbol in ScreenerService._realtime_buffers:
                    continue  # Already has a live buffer; don't overwrite
                # Try to get cached OHLCV from market data layer
                yf_sym = symbol + ".NS"
                cache_entry = MarketDataService._ohlcv_cache.get(yf_sym)
                if cache_entry and 'df' in cache_entry:
                    df = cache_entry['df']
                    if not df.empty:
                        ScreenerService._realtime_buffers[symbol] = df.tail(100).copy()
        except Exception as e:
            print(f"[SafetySync] Buffer populate error: {e}", flush=True)

    # --- WEBSOCKET STREAMING SERVICE ---
    async def start_websocket_service():
        """Starts FyersSocketService after warmup completes."""
        await asyncio.sleep(130)  # Wait safely after warmup (60s sleep + ~60s sync)
        from app.services.screener_service import ScreenerService
        # Build Fyers-format symbol list from screener constituents
        try:
            from app.services.constituent_service import ConstituentService
            symbols_raw = ConstituentService.get_nifty100_symbols()
            # Convert to Fyers format: SBIN -> NSE:SBIN-EQ
            fyers_symbols = [f"NSE:{s.replace('.NS','').replace('.BO','')}-EQ" for s in symbols_raw if s]
            print(f"[FyersSocket] Registering {len(fyers_symbols)} symbols for streaming.", flush=True)
            await FyersSocketService.start(symbols=fyers_symbols)
        except Exception as e:
            print(f"[FyersSocket] Startup error: {e}", flush=True)

    asyncio.create_task(safety_sync_loop())
    asyncio.create_task(start_websocket_service())
    asyncio.create_task(_warmup())
    yield
    await FyersSocketService.stop()


# Authentication Constants
AUTH_COOKIE_NAME = "sr_pro_session"
ADMIN_USER = "Admin"
ADMIN_PASS = "SPAdmin@123"

def get_current_user(sr_pro_session: Optional[str] = Cookie(None)):
    # Bypassing login for development
    return ADMIN_USER
    # if sr_pro_session != "authenticated_admin":
    #     return None
    # return ADMIN_USER

def login_required(user: Optional[str] = Depends(get_current_user)):
    # Always allow in development
    return user
    # if not user:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Authentication required",
    #     )
    # return user

app = FastAPI(title="Support & Resistance Dashboard", lifespan=lifespan)
ai_engine = AIEngine()


def _json_serializable(obj):
    """Recursively convert numpy types and non-serializable objects to python types."""
    import numpy as np
    import math
    
    if isinstance(obj, dict):
        return {_json_serializable(k): _json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_json_serializable(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return [_json_serializable(v) for v in obj.tolist()]
    
    # Handle numpy scalars by converting to python types first
    if hasattr(obj, 'item') and callable(getattr(obj, 'item')):
        obj = obj.item()

    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return None if math.isnan(val) or math.isinf(val) else val
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.bool_, bool, np.bool_)):
        return bool(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    
    # Handle string cases for numpy specifically if they slipped through
    if str(type(obj)).find('numpy') != -1:
        if str(type(obj)).find('bool') != -1: return bool(obj)
        if str(type(obj)).find('int') != -1: return int(obj)
        if str(type(obj)).find('float') != -1:
            val = float(obj)
            return None if math.isnan(val) or math.isinf(val) else val

    return obj

def _to_price_list(levels):
    prices = []
    for level in levels or []:
        if not isinstance(level, dict):
            continue
        value = level.get("price")
        if value is None:
            continue
        try:
            prices.append(float(value))
        except (TypeError, ValueError):
            continue
    return prices


def _resolve_summary_levels(cmp, supports, resistances, mtf_levels=None):
    all_supports = _to_price_list(supports) + _to_price_list((mtf_levels or {}).get("supports", []))
    all_resists = _to_price_list(resistances) + _to_price_list((mtf_levels or {}).get("resistances", []))
    
    # Filter and sort to get nearest
    s_nearest = max([s for s in all_supports if s < cmp]) if any(s < cmp for s in all_supports) else 0.0
    r_nearest = min([r for r in all_resists if r > cmp]) if any(r > cmp for r in all_resists) else 0.0
    
    return s_nearest, r_nearest




def _build_trade_signal(ema_bias, risk_reward):
    if ema_bias == "Bullish" and risk_reward is not None and risk_reward >= 1.5:
        return "BUY", "Bullish bias + favorable risk/reward"
    if ema_bias == "Caution":
        return "SELL", "Momentum is weak/cautionary"
    return "HOLD", "Wait for better structure or confirmation"


def _external_base_url(request: Request) -> str:
    # Most reliable detection for Render and SSL terminates proxies
    env_url = os.getenv("FYERS_REDIRECT_URL")
    if env_url and "http" in env_url:
        return env_url.split("/api/v1/fyers/callback")[0].rstrip("/")

    forwarded_host = request.headers.get("x-forwarded-host")
    host = forwarded_host if forwarded_host else request.headers.get("host", "stock-dashboard-9nvy.onrender.com")
    
    # Force https if on render.com or if x-forwarded-proto says so
    proto = request.headers.get("x-forwarded-proto")
    if not proto:
        proto = "https" if "render.com" in host else "http"
    
    return f"{proto}://{host}"


def _resolve_fyers_redirect_url(request: Request) -> str:
    configured_redirect = os.getenv("FYERS_REDIRECT_URL")
    if configured_redirect:
        return fyers_config.normalize_redirect_url(configured_redirect)
    return fyers_config.normalize_redirect_url(
        f"{_external_base_url(request)}/api/v1/fyers/callback"
    )


def _build_fyers_redirect(request: Request, status: str, message: Optional[str] = None) -> str:
    from urllib.parse import urlencode

    params = {"fyers_login": status}
    if message:
        params["fyers_message"] = str(message)[:200]
    return f"{_external_base_url(request)}/?{urlencode(params)}"


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v2/ai-insights", dependencies=[Depends(login_required)])
async def get_ai_insights(symbol: str = "NIFTY50", tf: str = "1D", base_conf: Optional[int] = None):
    """
    Returns assistive AI insights for the given symbol.
    """
    try:
        norm_symbol = MarketDataService.normalize_symbol(symbol)
        df, _ = MarketDataService.get_ohlcv(norm_symbol, tf)
        insights = ai_engine.get_insights(df, base_conf)
        return insights
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v2/regime", dependencies=[Depends(login_required)])
async def get_market_regime_v2(tf: str = "1D"):
    """
    Returns system-wide Market Regime data.
    """
    try:
        from app.services.screener_service import ScreenerService
        regime = ScreenerService._calculate_market_regime(tf)
        return {"status": "success", "data": _json_serializable(regime)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v2/sectors/active", dependencies=[Depends(login_required)])
async def get_active_sectors_v2(tf: str = "1D"):
    """
    Returns active focus rotating sectors.
    """
    try:
        from app.services.screener_service import ScreenerService
        from app.engine.sector_rotation import SectorRotationEngine
        sector_data = ScreenerService._calculate_sector_rotation(tf)
        active_focus = SectorRotationEngine.get_focus_sectors(sector_data)
        return {"status": "success", "data": _json_serializable(active_focus)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v2/screener/us-portfolio", dependencies=[Depends(login_required)])
async def get_us_portfolio_v2(tf: str = "1D"):
    """
    US Quality-Only Portfolio hits.
    """
    try:
        from app.services.screener_service import ScreenerService
        res = ScreenerService.get_screener_data(tf)
        hits = res.get("hits", [])
        us_hits = [h for h in hits if h.get("sectorKey") == "US_PORTFOLIO"]
        return {"status": "success", "data": _json_serializable(us_hits)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v2/portfolio/exposure", dependencies=[Depends(login_required)])
async def get_portfolio_exposure_v2(tf: str = "1D"):
    """
    Portfolio exposure statistics.
    """
    try:
        from app.services.screener_service import ScreenerService
        res = ScreenerService.get_screener_data(tf)
        return {
            "status": "success",
            "data": _json_serializable({
                "total_exposure_pct": 28.0,
                "sector_concentration": res.get("sector_concentration", []),
                "cash_buffer_pct": 30.0,
                "open_positions": 7
            })
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/quotes", dependencies=[Depends(login_required)])
async def get_quotes(symbols: str = Query(...)):
    """
    Returns real-time quotes for a comma-separated list of symbols.
    """
    try:
        sym_list = [s.strip().upper() for s in symbols.split(",")]
        
        # Mapping to Fyers format
        fyers_to_orig = {}
        fyers_symbols = []
        
        INDEX_MAP = {
            "NIFTY50": "NSE:NIFTY50-INDEX",
            "NIFTYBANK": "NSE:NIFTYBANK-INDEX",
            "FINNIFTY": "NSE:FINNIFTY-INDEX",
            "MIDCAP": "NSE:MIDCAPSELECT-INDEX",
            "SENSEX": "BSE:SENSEX-INDEX",
            "NIFTY_BANK": "NSE:NIFTYBANK-INDEX",
            "NIFTY_IT": "NSE:NIFTYIT-INDEX",
            "NIFTY_PHARMA": "NSE:NIFTYPHARMA-INDEX",
            "NIFTY_FMCG": "NSE:NIFTYFMCG-INDEX",
            "NIFTY_AUTO": "NSE:NIFTYAUTO-INDEX",
            "NIFTY_ENERGY": "NSE:NIFTYENERGY-INDEX",
            "NIFTY_METAL": "NSE:NIFTYMETAL-INDEX"
        }

        for s in sym_list:
            if s in INDEX_MAP:
                fs = INDEX_MAP[s]
            elif ":" in s:
                fs = s
            else:
                # Default to NSE Equity
                clean_s = s.replace(".NS", "").replace(".BO", "")
                fs = f"NSE:{clean_s}-EQ"
            
            fyers_symbols.append(fs)
            fyers_to_orig[fs] = s

        quotes = {}
        if FyersService.is_active():
            fyers_quotes = await asyncio.to_thread(FyersService.get_quotes, fyers_symbols)
            # Map back to original symbols
            for fs, q in fyers_quotes.items():
                orig_s = fyers_to_orig.get(fs, fs)
                quotes[orig_s] = q
                # Also add clean version for redundancy (e.g. NSE:RELIANCE-EQ -> RELIANCE)
                clean_orig = orig_s.upper().replace(".NS", "").replace(".BO", "").split(":")[-1].split("-")[0].strip()
                quotes[clean_orig] = q
        
        # Fallback for missing symbols or if Fyers is not active
        from app.services.screener_service import ScreenerService
        intel_data = ScreenerService._intelligence_cache.get("data", [])
        intel_map = {d["symbol"].upper().replace(".NS", ""): d for d in intel_data}
        
        formatted_quotes = {}
        for s in sym_list:
            # Robust cleaning: "NSE:RELIANCE-EQ" -> "RELIANCE", "NIFTY50.NS" -> "NIFTY50"
            clean_s = s.upper().replace(".NS", "").replace(".BO", "").split(":")[-1].split("-")[0].strip()
            q = quotes.get(s)
            
            if q:
                formatted_quotes[s] = {
                    "lp": q.get("lp", 0),
                    "ch": q.get("ch", 0),
                    "chp": q.get("chp", 0)
                }
            elif clean_s in intel_map:
                # Use intel cache if Fyers quote missing
                idat = intel_map[clean_s]
                formatted_quotes[s] = {
                    "lp": idat.get("price", 0),
                    "ch": 0, # Change not directly in intel cache
                    "chp": idat.get("change_pct", 0)
                }
                # Also provide clean key for frontend robustness
                formatted_quotes[clean_s] = formatted_quotes[s]
            else:
                # Final fallback: Check SectorService for indices (NIFTY50, etc)
                try:
                    sector_data, _ = SectorService.get_rotation_data(timeframe="1D", include_constituents=False)
                    for sname, sdata in sector_data.items():
                        # Match NIFTY_BANK, BANK, NIFTY50, or ^NSEBANK
                        if clean_s.replace("_", "") == sname.replace("_", "") or \
                           clean_s == sname.replace("NIFTY_", "") or \
                           clean_s == sdata.get("symbol", "").replace("^", ""):
                            m = sdata.get("metrics", {})
                            formatted_quotes[s] = {
                                "lp": sdata.get("current", {}).get("price", 0),
                                "ch": 0,
                                "chp": m.get("sr", 0) * 100
                            }
                            formatted_quotes[clean_s] = formatted_quotes[s]
                            break
                except Exception:
                    pass
            
            if s not in formatted_quotes:
                # Try yfinance fast_info as last resort for stocks
                try:
                    import yfinance as yf
                    # Avoid appending .NS to indices
                    yf_sym = clean_s if clean_s.startswith("^") else f"{clean_s}.NS"
                    ticker = yf.Ticker(yf_sym)
                    fi = ticker.fast_info
                    lp = float(fi.get('lastPrice') or fi.get('last_price') or 0)
                    prev = float(fi.get('previousClose') or fi.get('previous_close') or 0)
                    chp = ((lp - prev) / prev) * 100 if prev > 0 else 0
                    if lp > 0:
                        formatted_quotes[s] = {"lp": lp, "ch": lp - prev, "chp": chp}
                        formatted_quotes[clean_s] = formatted_quotes[s]
                except Exception:
                    pass
            
            if s not in formatted_quotes:
                formatted_quotes[s] = {"lp": 0, "ch": 0, "chp": 0}
            
        return {"status": "success", "data": formatted_quotes}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/search", dependencies=[Depends(login_required)])
async def search_symbols(q: str = Query(..., min_length=1)):
    """
    Searches for symbols using Fyers symbol master.
    """
    try:
        # 1. Search Fyers Symbols
        results = await asyncio.to_thread(FyersService.search_symbols, q)
        
        # 2. Inject custom keywords
        custom_keywords = {
            "GOLD_IN": "Gold Beess ETF (NSE Proxy - ₹130 range)",
            "SILVER_IN": "Silver Beess ETF (NSE Proxy)",
            "CRUDE_IN": "Indian Crude Proxy (INR Price based on Global Market)",
            "GOLD": "Global Gold Spot (GC=F - $2600 range)",
            "SILVER": "Global Silver Spot (SI=F)",
            "CRUDE": "Crude Oil Global Futures (CL=F)",
            "NIFTY": "Nifty 50 Index (NSE)",
            "BANKNIFTY": "Nifty Bank Index (NSE)",
            "USDINR": "US Dollar / Indian Rupee (Live)",
            "OIL_INDIA": "Oil India Ltd (Stock - ₹500 range)"
        }
        
        custom_results = []
        for kw, desc in custom_keywords.items():
            if q.upper() in kw or q.lower() in desc.lower():
                custom_results.append({
                    "symbol": kw,
                    "shortname": desc,
                    "exchange": "CUSTOM"
                })
        
        # Merge results - Custom first, then Fyers
        return custom_results + results
    except Exception as e:
        print(f"Search error: {e}")
        return []


@app.get("/api/v1/market-status", dependencies=[Depends(login_required)])
async def get_market_status():
    """
    Returns the current market status, phase, and metadata.
    """
    try:
        from app.services.market_status_service import MarketStatusService
        status = MarketStatusService.get_market_status()
        return {"status": "success", "data": status}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Cause 4 Fix: /ping endpoint wakes up Render free-tier on page load (called from frontend)
@app.get("/ping")
async def ping():
    return {"status": "ok", "ts": datetime.now().isoformat()}

@app.get("/api/v1/dashboard", dependencies=[Depends(login_required)])
async def get_dashboard(response: Response, symbol: str = "NIFTY50", tf: str = "1D", strategy: str = "SR", lite: bool = False):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    print(f"DEBUG: Dashboard Request - {symbol} @ {tf} | Strategy: {strategy} | lite={lite}")
    try:
        # 0. Normalize Symbol
        norm_symbol = await asyncio.to_thread(MarketDataService.normalize_symbol, symbol)

        # 1. Parallelize ALL Data Fetching (Primary, MTF, Sector)
        # Cause 3 Fix: Skip MTF when lite=True (Intelligence tab calls)
        higher_tfs = []
        if not lite:
            if tf == "5m": higher_tfs = ["15m", "1H", "1D"]
            elif tf == "15m": higher_tfs = ["1H", "2H", "1D"]
            elif tf == "1H": higher_tfs = ["2H", "4H", "1D"]
            elif tf == "2H": higher_tfs = ["4H", "1D", "1W"]
            elif tf == "1D": higher_tfs = ["1W", "1M"]
            elif tf == "1W": higher_tfs = ["1M"]
            elif tf == "1M": higher_tfs = []

        async def fetch_mtf_wrapper(htf_name):
            try:
                h_df, _, h_err, _ = await asyncio.to_thread(
                    MarketDataService.get_ohlcv, 
                    norm_symbol, 
                    htf_name, 
                    use_fast_info=False
                )
                if h_df.empty: return htf_name, [], []
                
                hs, hr = [], []
                if strategy == "SR":
                    hs, hr = await asyncio.to_thread(SREngine.calculate_sr_levels, h_df)
                elif strategy == "SWING":
                    hs, hr = await asyncio.to_thread(SwingEngine.calculate_swing_levels, h_df)
                elif strategy == "DEMAND_SUPPLY":
                    h_zones = await asyncio.to_thread(ZoneEngine.calculate_demand_supply_zones, h_df)
                    hs = [z for z in h_zones if z['type'] == 'DEMAND']
                    hr = [z for z in h_zones if z['type'] == 'SUPPLY']
                
                for h in hs: h['timeframe'] = htf_name
                for h in hr: h['timeframe'] = htf_name
                return htf_name, hs, hr
            except Exception as e:
                print(f"MTF {htf_name} error: {e}")
                return htf_name, [], []

        async def get_sector_state_task():
            try:
                sec_name = await asyncio.to_thread(ConstituentService.get_sector_for_ticker, norm_symbol)
                sec_state = "NEUTRAL"
                if sec_name:
                    rotation_data, _ = await asyncio.to_thread(
                        SectorService.get_rotation_data, 
                        timeframe="1D", # Always use Daily for sector context
                        include_constituents=False
                    )
                    if rotation_data and sec_name in rotation_data:
                        sec_state = rotation_data[sec_name]['metrics']['state']
                return sec_name, sec_state
            except Exception as e:
                print(f"Sector error: {e}")
                return None, "NEUTRAL"

        # Start everything in parallel
        primary_task = asyncio.create_task(asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, tf))
        sector_task = asyncio.create_task(get_sector_state_task())
        mtf_tasks = [asyncio.create_task(fetch_mtf_wrapper(h)) for h in higher_tfs]

        # 2. Await Primary Data first (Essential)
        try:
            # 14 seconds allows Fyers to fail (timeout 8s) and smoothly hit Yahoo Proxy fallback
            df, currency, error, source_type = await asyncio.wait_for(primary_task, timeout=14.0)
            
            # SESSION EXPIRED DETECTION:
            # If the primary provider (Fyers) reports token expired, make it transparent
            is_expired = error and "Fyers Token Expired" in str(error)
            
            # Map source_type to standardized UI labels
            # If df is not empty, we proceed with whatever source we have (live or cache)
            source = "expired" if is_expired else (source_type if source_type != "error" else "fallback")
            
            if df.empty:
                status_code = 401 if is_expired else 200
                return JSONResponse(
                    status_code=status_code,
                    content={
                        "status": "error", 
                        "message": error or f"No data found for {symbol}. (API Rate Limit)", 
                        "source": source
                    }
                )
        except asyncio.TimeoutError:
            print(f"CRITICAL: Primary data fetch timed out for {symbol} after 14s.")
            return {"status": "error", "message": "Market data fetch timed out. Please retry."}
            
        cmp = float(df['close'].iloc[-1])

        
        # 3. Await Secondary Data (with short residual timeout)
        # We give secondary tasks 3 more seconds or until they finish.
        try:
            secondary_results = await asyncio.wait_for(
                asyncio.gather(sector_task, *mtf_tasks, return_exceptions=True),
                timeout=4.0
            )
        except asyncio.TimeoutError:
            print("WARNING: Secondary data fetching timed out. Using partial results.")
            secondary_results = [ (None, "NEUTRAL") ] + [ (h, [], []) for h in higher_tfs ]

        # Parse Secondary Results
        sector_res = secondary_results[0]
        if isinstance(sector_res, tuple):
            sector_name, sector_state = sector_res
        else:
            sector_name, sector_state = None, "NEUTRAL"

        mtf_levels: Dict[str, List[Any]] = {"supports": [], "resistances": []}
        if isinstance(secondary_results, list) and len(secondary_results) > 1:
            mtf_results = secondary_results[1:]
            for res in mtf_results:
                if isinstance(res, tuple) and len(res) == 3:
                    _, hs, hr = res
                    if isinstance(hs, list): mtf_levels["supports"].extend(hs)
                    if isinstance(hr, list): mtf_levels["resistances"].extend(hr)

        # 4. Strategy Execution (Fast)
        supports, resistances = [], []
        strategy_result = {}
        rendered_levels = {"supports": [], "resistances": []}

        # Normalize strategy codes (Backward Compatibility)
        if strategy == "FIB": strategy = "FIBONACCI"
        if strategy == "DS": strategy = "DEMAND_SUPPLY"
        if strategy == "TREND": strategy = "SWING"

        if strategy == "SR":
            supports, resistances = await asyncio.to_thread(SREngine.calculate_sr_levels, df)
            strategy_result = await asyncio.to_thread(SREngine.runSRStrategy, df, sector_state, supports, resistances)
            rendered_levels = {"supports": supports, "resistances": resistances}
        elif strategy == "SWING":
            supports, resistances = await asyncio.to_thread(SwingEngine.calculate_swing_levels, df, tf)
            # Use same DF for structure if MTF failed
            strategy_result = await asyncio.to_thread(SwingEngine.runSwingStrategy, df, sector_state, "NEUTRAL", supports, resistances)
            rendered_levels = {"supports": supports, "resistances": resistances}
        elif strategy == "DEMAND_SUPPLY":
            zones = await asyncio.to_thread(ZoneEngine.calculate_demand_supply_zones, df)
            strategy_result = await asyncio.to_thread(ZoneEngine.runDemandSupplyStrategy, df, sector_state, zones)
            
            # Map zones to levels for primary display and summary calculation
            supp_zones = [z for z in zones if isinstance(z, dict) and z.get('type') == 'DEMAND']
            res_zones = [z for z in zones if isinstance(z, dict) and z.get('type') == 'SUPPLY']
            
            # Sort by proximity to CMP
            supp_sorted = sorted(supp_zones, key=lambda x: float(str(x.get('price', 0.0))), reverse=True)
            res_sorted = sorted(res_zones, key=lambda x: float(str(x.get('price', 0.0))))
            
            supports = supp_sorted
            resistances = res_sorted
            
            # Use explicit list slicing to avoid type-checker confusion
            s_top = supp_sorted[0:4] if len(supp_sorted) >= 4 else supp_sorted
            r_top = res_sorted[0:4] if len(res_sorted) >= 4 else res_sorted
            rendered_levels = {"supports": s_top, "resistances": r_top}
        elif strategy == "FIBONACCI":
            fib_results = await asyncio.to_thread(FibonacciEngine.calculate_fib_levels, df)
            strategy_result = await asyncio.to_thread(FibonacciEngine.runFibonacciStrategy, df, sector_state, fib_results)
            
            supports = fib_results.get("supports", [])
            resistances = fib_results.get("resistances", [])
            rendered_levels = {"supports": supports, "resistances": resistances}
        elif strategy == "CPR":
            cpr_results = await asyncio.to_thread(CPREngine.calculate_cpr_levels, df)
            strategy_result = await asyncio.to_thread(CPREngine.runCPRStrategy, df, sector_state, cpr_results)
            
            supports = cpr_results.get("supports", [])
            resistances = cpr_results.get("resistances", [])
            rendered_levels = {"supports": supports, "resistances": resistances}

        # 5. Technical & AI Insights
        try:
            from app.engine.insights import InsightEngine
            tech_insights = await asyncio.to_thread(InsightEngine.get_technical_summary, df)
            
            ai_analysis = await asyncio.wait_for(asyncio.to_thread(ai_engine.get_insights, df), timeout=5.0)
            # Merge technicals into insights
            ai_analysis.update(tech_insights)
        except asyncio.TimeoutError:
            print("WARNING: AI analysis timed out. Using technical fallbacks.")
            from app.engine.insights import InsightEngine
            ai_analysis = await asyncio.to_thread(InsightEngine.get_technical_summary, df)
            ai_analysis.update({"priority": {"level": "MEDIUM", "score": 50}, "breakout": {"breakout_quality": "NORMAL", "reason": "AI timeout"}})
        except Exception as e:
            print(f"ERROR: Insights failed: {e}")
            from app.engine.insights import InsightEngine
            ai_analysis = await asyncio.to_thread(InsightEngine.get_technical_summary, df)
        if not ai_analysis: ai_analysis = {}

        # 5. Final Formatting - Filter out NaN candles that crash lightweight-charts
        ohlcv = []
        import math
        from app.engine.vwap import VWAPEngine
        try:
            vwap_series = VWAPEngine.calculate_vwap(df, tf)
        except Exception as ve:
            print(f"[Backend VWAP] Calculation error: {ve}")
            vwap_series = pd.Series(dtype=float)

        for i in range(len(df)):
            try:
                o, h, l, c = float(df['open'].iloc[i]), float(df['high'].iloc[i]), float(df['low'].iloc[i]), float(df['close'].iloc[i])
                if math.isnan(o) or math.isnan(h) or math.isnan(l) or math.isnan(c):
                    continue
                    
                v = float(df['volume'].iloc[i]) if 'volume' in df.columns else 0.0
                vw = float(vwap_series.iloc[i]) if not vwap_series.empty and i < len(vwap_series) else None
                if vw is not None and math.isnan(vw):
                    vw = None
                ohlcv.append({
                    "time": int(df.index[i].timestamp()),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": 0.0 if math.isnan(v) else v,
                    "vwap": vw
                })
            except: continue
            
        # Initialize response_data with meta and structured levels
        ns, nr = _resolve_summary_levels(cmp, supports, resistances, mtf_levels)
        
        # Extract CPR specific data if selected
        cpr_info = {}
        virgin_cprs_info = []
        if strategy == "CPR" and 'cpr_results' in locals():
            cpr_info = cpr_results.get("cpr", {})
            virgin_cprs_info = cpr_results.get("virgin_cprs", [])

        response_data: Dict[str, Any] = {
            "status": "success",
            "meta": {
                "symbol": symbol,
                "norm_symbol": norm_symbol,
                "tf": tf,
                "strategy": strategy,
                "cmp": cmp,
                "currency": currency or "INR",
                "last_update": datetime.now().strftime("%H:%M:%S")
            },
            "ohlcv": ohlcv,
            "levels": {
                "primary": rendered_levels,
                "mtf": mtf_levels
            },
            "strategy": strategy_result,
            "insights": ai_analysis,
            "ai_analysis": {
                "status": "success",
                **ai_analysis
            },
            "sector_info": {
                "name": sector_name,
                "state": sector_state
            },
            "summary": {
                "trade_signal": str(strategy_result.get("entryStatus", strategy_result.get("signal", "HOLD"))),
                "trade_signal_reason": strategy_result.get("bias", "Neutral bias"),
                "side": strategy_result.get("side", "LONG"),
                "confidence": int(strategy_result.get("confidence", 50)),
                "nearest_support": ns or 0.0,
                "nearest_resistance": nr or 0.0,
                "stop_loss": strategy_result.get("stopLoss") or 0.0,
                "target": strategy_result.get("target") or 0.0,
                "risk_reward": strategy_result.get("riskReward") or 0.0,
                "market_regime": strategy_result.get("additionalMetrics", {}).get("regime", ai_analysis.get("regime", "STABLE"))
            }
        }

        if strategy == "CPR":
            response_data["cpr"] = cpr_info
            response_data["virgin_cprs"] = virgin_cprs_info

        # 6. Trade Decision Add-on (Unified V5 Execution Edge)
        try:
            from app.trade_engine.models import MarketContext
            from app.trade_engine.trade_decision_service import TradeDecisionService as V5Engine
            from app.engine.insights import InsightEngine as MetricsEngine
            from app.engine.zones import ZoneEngine as VolEngine
            from app.engine.regime import MarketRegimeEngine as TrendEngine
            
            # Fetch real-time quotes for OI/PCR
            quotes = {}
            if FyersService.is_active():
                # For stocks, we might want the future symbol, but for now we get the equity quote
                # Fyers often provides OI in the quotes for many symbols
                quotes = await asyncio.to_thread(FyersService.get_quotes, [norm_symbol])
            
            symbol_quote = quotes.get(norm_symbol, {})
            oi = symbol_quote.get("oi", 0)
            oi_prev = symbol_quote.get("poi", 0) # Previous day OI
            
            # Simple OI buildup logic
            oi_buildup = "Neutral"
            if oi > 0 and oi_prev > 0:
                oi_change = ((oi - oi_prev) / oi_prev) * 100
                if oi_change > 5 and strategy_result.get("side") == "LONG": oi_buildup = "Long Buildup"
                elif oi_change > 5 and strategy_result.get("side") == "SHORT": oi_buildup = "Short Buildup"
                elif oi_change < -5 and strategy_result.get("side") == "LONG": oi_buildup = "Short Covering"
                elif oi_change < -5 and strategy_result.get("side") == "SHORT": oi_buildup = "Long Unwinding"

            # Calculate metrics for V5 Engine
            atr_series = await asyncio.to_thread(VolEngine.calculate_atr, df)
            atr = float(atr_series.iloc[-1]) if not atr_series.empty else cmp * 0.01
            adx = await asyncio.to_thread(MetricsEngine.get_adx, df)
            vol_ratio = await asyncio.to_thread(MetricsEngine.get_volume_ratio, df)
            
            # Build Market Context
            context = MarketContext(
                symbol=symbol,
                price=cmp,
                open=float(df['open'].iloc[-1]),
                high=float(df['high'].iloc[-1]),
                low=float(df['low'].iloc[-1]),
                close=float(df['close'].iloc[-1]),
                prev_close=float(df['close'].iloc[-2]) if len(df) > 1 else cmp,
                supports=[float(s['price']) for s in supports if 'price' in s],
                resistances=[float(r['price']) for r in resistances if 'price' in r],
                atr=atr,
                adx=adx,
                volume_ratio=vol_ratio,
                trend=strategy_result.get("side", "BULLISH"),
                oi_data={"oi": oi, "oi_buildup": oi_buildup}
            )
            
            # Generate V5 Decision
            decision = await asyncio.to_thread(V5Engine.generate_trade, context, tf)
            import json
            if hasattr(decision, "model_dump_json"):
                decision_dict = json.loads(decision.model_dump_json())
            else:
                decision_dict = json.loads(decision.json())
            
            # Inject into response
            response_data["decision"] = decision_dict
            response_data["insights"]["oi_buildup"] = oi_buildup
            response_data["insights"]["pcr"] = symbol_quote.get("pcr", 0.95) # Placeholder or from quotes if available
            
            # SYNC FIX: Ensure the summary signal matches the V5 decision
            response_data["summary"]["trade_signal"] = decision_dict.get("meta_score", {}).get("final_decision", "WATCH")
            response_data["summary"]["confidence"] = decision_dict.get("meta_score", {}).get("meta_score", 50)
            response_data["summary"]["market_regime"] = decision_dict.get("market_regime", {}).get("regime", "STABLE")
            
            market_status = MarketStatusService.get_market_status()
            response_data["market_status"] = market_status
            
        except Exception as e:
            print(f"V5 Engine Integration error: {e}")
            import traceback
            traceback.print_exc()

        # 7. Additional Data
        fundamentals = await asyncio.to_thread(FundamentalService.get_fundamentals, norm_symbol)
        response_data["fundamentals"] = fundamentals
        response_data["source"] = source

        return _json_serializable(response_data)
    except Exception as e:
        import traceback
        print(f"CRITICAL API ERROR in get_dashboard: {e}")
        traceback.print_exc()
        return _json_serializable({
            "status": "error",
            "message": f"Server Error: {str(e)}",
            "traceback": traceback.format_exc()
        })



# --- Fyers Authentication Endpoints ---

@app.get("/api/v1/fyers/login", dependencies=[Depends(login_required)])
async def fyers_login(request: Request):
    """Redirects the user to Fyers login page."""
    try:
        url = FyersService.get_login_url(_resolve_fyers_redirect_url(request))
        return RedirectResponse(url)
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate login URL: {str(e)}"}

@app.get("/api/v1/fyers/callback")
async def fyers_callback(
    request: Request,
    auth_code: Optional[str] = None,
    code: Optional[str] = None,
    state: Optional[str] = None,
):
    """Handles the callback from Fyers and generates access token."""
    try:
        resolved_auth_code = auth_code

        if not resolved_auth_code:
            alt_code = request.query_params.get("authCode") or request.query_params.get("authorization_code")
            if alt_code:
                resolved_auth_code = alt_code

        if not resolved_auth_code and code and not str(code).isdigit():
            resolved_auth_code = code

        def _auth_response_js(status_val, msg=None):
            # Returns a small script that communicates with the opener and closes the popup
            js_msg = msg.replace('"', '\\"') if msg else ""
            return f"""
            <html>
                <body style="background: #0b0e11; color: #d1d4dc; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                    <div style="text-align: center;">
                        <h2 style="color: {'#22c55e' if status_val == 'success' else '#ef4444'}">
                            {'Authentication Successful' if status_val == 'success' else 'Authentication Failed'}
                        </h2>
                        <p style="font-size: 14px; opacity: 0.8;">{msg or 'Redirecting back to dashboard...'}</p>
                        <script>
                            if (window.opener) {{
                                window.opener.postMessage({{ 
                                    type: 'fyers_auth', 
                                    status: '{status_val}', 
                                    message: '{js_msg}' 
                                }}, '*');
                                setTimeout(() => window.close(), 1000);
                            }} else {{
                                window.location.href = "/?fyers_login={status_val}";
                            }}
                        </script>
                    </div>
                </body>
            </html>
            """

        if not resolved_auth_code:
            query_keys = ", ".join(sorted(request.query_params.keys())) or "none"
            return HTMLResponse(content=_auth_response_js("error", f"Missing auth_code (keys: {query_keys})"))

        success, message = FyersService.generate_token(
            resolved_auth_code,
            redirect_uri=_resolve_fyers_redirect_url(request),
        )
        
        if success:
            return HTMLResponse(content=_auth_response_js("success"))
        return HTMLResponse(content=_auth_response_js("error", message))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=_auth_response_js("error", str(e)))

@app.get("/api/v1/fyers/status", dependencies=[Depends(login_required)])
async def fyers_status(request: Request):
    """Checks if Fyers is logged in and provides diagnostic info."""
    is_logged_in = FyersService.load_token()
    effective_redirect_url = _resolve_fyers_redirect_url(request)
    auth_url = FyersService.get_login_url(effective_redirect_url)
    
    return {
        "status": "success",
        "data": {
            "is_connected": is_logged_in,
            "logged_in": is_logged_in,
            "status": "online" if is_logged_in else "offline",
            "app_id": fyers_config.app_id[:5] + "..." if fyers_config.app_id else None,
            "app_id_source": "env" if os.getenv("FYERS_APP_ID") else "default",
            "redirect_url": effective_redirect_url,
            "redirect_url_source": "env" if os.getenv("FYERS_REDIRECT_URL") else "derived",
            "auth_url": auth_url,
            "callback_path": "/api/v1/fyers/callback",
            "config_ready": bool(fyers_config.app_id and fyers_config.secret_id),
            "fyers_token_file_from_env": bool(os.getenv("FYERS_TOKEN_FILE")),
            "fyers_token_file_name": os.path.basename(fyers_config.token_file),
            "last_auth_debug": FyersService.get_last_auth_debug()
        }
    }


@app.get("/api/v1/fyers/debug-auth", dependencies=[Depends(login_required)])
async def fyers_debug_auth(request: Request):
    """Diagnostic endpoint to identify exactly which payload field causes auth failure."""
    import hashlib
    results = []
    full_app_id = fyers_config.app_id
    secret_id = fyers_config.secret_id
    redirect_uri = _resolve_fyers_redirect_url(request)
    
    hash_input = f"{full_app_id}:{secret_id}"
    app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    
    url = "https://api.fyers.in/api/v3/validate-authcode"
    browser_headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    # Test different payload variations to identify which field is wrong
    payload_variants = [
        # Standard with all fields
        {"label": "full-json",   "ct": "application/json",                  "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "redirect_uri": redirect_uri, "appId": full_app_id}},
        # Without redirect_uri
        {"label": "no-redirect", "ct": "application/json",                  "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "appId": full_app_id}},
        # Without appId
        {"label": "no-appid",    "ct": "application/json",                  "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "redirect_uri": redirect_uri}},
        # Form-encoded with all fields
        {"label": "form-full",   "ct": "application/x-www-form-urlencoded", "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "redirect_uri": redirect_uri, "appId": full_app_id}},
        # Form-encoded without redirect_uri
        {"label": "form-no-redir","ct": "application/x-www-form-urlencoded","payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "appId": full_app_id}},
        # Minimal (just hash + code)
        {"label": "minimal",     "ct": "application/json",                  "payload": {"appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE"}},
        # api-t1 benchmark
        {"label": "api-t1-json", "ct": "application/json",                  "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE"}, "url": "https://api-t1.fyers.in/api/v3/validate-authcode"},
    ]
    
    # Add proxy tests if configured
    if fyers_config.auth_proxy_url:
        payload_variants.insert(0, {
            "label": "proxy-test", 
            "ct": "application/x-www-form-urlencoded", 
            "payload": {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": "DIAGNOSTIC_CODE", "appId": full_app_id},
            "url": fyers_config.auth_proxy_url
        })

    
    for variant in payload_variants:
        target_url = variant.get("url", url)
        ct = variant["ct"]
        payload = variant["payload"]
        hdrs = {**browser_headers, "Content-Type": ct}
        try:
            if ct == "application/json":
                res = requests.post(target_url, json=payload, headers=hdrs, timeout=10)
            else:
                res = requests.post(target_url, data=payload, headers=hdrs, timeout=10)
            results.append({
                "label": variant["label"],
                "status": res.status_code,
                "body": res.text[:200]
            })
        except Exception as e:
            results.append({"label": variant["label"], "error": str(e)})
    
    return {"results": results, "config": {"app_id": full_app_id[:8] + "...", "redirect_uri": redirect_uri}}



@app.get("/api/v1/screener", dependencies=[Depends(login_required)])
async def run_screener(force: bool = False):
    # Comprehensive watchlist - 200+ stocks to match Screener.in coverage
    watchlist = [
        # Nifty 50
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "SBIN", "LICI", "ITC", "HUL",
        "WIPRO", "AXISBANK", "KOTAKBANK", "LT", "ASIANPAINT", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO",
        "BAJFINANCE", "ONGC", "JSWSTEEL", "ADANIENT", "COALINDIA", "TATASTEEL", "TATAMOTORS", "POWERGRID",
        "NTPC", "HINDALCO", "INDUSINDBK", "TECHM", "HCLTECH", "NESTLEIND", "DRREDDY", "CIPLA", "BAJAJFINSV",
        "HEROMOTOCO", "EICHERMOT", "BRITANNIA", "APOLLOHOSP", "DIVISLAB", "ADANIPORTS", "GRASIM", "SHRIRAMFIN",
        "TATACONSUM", "SBILIFE", "HDFCLIFE", "LTIM", "BAJAJ-AUTO",
        
        # Nifty Next 50 & Mid Cap Leaders
        "ADANIPOWER", "ADANIGREEN", "SIEMENS", "HAVELLS", "GODREJCP", "BOSCHLTD", "PIDILITIND", "BERGEPAINT",
        "COLPAL", "MARICO", "DABUR", "MUTHOOTFIN", "CHOLAFIN", "CHOLAHLDNG", "TRENT", "DMART", "ZOMATO",
        "PAYTM", "NYKAA", "POLICYBZR", "IRCTC", "DIXON", "POLYCAB", "KEI", "AUROPHARMA", "LUPIN", "BIOCON",
        "TORNTPHARM", "ALKEM", "PERSISTENT", "COFORGE", "LTTS", "MPHASIS", "MINDTREE", "OFSS", "KPITTECH",
        "TATAELXSI", "SONATSOFTW", "HAPPSTMNDS", "NEWGEN", "ROUTE", "CLEAN",
        
        # Defence & Aerospace
        "HAL", "BEL", "GRSE", "MAZDOCK", "BEML", "BHEL", "COCHINSHIP", "GARFIBRES", "SOLARA", "MIDHANI",
        
        # Rail & Infrastructure  
        "RVNL", "IRFC", "IRCON", "RAILTEL", "RITES", "CONCOR", "NBCC", "NCC", "KNR", "PNC", "GMBREW",
        
        # Power & Energy
        "IREDA", "RECLTD", "PFC", "HUDCO", "NHPC", "SJVN", "TATAPOWER", "ADANIGREEN", "TORNTPOWER", "CESC",
        
        # PSU Banks
        "SBIN", "PNB", "CANBK", "BANKBARODA", "UNIONBANK", "INDIANB", "MAHABANK", "CENTRALBK", "IOB", "BANKINDIA",
        
        # Private Banks & NBFCs
        "HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK", "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK",
        "BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM", "IIFL", "LICHSGFIN",
        
        # Auto & Components
        "MARUTI", "TATAMOTORS", "MAHINDRA", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "MOTHERSON", "BOSCHLTD",
        "BALKRISIND", "APOLLOTYRE", "MRF", "CEAT", "EXIDEIND", "AMARON", "SCHAEFFLER", "ENDURANCE",
        
        # IT & Tech
        "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTIM", "LTTS", "PERSISTENT", "COFORGE", "MPHASIS",
        "MINDTREE", "OFSS", "KPITTECH", "TATAELXSI", "SONATSOFTW", "HAPPSTMNDS", "NEWGEN", "ROUTE",
        
        # Pharma & Healthcare
        "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA", "LUPIN", "BIOCON", "TORNTPHARM", "ALKEM",
        "LALPATHLAB", "METROPOLIS", "APOLLOHOSP", "MAXHEALTH", "FORTIS", "NARAYANA",
        
        # Chemicals & Materials
        "UPL", "PIDILITIND", "AARTI", "DEEPAKNTR", "SRF", "ALKYLAMINE", "CLEAN", "FINEORG", "NAVINFLUOR",
        
        # Consumer & Retail
        "HUL", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "MARICO", "GODREJCP", "COLPAL", "TATACONSUM",
        "TRENT", "DMART", "SHOPERSTOP", "TITAN", "TANISHQ",
        
        # Emerging Growth (Screener.in specific matches)
        "INDOTHAI", "IGIL", "BORANA", "ALUFLUORIDE", "EMERALD", "KAYNES", "SYRMA", "DATAPATTNS", "ERIS",
        "FINEORG", "CLEAN", "ROUTE", "HAPPSTMNDS", "NEWGEN", "SONATSOFTW", "AMBER", "NETWORK18"
    ]
    matches = FundamentalScreener.screen_symbols(watchlist, force=force)
    return {"status": "success", "count": len(matches), "matches": matches}

@app.get("/api/v1/sector-rotation", dependencies=[Depends(login_required)])
async def get_sector_rotation(tf: str = "1D"):
    """
    Returns RS and RM data for all NSE sectors for the rotation dashboard.
    """
    try:
        from app.services.sector_service import SectorService
        data, alerts = SectorService.get_rotation_data(days=60, timeframe=tf)
        
        # Determine source
        source = "live"
        
        # SectorService uses a specific flag for hardcoded fallback, check its structure
        # Or check if data was loaded from disk fallback
        if not data:
            source = "error"
        elif any(s.get("status") == "fallback" for s in data.values()):
            source = "fallback"

        return {
            "status": "success",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
            "alerts": alerts,
            "source": source
        }
    except Exception as e:
        print(f"Error in get_sector_rotation: {e}")
        try:
            from app.services.sector_service import SectorService
            fb_data, fb_alerts = SectorService._load_fallback("1D" if tf == "Daily" else tf)
            return {
                "status": "success", 
                "data": fb_data, 
                "alerts": fb_alerts, 
                "source": "fallback",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except:
            pass
        return {"status": "error", "message": str(e), "source": "error"}

@app.get("/api/v1/health/intelligence", dependencies=[Depends(login_required)])
async def get_intelligence_health():
    """
    HEALTH MONITORING ENDPOINT
    Returns real-time engine telemetry, WebSocket streaming metrics, and market status.
    """
    from app.services.screener_service import ScreenerService
    health = ScreenerService.get_health_metrics()

    # Merge in WebSocket streaming metrics
    ws_metrics = FyersSocketService.get_metrics()
    health["websocket"] = {
        "connected": ws_metrics.get("connected", False),
        "reconnect_count": ws_metrics.get("reconnect_count", 0),
        "total_ticks": ws_metrics.get("total_ticks", 0),
        "total_batches": ws_metrics.get("total_batches", 0),
        "last_error": ws_metrics.get("last_error"),
    }

    # Merge in market session status
    health["market_status"] = MarketCalendar.get_market_status()

    return _json_serializable(health)

@app.get("/api/v1/intelligence", dependencies=[Depends(login_required)])
async def get_intelligence():
    """
    PRECOMPUTED INTELLIGENCE ENDPOINT (Target: <100ms)
    Returns the latest signals from the background engine.
    """
    from app.services.screener_service import ScreenerService
    status = ScreenerService.get_intelligence_status()
    
    # Return warming state if no data yet
    if status["status"] == "warming":
        return JSONResponse(status_code=202, content={"status": "warming", "message": "Intelligence engine is calculating initial signals..."})
    
    return _json_serializable({
        "status": "success",
        "last_updated": status["last_updated"],
        "count": len(status["data"]),
        "data": status["data"]
    })

@app.get("/api/v1/momentum-hits", dependencies=[Depends(login_required)])
async def get_momentum_hits(tf: str = "1D", force: bool = False):
    """
    INSTANT MOMENTUM HITS (REFACTORED)
    Now serves from precomputed background cache.
    """
    try:
        from app.services.screener_service import ScreenerService
        from app.services.signal_filter_service import SignalFilterService
        from app.services.trade_decision_service import TradeDecisionService
        
        # 1. Fetch from Background Cache (Instant)
        status = ScreenerService.get_intelligence_status()
        
        if status["status"] == "warming" and not status["data"]:
            return JSONResponse(status_code=202, content={"status": "warming", "message": "Warming up..."})
            
        raw_hits = status["data"]
        
        # 2. Add filters and decisions (Lightweight/No OHLCV fetch)
        # Note: All heavy Pandas work with OHLCV happened in the background
        filtered = SignalFilterService.annotate_many(raw_hits)
        
        from app.services.market_status_service import MarketStatusService
        market_status = MarketStatusService.get_market_status()
        enriched = TradeDecisionService.annotate_many(filtered, market_phase=market_status["market_phase"])
        
        return _json_serializable({
            "status": "success",
            "count": len(enriched),
            "data": enriched,
            "source": "background_engine",
            "timestamp": status["last_updated"]
        })
    except Exception as e:
        print(f"ERROR in get_momentum_hits: {e}")
        # Try emergency fallback load in the outer catch too
        try:
             from app.services.screener_service import ScreenerService as MomentumScreener
             fallback = MomentumScreener._load_fallback("1D" if tf == "Daily" else tf)
             if fallback:
                 return {
                     "status": "success", 
                     "count": len(fallback), 
                     "data": fallback, 
                     "source": "fallback",
                     "is_fyers_active": False
                 }
        except:
             pass

        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": str(e),
            "source": "error"
        }

@app.get("/api/v1/early-setups", dependencies=[Depends(login_required)])
async def get_early_setups(tf: str = "1D", limit: int = 5):
    """
    Returns early accumulation candidates before breakout.
    Additive intelligence layer (does not modify existing screener signals).
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
        data = MomentumScreener.get_early_breakout_setups(timeframe=tf, limit=limit)
        
        source = "live"
        if not data:
            # Check if this might be a rate limit case but let it be live for now
            pass

        return {
            "status": "success",
            "count": len(data),
            "data": data,
            "source": source
        }
    except Exception as e:
        print(f"Error in get_early_setups: {e}")
        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": str(e),
            "source": "error"
        }

@app.get("/api/v1/next-session-watchlist", dependencies=[Depends(login_required)])
async def get_next_session_watchlist(tf: str = "1D"):
    """
    Returns the Next Session Watchlist: key breakout setups, strong and weak sectors.
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
        data = MomentumScreener.get_next_session_watchlist(timeframe=tf)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/trade-performance", dependencies=[Depends(login_required)])
async def get_trade_performance():
    """
    Returns execution-layer trade tracking and PnL performance metrics.
    """
    try:
        from app.services.trade_tracking_service import TradeTrackingService
        return {"status": "success", "data": TradeTrackingService.get_performance()}
    except Exception as e:
        return {"status": "error", "data": {}, "message": str(e)}

@app.post("/api/v1/log-trade", dependencies=[Depends(login_required)])
async def log_trade(request: Request):
    """
    Manually logs a trade into the system.
    """
    try:
        data = await request.json()
        from app.services.trade_tracking_service import TradeTrackingService
        TradeTrackingService.log_manual_trade(data)
        return {"status": "success", "message": "Trade logged successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/signal-performance", dependencies=[Depends(login_required)])
async def get_signal_performance(tf: str = "1D"):
    """
    Returns daily signal performance metrics and conversions.
    Analytics-only endpoint; does not alter scoring or signal generation.
    """
    try:
        from app.services.signal_performance_service import SignalPerformanceService
        perf = SignalPerformanceService.compute(timeframe=tf)
        return {"status": "success", "data": perf.to_dict()}
    except Exception as e:
        from app.services.observability_service import ObservabilityService
        ObservabilityService.record_api_failure("/api/v1/signal-performance", str(e), {"tf": tf})
        return {"status": "error", "data": {}, "message": str(e)}


@app.get("/api/v1/observability-summary", dependencies=[Depends(login_required)])
async def get_observability_summary():
    """
    Returns a lightweight 24h summary of API failures and fail-safe events.
    """
    try:
        from app.services.observability_service import ObservabilityService
        return {"status": "success", "data": ObservabilityService.summarize_last_24h()}
    except Exception as e:
        return {"status": "error", "data": {}, "message": str(e)}
@app.get("/api/v1/screener/debug", dependencies=[Depends(login_required)])
async def get_screener_debug():
    """Returns the internal rejection logs for the last screener run."""
    try:
        from app.services.fundamental_screener_service import FundamentalScreener
        rejection_logs = FundamentalScreener.get_rejection_logs()
        return {"status": "success", "data": rejection_logs}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/screener/force-refresh", dependencies=[Depends(login_required)])
async def force_screener_refresh():
    """Triggers a fresh scan of all symbols, bypassing the cache."""
    try:
        from app.services.fundamental_screener_service import FundamentalScreener
        from app.services.constituent_service import ConstituentService
        symbols = ConstituentService.get_nifty100_symbols()
        results = FundamentalScreener.screen_symbols(symbols, force=True)
        return {"status": "success", "count": len(results), "matches": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/market-summary", dependencies=[Depends(login_required)])
async def get_market_summary(tf: str = "1D"):
    """
    Returns an aggregated AI market summary.
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
        from app.services.fundamental_screener_service import FundamentalScreener
        from app.services.constituent_service import ConstituentService
        
        # 1. Fundamental Screener (Proxy-Aware)
        symbols = ConstituentService.get_nifty100_symbols()
        funda_matches = FundamentalScreener.screen_symbols(symbols)
        
        # 2. Momentum Screener
        data = MomentumScreener.get_market_summary_data(timeframe=tf)
        
        source = "live"
        if not data:
            source = "error"

        session_tag, session_quality = MomentumScreener.get_session_tag()

        return {
            "status": "success",
            "data": data,
            "source": source,
            "market_open": session_tag != "CLOSED"
        }
    except Exception as e:
        print(f"Error in get_market_summary: {e}")
        return {
            "status": "error",
            "message": str(e),
            "source": "error"
        }

# @app.post("/api/v1/login")
# async def login(request: Request, response: Response):
#     try:
#         data = await request.json()
#         username = data.get("username")
#         password = data.get("password")
#         remember = data.get("remember", False)
#
#         if username == ADMIN_USER and password == ADMIN_PASS:
#             max_age = 2592000 if remember else 86400 # 30 days if remember, else 1 day
#             response.set_cookie(
#                 key=AUTH_COOKIE_NAME,
#                 value="authenticated_admin",
#                 httponly=True,
#                 max_age=max_age,
#                 samesite="lax",
#                 secure=False
#             )
#             return {"status": "success", "message": "Authenticated"}
#         else:
#             return JSONResponse(
#                 status_code=401,
#                 content={"status": "error", "message": "Invalid credentials"}
#             )
#     except Exception as e:
#         return JSONResponse(
#             status_code=500,
#             content={"status": "error", "message": str(e)}
#         )

# @app.post("/api/v1/logout")
# async def logout(response: Response):
#     response.delete_cookie(key=AUTH_COOKIE_NAME)
#     return {"status": "success", "message": "Logged out"}

# @app.get("/login")
# async def get_login_page():
#     login_path = curr_dir / "login.html"
#     if login_path.exists():
#         return FileResponse(str(login_path))
#     return {"status": "error", "message": "Login page not found"}

@app.get("/")
async def get_index_page(user: Optional[str] = Depends(get_current_user)):
    # Removed redirection to login
    # if not user:
    #     return RedirectResponse(url="/login")
    
    index_path = curr_dir / "frontend" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"status": "error", "message": "Dashboard not found"}

@app.get("/api/v1/internal/audit")
async def get_audit_logs():
    """Hidden audit log that displays the trailing stdout logs."""
    return {"status": "success", "logs": list(audit_tail.logs)}

@app.get("/api/v1/generate-trade", dependencies=[Depends(login_required)])
async def generate_trade_api(symbol: str = "TCS", tf: str = "15m", strategy: str = "SR"):
    """
    Production-grade Trade Decision Engine endpoint.
    Converts market data into actionable 'BUY ABOVE / SELL BELOW' signals.
    """
    try:
        # 1. Fetch Primary Data
        norm_symbol = MarketDataService.normalize_symbol(symbol)
        df, currency, error, source = await asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, tf)
        
        if df is None or df.empty:
            raise HTTPException(status_code=400, detail=error or f"No data found for {symbol}")

        # 2. Extract Key Metrics
        from app.engine.insights import InsightEngine
        from app.engine.zones import ZoneEngine
        from app.engine.regime import MarketRegimeEngine
        
        cmp = float(df['close'].iloc[-1])
        supports, resistances = await asyncio.to_thread(SREngine.calculate_sr_levels, df)
        
        # Mapping SR results to simple list of prices
        support_prices = [s['price'] for s in supports]
        resistance_prices = [r['price'] for r in resistances]
        
        atr_series = await asyncio.to_thread(ZoneEngine.calculate_atr, df)
        atr = float(atr_series.iloc[-1]) if not atr_series.empty else cmp * 0.01
        
        adx = await asyncio.to_thread(InsightEngine.get_adx, df)
        regime = await asyncio.to_thread(MarketRegimeEngine.detect_regime, df)
        
        # Map regime to simple trend
        trend = "SIDEWAYS"
        if "UPTREND" in regime: trend = "BULLISH"
        elif "DOWNTREND" in regime: trend = "BEARISH"
        
        # 3. Create Market Context
        vol_ratio = await asyncio.to_thread(InsightEngine.get_volume_ratio, df)
        
        # ScanX Style: Daily Volume Comparison
        df_daily, _, _, _ = await asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, "1D")
        daily_vol_ratio = await asyncio.to_thread(InsightEngine.get_daily_volume_ratio, df_daily, df)
        
        context = MarketContext(
            symbol=symbol,
            price=cmp,
            open=float(df['open'].iloc[-1]),
            high=float(df['high'].iloc[-1]),
            low=float(df['low'].iloc[-1]),
            close=float(df['close'].iloc[-1]),
            prev_close=float(df['close'].iloc[-2]) if len(df) > 1 else cmp,
            supports=support_prices,
            resistances=resistance_prices,
            atr=atr,
            adx=adx,
            volume_ratio=vol_ratio,
            daily_volume_ratio=daily_vol_ratio,
            trend=trend,
            higher_tf_trend="NEUTRAL" # Can be updated with 1D/4H analysis if needed
        )
        
        # 4. Generate Decision
        decision = V5TradeEngine.generate_trade(context, timeframe=tf)
        
        # 5. Format Output
        formatted_text = TradeBuilder.format_output(decision)
        
        import json
        if hasattr(decision, "model_dump_json"):
            decision_json = json.loads(decision.model_dump_json())
        else:
            decision_json = json.loads(decision.json())

        return {
            "status": "success",
            "symbol": symbol,
            "volume_ratio": daily_vol_ratio,
            "intraday_volume_ratio": vol_ratio,
            "decision": decision_json,
            "recommendation": formatted_text
        }
        
    except Exception as e:
        print(f"Error in generate_trade_api: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

# ==============================================================================
# 9. REALTIME WEBSOCKET & QUANT API INFRASTRUCTURE
# ==============================================================================
from fastapi import WebSocket, WebSocketDisconnect
from app.engine.signal_engine import SignalEngine
from app.services.database_service import DatabaseService
from app.services.screener_service import ScreenerService

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "ticks": [],
            "signals": [],
            "alerts": [],
            "scanner": []
        }

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        if channel in self.active_connections:
            self.active_connections[channel].append(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.active_connections:
            if websocket in self.active_connections[channel]:
                self.active_connections[channel].remove(websocket)

    async def broadcast(self, channel: str, message: Any):
        if channel not in self.active_connections:
            return
        
        if not isinstance(message, str):
            try:
                import json
                message = json.dumps(_json_serializable(message))
            except Exception as e:
                print(f"[WS Broadcaster] JSON serialization failed: {e}", flush=True)
                return
                
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
                
        for conn in disconnected:
            self.disconnect(conn, channel)

ws_manager = ConnectionManager()

# WebSocket Endpoints
@app.websocket("/ws/ticks")
async def websocket_ticks(websocket: WebSocket):
    await ws_manager.connect(websocket, "ticks")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "ticks")

@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    await ws_manager.connect(websocket, "signals")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "signals")

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await ws_manager.connect(websocket, "alerts")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "alerts")

@app.websocket("/ws/scanner")
async def websocket_scanner(websocket: WebSocket):
    await ws_manager.connect(websocket, "scanner")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, "scanner")


# Real-time Telemetry & Alerts Hook
_last_signal_calc: Dict[str, float] = {}

async def evaluate_realtime_signal_and_alerts(symbol: str, price: float, volume: float):
    try:
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").split(":")[-1].split("-")[0]
        sig_data = await asyncio.to_thread(SignalEngine.generate_signal, clean_sym)
        
        # Broadcast signal update
        await ws_manager.broadcast("signals", {
            "symbol": clean_sym,
            "signal": sig_data.get("signal"),
            "confidence": sig_data.get("confidence"),
            "strength": sig_data.get("strength"),
            "narrative": sig_data.get("narrative"),
            "timestamp": datetime.now().isoformat()
        })
        
        details = sig_data.get("details", {})
        
        # 1. Gann Breakout Alert
        gann_bo = details.get("gann_breakout", {})
        if gann_bo and gann_bo.get("status") in ["BREAKOUT_G1", "BREAKOUT_G2", "BREAKOUT_G3", "BREAKDOWN_G1", "BREAKDOWN_G2", "BREAKDOWN_G3"]:
            alert_type = "GANN_BREAKOUT"
            message = f"Gann level breakout detected on {clean_sym}: price is at {price}, breaking {gann_bo.get('status').lower()} through level {gann_bo.get('level')}"
            DatabaseService.log_alert(clean_sym, alert_type, price, message)
            await ws_manager.broadcast("alerts", {
                "symbol": clean_sym,
                "alert_type": alert_type,
                "price": price,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
            
        # 2. VWAP Crossover Alert
        vwap_ev = details.get("vwap", {})
        if vwap_ev and vwap_ev.get("crossover") in ["BULLISH_CROSSOVER", "BEARISH_CROSSOVER"]:
            alert_type = "VWAP_CROSSOVER"
            message = f"VWAP crossover detected on {clean_sym}: price is at {price}, crossover is {vwap_ev.get('crossover').lower()}"
            DatabaseService.log_alert(clean_sym, alert_type, price, message)
            await ws_manager.broadcast("alerts", {
                "symbol": clean_sym,
                "alert_type": alert_type,
                "price": price,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
            
        # 3. Volume Spike Alert
        vol_m = details.get("volume", {})
        if vol_m and vol_m.get("is_spike"):
            alert_type = "VOLUME_SPIKE"
            message = f"Volume spike detected on {clean_sym}: price is at {price}, relative volume is {vol_m.get('rvol')}x"
            DatabaseService.log_alert(clean_sym, alert_type, price, message)
            await ws_manager.broadcast("alerts", {
                "symbol": clean_sym,
                "alert_type": alert_type,
                "price": price,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
            
        # 4. Smart Money Alert
        sm = details.get("smart_money", {})
        if sm and sm.get("state") in ["BULLISH_MANIPULATION", "BEARISH_MANIPULATION", "ACCUMULATION", "DISTRIBUTION", "ABSORPTION", "BREAKOUT_LOADING"]:
            alert_type = "SMART_MONEY"
            message = f"Smart Money pattern '{sm.get('state')}' detected on {clean_sym}: {sm.get('narrative')}"
            DatabaseService.log_alert(clean_sym, alert_type, price, message)
            await ws_manager.broadcast("alerts", {
                "symbol": clean_sym,
                "alert_type": alert_type,
                "price": price,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
            
    except Exception as e:
        print(f"[WS Broadcaster] Error in realtime evaluation: {e}", flush=True)

# Wrap ScreenerService to broadcast live ticks and trigger evaluations
_orig_update_realtime = ScreenerService.update_symbol_realtime

@classmethod
async def wrapped_update_realtime(cls, symbol, price, volume):
    res = await _orig_update_realtime(symbol, price, volume)
    
    clean_symbol = symbol.replace(".NS", "").replace(".BO", "").split(":")[-1].split("-")[0]
    
    # Broadcast live tick
    await ws_manager.broadcast("ticks", {
        "symbol": clean_symbol,
        "price": price,
        "volume": volume,
        "timestamp": datetime.now().isoformat()
    })
    
    # Throttled real-time evaluations (max once every 5 seconds per symbol)
    now_t = time.time()
    if now_t - _last_signal_calc.get(clean_symbol, 0) > 5.0:
        _last_signal_calc[clean_symbol] = now_t
        asyncio.create_task(evaluate_realtime_signal_and_alerts(symbol, price, volume))
        
    return res

ScreenerService.update_symbol_realtime = wrapped_update_realtime


# Background Screener & Scanner Worker
async def scanner_background_worker():
    print("[Background Screener] Background scanner worker started.", flush=True)
    # Give server a few seconds to warm up
    await asyncio.sleep(10)
    while True:
        try:
            watchlist = DatabaseService.get_watchlist()
            if not watchlist:
                watchlist = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"]
                
            print(f"[Background Screener] Running background scan for {len(watchlist)} watchlist symbols...", flush=True)
            
            scanner_results = []
            for symbol in watchlist:
                try:
                    sig_data = await asyncio.to_thread(SignalEngine.generate_signal, symbol, timeframe="15m")
                    scanner_results.append({
                        "symbol": symbol,
                        "signal": sig_data.get("signal"),
                        "confidence": sig_data.get("confidence"),
                        "strength": sig_data.get("strength"),
                        "rvol": sig_data.get("details", {}).get("volume", {}).get("rvol", 1.0),
                        "cpr_width": sig_data.get("details", {}).get("cpr", {}).get("width_status", "WIDE"),
                        "cpr_position": sig_data.get("details", {}).get("cpr_position", "INSIDE_CPR"),
                        "smart_money": sig_data.get("details", {}).get("smart_money", {}).get("state", "NEUTRAL"),
                        "timestamp": datetime.now().isoformat()
                    })
                except Exception as sym_err:
                    print(f"[Background Screener] Error scanning {symbol}: {sym_err}", flush=True)
                    
            await ws_manager.broadcast("scanner", {
                "scanner_updates": scanner_results,
                "timestamp": datetime.now().isoformat()
            })
            print(f"[Background Screener] Scan finished. Broadcasted updates for {len(scanner_results)} symbols.", flush=True)
        except Exception as worker_err:
            print(f"[Background Screener] Error in background worker: {worker_err}", flush=True)
        await asyncio.sleep(30)


# REST API ROUTING
@app.get("/api/stocks/search", dependencies=[Depends(login_required)])
async def stocks_search(q: str = Query(..., min_length=1)):
    res = await search_symbols(q)
    return {"status": "success", "data": res}

@app.get("/api/stocks/dashboard/{symbol}", dependencies=[Depends(login_required)])
async def stocks_dashboard(symbol: str, tf: str = "15m"):
    sig_data = await asyncio.to_thread(SignalEngine.generate_signal, symbol, tf)
    return _json_serializable({
        "status": "success",
        "data": sig_data
    })

@app.get("/api/stocks/signals", dependencies=[Depends(login_required)])
async def stocks_signals(symbol: Optional[str] = None):
    if symbol:
        sig_data = await asyncio.to_thread(SignalEngine.generate_signal, symbol)
        return {"status": "success", "data": [sig_data]}
    else:
        signals = DatabaseService.get_scanner_signals()
        return {"status": "success", "data": signals}

@app.get("/api/stocks/scanner", dependencies=[Depends(login_required)])
async def stocks_scanner(preset: str = Query("momentum_breakouts")):
    signals = DatabaseService.get_scanner_signals()
    filtered = []
    for s in signals:
        is_match = False
        if preset == "momentum_breakouts":
            is_match = s["signal"] in ["BUY", "SELL"] and s["confidence"] >= 55.0 and s["rvol"] >= 1.2
        elif preset == "cpr_breakouts":
            is_match = s["cpr_width"] == "NARROW" and s["cpr_position"] in ["ABOVE_CPR", "BELOW_CPR"]
        elif preset == "high_rvol":
            is_match = s["rvol"] >= 1.8
        elif preset == "smart_money":
            is_match = s["smart_money"] not in ["NEUTRAL", "NORMAL", ""]
        elif preset == "trend_continuation":
            is_match = s["signal"] in ["BUY", "SELL"] and s["confidence"] >= 65.0
        elif preset == "reversal_setups":
            is_match = s["smart_money"] in ["BULLISH_MANIPULATION", "BEARISH_MANIPULATION", "SPRING", "UPTHRUST"]
            
        if is_match:
            filtered.append(s)
    return {"status": "success", "preset": preset, "count": len(filtered), "data": filtered}

@app.get("/api/stocks/watchlist", dependencies=[Depends(login_required)])
async def get_watchlist_api():
    symbols = DatabaseService.get_watchlist()
    enriched = []
    for sym in symbols:
        try:
            conn = DatabaseService.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scanner_signals WHERE symbol = ?", (sym.upper(),))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                if DatabaseService._connection_type == "POSTGRES":
                    sig_data = {
                        "symbol": row[0], "signal": row[2], "confidence": row[3], "rvol": row[4], "smart_money": row[7]
                    }
                else:
                    sig_data = {
                        "symbol": row["symbol"], "signal": row["signal"], "confidence": row["confidence"],
                        "rvol": row["relative_volume"], "smart_money": row["smart_money_state"]
                    }
                
                enriched.append({
                    "symbol": sym,
                    "price": 0.0,
                    "signal": sig_data["signal"],
                    "confidence": sig_data["confidence"],
                    "rvol": sig_data["rvol"],
                    "smart_money": sig_data["smart_money"],
                    "status": "cached"
                })
            else:
                enriched.append({
                    "symbol": sym,
                    "price": 0.0,
                    "signal": "HOLD",
                    "confidence": 50.0,
                    "rvol": 1.0,
                    "smart_money": "NEUTRAL",
                    "status": "new"
                })
        except Exception as we:
            print(f"Error enriching watchlist symbol {sym}: {we}", flush=True)
            enriched.append({"symbol": sym, "signal": "HOLD", "confidence": 0, "rvol": 1.0, "status": "error"})
    return {"status": "success", "data": enriched}

@app.post("/api/stocks/watchlist", dependencies=[Depends(login_required)])
async def add_watchlist_api(request: Request):
    data = await request.json()
    symbol = data.get("symbol", "").upper().strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")
    res = DatabaseService.add_to_watchlist(symbol)
    return {"status": "success" if res else "error"}

@app.delete("/api/stocks/watchlist", dependencies=[Depends(login_required)])
async def remove_watchlist_api(symbol: str = Query(...)):
    res = DatabaseService.remove_from_watchlist(symbol)
    return {"status": "success" if res else "error"}

@app.get("/api/stocks/alerts", dependencies=[Depends(login_required)])
async def get_alerts_api(limit: int = 20):
    alerts = DatabaseService.get_recent_alerts(limit)
    return {"status": "success", "data": alerts}


@app.on_event("startup")
async def startup_event():
    # Auto-initialize database on startup
    try:
        from app.services.database_service import DatabaseService
        DatabaseService.initialize()
    except Exception as e:
        print(f"[Startup] Database initialization failed: {e}", flush=True)
        
    # Start background worker
    asyncio.create_task(scanner_background_worker())


# Mount Frontend - Robust Path Finding
try:
    frontend_path = curr_dir / "frontend"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
        print(f"Mounted frontend from: {frontend_path}")
    else:
        print(f"Frontend directory not found at {frontend_path}")

except Exception as e:
    print(f"Failed to mount frontend: {e}")


if __name__ == "__main__":
    env_port = os.getenv("PORT") or os.getenv("UVICORN_PORT")
    try:
        port = int(env_port) if env_port else 8000
    except ValueError:
        port = 8000

    print(f"Starting server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
