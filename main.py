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
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from app.services.market_data import MarketDataService
from app.services.fundamentals import FundamentalService
from app.services.screener import ScreenerService
from app.services.sector_service import SectorService
from app.services.constituent_service import ConstituentService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.insights import InsightEngine
from app.engine.confidence import ConfidenceEngine
from app.ai.engine import AIEngine

from app.services.fyers_service import FyersService
from app.config import fyers_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def _warmup():
        try:
            import time

            print("[Warmup] Pre-warming screener cache in background...")
            t0 = time.time()

            def _sync_warmup():
                symbols = ConstituentService.get_nifty100_symbols()
                ScreenerService.screen_symbols(symbols)

            await asyncio.to_thread(_sync_warmup)
            print(f"[Warmup] Done in {time.time() - t0:.1f}s")
        except Exception as e:
            print(f"[Warmup] Error: {e}")

    asyncio.create_task(_warmup())
    yield


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


def _resolve_summary_levels(cmp, supports, resistances, mtf_levels):
    primary_supports = [p for p in _to_price_list(supports) if p < cmp]
    primary_resistances = [p for p in _to_price_list(resistances) if p > cmp]

    mtf_supports = [p for p in _to_price_list((mtf_levels or {}).get("supports", [])) if p < cmp]
    mtf_resistances = [p for p in _to_price_list((mtf_levels or {}).get("resistances", [])) if p > cmp]

    nearest_support = max(primary_supports) if primary_supports else (max(mtf_supports) if mtf_supports else None)
    nearest_resistance = min(primary_resistances) if primary_resistances else (min(mtf_resistances) if mtf_resistances else None)
    return nearest_support, nearest_resistance


def _build_trade_signal(ema_bias, risk_reward):
    if ema_bias == "Bullish" and risk_reward is not None and risk_reward >= 1.5:
        return "BUY", "Bullish bias + favorable risk/reward"
    if ema_bias == "Caution":
        return "SELL", "Momentum is weak/cautionary"
    return "HOLD", "Wait for better structure or confirmation"


def _external_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")

    if forwarded_host:
        scheme = forwarded_proto or request.url.scheme or "http"
        return f"{scheme}://{forwarded_host}".rstrip("/")

    return str(request.base_url).rstrip("/")


def _resolve_fyers_redirect_url(request: Request) -> str:
    configured_redirect = os.getenv("FYERS_REDIRECT_URL")
    if configured_redirect:
        return configured_redirect
    return f"{_external_base_url(request)}/api/v1/fyers/callback"


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

@app.get("/api/v2/ai-insights")
async def get_ai_insights(symbol: str = "RELIANCE", tf: str = "1D", base_conf: Optional[int] = None):
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

@app.get("/api/v1/search")
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


@app.get("/api/v1/dashboard")
async def get_dashboard(response: Response, symbol: str = "RELIANCE", tf: str = "1D", strategy: str = "SR"):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    print(f"DEBUG: Dashboard Request - {symbol} @ {tf} | Strategy: {strategy}")
    try:
        # 0. Normalize Symbol
        norm_symbol = await asyncio.to_thread(MarketDataService.normalize_symbol, symbol)

        # 1. Parallelize ALL Data Fetching (Primary, MTF, Sector)
        higher_tfs = []
        if tf == "5m": higher_tfs = ["15m", "1H", "1D"]
        elif tf == "15m": higher_tfs = ["1H", "2H", "1D"]
        elif tf == "1H": higher_tfs = ["2H", "4H", "1D"]
        elif tf == "2H": higher_tfs = ["4H", "1D", "1W"]
        elif tf == "1D": higher_tfs = ["1W", "1M"]

        async def fetch_mtf_wrapper(htf_name):
            try:
                h_df, _, h_err = await asyncio.to_thread(
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
            df, currency, error = await asyncio.wait_for(primary_task, timeout=8.0)
            
            source = "live"
            if error and not df.empty:
                source = "fallback"
            elif df.empty:
                return {"status": "error", "message": error or f"No data found for {symbol}.", "source": "error"}
        except asyncio.TimeoutError:
            print("CRITICAL: Primary data fetch timed out!")
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

        # 5. AI Insights (Non-blocking or Short Timeout)
        try:
            ai_analysis = await asyncio.wait_for(asyncio.to_thread(ai_engine.get_insights, df), timeout=2.0)
        except:
            ai_analysis = {}
        if not ai_analysis: ai_analysis = {}

        # 5. Final Formatting - Filter out NaN candles that crash lightweight-charts
        ohlcv = []
        import math
        for i in range(len(df)):
            try:
                o, h, l, c = float(df['open'].iloc[i]), float(df['high'].iloc[i]), float(df['low'].iloc[i]), float(df['close'].iloc[i])
                if math.isnan(o) or math.isnan(h) or math.isnan(l) or math.isnan(c):
                    continue
                    
                ohlcv.append({
                    "time": int(df.index[i].timestamp()),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c
                })
            except: continue
            
        # Initialize response_data with meta and structured levels
        ns, nr = _resolve_summary_levels(cmp, supports, resistances, mtf_levels)
        
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
                "confidence": int(strategy_result.get("confidence", 50)),
                "nearest_support": ns,
                "nearest_resistance": nr,
                "stop_loss": strategy_result.get("stopLoss"),
                "target": strategy_result.get("target"),
                "risk_reward": strategy_result.get("riskReward"),
                "market_regime": strategy_result.get("additionalMetrics", {}).get("regime", "STABLE")
            }
        }

        # 6. Trade Decision Add-on
        from app.services.trade_decision_service import TradeDecisionService
        try:
            decision_data = TradeDecisionService.compute_trade_score(response_data)
            response_data.update(decision_data)
        except Exception as e:
            print(f"TradeDecisionService error: {e}")

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

@app.get("/api/v1/fyers/login")
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

        if not resolved_auth_code:
            query_keys = ", ".join(sorted(request.query_params.keys())) or "none"
            return RedirectResponse(
                url=_build_fyers_redirect(
                    request,
                    "error",
                    f"Missing auth_code in Fyers callback (received query keys: {query_keys}).",
                )
            )

        success, message = FyersService.generate_token(resolved_auth_code)
        if success:
            # Redirect back to the dashboard with a success message
            return RedirectResponse(url=_build_fyers_redirect(request, "success"))
        return RedirectResponse(url=_build_fyers_redirect(request, "error", message))
    except Exception as e:
        return RedirectResponse(url=_build_fyers_redirect(request, "error", str(e)))

@app.get("/api/v1/fyers/status")
async def fyers_status(request: Request):
    """Checks if Fyers is logged in."""
    is_logged_in = FyersService.load_token()
    from app.services.screener_service import ScreenerService as MomentumScreener
    session_tag, session_quality = MomentumScreener.get_session_tag()
    effective_redirect_url = _resolve_fyers_redirect_url(request)
    auth_url = FyersService.get_login_url(effective_redirect_url)
    app_id_source = "env" if os.getenv("FYERS_APP_ID") else "default"
    redirect_url_source = "env" if os.getenv("FYERS_REDIRECT_URL") else "derived"
    return {
        "logged_in": is_logged_in,
        "market_open": session_tag != "CLOSED",
        "app_id": fyers_config.app_id[:5] + "..." if fyers_config.app_id else None,
        "app_id_source": app_id_source,
        "redirect_url": effective_redirect_url,
        "redirect_url_source": redirect_url_source,
        "auth_url": auth_url,
        "callback_path": "/api/v1/fyers/callback",
        "config_ready": bool(fyers_config.app_id and fyers_config.secret_id and effective_redirect_url),
        "last_auth_debug": FyersService.get_last_auth_debug(),
    }

@app.get("/api/v1/screener")
async def run_screener():
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
    matches = ScreenerService.screen_symbols(watchlist)
    return {"status": "success", "count": len(matches), "matches": matches}

@app.get("/api/v1/sector-rotation")
async def get_sector_rotation(tf: str = "1D"):
    """
    Returns RS and RM data for all NSE sectors for the rotation dashboard.
    """
    try:
        from app.services.sector_service import SectorService
        data, alerts = SectorService.get_rotation_data(days=60, timeframe=tf)
        
        source = "live"
        if not data:
            source = "error"

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

@app.get("/api/v1/momentum-hits")
async def get_momentum_hits(tf: str = "1D"):
    """
    Returns stocks with momentum hits (price and volume acceleration).
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
        from app.services.signal_filter_service import SignalFilterService
        from app.services.trade_decision_service import TradeDecisionService
        from app.services.trade_tracking_service import TradeTrackingService

        data = MomentumScreener.get_screener_data(timeframe=tf)
        if not data:
             # Fallback if service returns empty list (e.g. rate limit caught but no file?)
             # ScreenerService.get_screener_data already tries to load fallback, 
             # but we can be extra sure here.
             pass
             
        filtered = SignalFilterService.annotate_many(data)
        enriched = TradeDecisionService.annotate_many(filtered)
        TradeTrackingService.log_trades(enriched)
        
        # Detect if this is fallback data (if all items are old)
        source = "live"
        if enriched and not any(h.get("isLatestSession", False) for h in enriched):
            source = "fallback"

        return {
            "status": "success",
            "count": len(enriched),
            "data": enriched,
            "source": source
        }
    except Exception as e:
        print(f"ERROR in get_momentum_hits: {e}")
        # Try emergency fallback load in the outer catch too
        try:
             from app.services.screener_service import ScreenerService as MomentumScreener
             fallback = MomentumScreener._load_fallback("1D" if tf == "Daily" else tf)
             if fallback:
                 return {"status": "success", "count": len(fallback), "data": fallback, "source": "fallback"}
        except:
             pass

        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": str(e),
            "source": "error"
        }

@app.get("/api/v1/early-setups")
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

@app.get("/api/v1/trade-performance")
async def get_trade_performance():
    """
    Returns execution-layer trade tracking and PnL performance metrics.
    Additive analytics endpoint; does not alter signal generation logic.
    """
    try:
        from app.services.trade_tracking_service import TradeTrackingService
        return {"status": "success", "data": TradeTrackingService.get_performance()}
    except Exception as e:
        from app.services.observability_service import ObservabilityService
        ObservabilityService.record_api_failure("/api/v1/trade-performance", str(e))
        return {"status": "error", "data": {}, "message": str(e)}

@app.get("/api/v1/signal-performance")
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


@app.get("/api/v1/observability-summary")
async def get_observability_summary():
    """
    Returns a lightweight 24h summary of API failures and fail-safe events.
    """
    try:
        from app.services.observability_service import ObservabilityService
        return {"status": "success", "data": ObservabilityService.summarize_last_24h()}
    except Exception as e:
        return {"status": "error", "data": {}, "message": str(e)}

@app.get("/api/v1/market-summary")
async def get_market_summary(tf: str = "1D"):
    """
    Returns an aggregated AI market summary.
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
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
