<<<<<<< codex/check-and-fix-local-code-for-git-push-qlsf0r
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
=======
import asyncio
>>>>>>> main
import pandas as pd
import requests
import uvicorn
import os
from datetime import datetime
<<<<<<< codex/check-and-fix-local-code-for-git-push-qlsf0r
=======
from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

# Add global asyncio just in case of scope issues
try:
    _test = asyncio.get_event_loop()
except:
    pass
>>>>>>> main

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

app = FastAPI(title="Support & Resistance Dashboard")
ai_engine = AIEngine()


def _json_serializable(obj):
    """Recursively convert numpy types and non-serializable objects to python types."""
    import numpy as np
    
    if isinstance(obj, dict):
        return {_json_serializable(k): _json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_json_serializable(v) for v in obj]
    elif isinstance(obj, np.ndarray):
        return [_json_serializable(v) for v in obj.tolist()]
    elif hasattr(obj, 'item') and callable(getattr(obj, 'item')):
        return obj.item()
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif str(type(obj)).find('numpy.bool') != -1:
        return bool(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
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


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v2/ai-insights")
async def get_ai_insights(symbol: str = "RELIANCE", tf: str = "1D", base_conf: int = None):
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
    Proxies search requests to Yahoo Finance to avoid CORS on frontend.
    """
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&quotesCount=10&newsCount=0"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers)
        data = r.json()
        
        results = []
        
        # Inject custom keywords
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
        for kw, desc in custom_keywords.items():
            # Match if query is in keyword or description
            if q.upper() in kw or q.lower() in desc.lower():
                results.append({
                    "symbol": kw,
                    "shortname": desc,
                    "exchange": "CUSTOM"
                })

        if 'quotes' in data:
            for item in data['quotes']:
                sym = item.get('symbol', '')
                name = item.get('shortname', item.get('longname', ''))
                
                # Enhance naming for clarity
                if sym == 'GC=F': name = "Global Gold Futures (COMEX)"
                elif sym == 'SI=F': name = "Global Silver Futures (COMEX)"
                elif sym == 'CL=F': name = "Global Crude Oil Futures (NYM)"
                
                results.append({
                    "symbol": sym,
                    "shortname": name,
                    "exchange": item.get('exchange', '')
                })
        return results
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

        # 1. Get Primary Data
        df, currency = await asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, tf)
        if df.empty:
            return {"status": "error", "message": f"No data found for {symbol}."}
            
        cmp = float(df['close'].iloc[-1])
        
        # 2. Get Sector Context
        async def get_sector_state():
            try:
                sec_name = await asyncio.to_thread(ConstituentService.get_sector_for_ticker, norm_symbol)
                sec_state = "NEUTRAL"
                if sec_name:
                    rotation_data, _ = await asyncio.to_thread(SectorService.get_rotation_data, timeframe=tf)
                    if rotation_data and sec_name in rotation_data:
                        sec_state = rotation_data[sec_name]['metrics']['state']
                return sec_name, sec_state
            except Exception as e:
                print(f"Sector error: {e}")
                return None, "NEUTRAL"

        sector_task = asyncio.create_task(get_sector_state())
        
        # 3. Primary Calculations
        # 3. Primary Calculations & Strategy Execution
        supports = []
        resistances = []
        strategy_result = {}
        rendered_levels = {"supports": [], "resistances": []}
        sector_name, sector_state = await sector_task

        if strategy == "SR":
            print("DEBUG: Executing SR Strategy")
            # 3a. SR Levels (Reaction)
            supports, resistances = await asyncio.to_thread(SREngine.calculate_sr_levels, df)
            strategy_result = await asyncio.to_thread(SREngine.runSRStrategy, df, sector_state, supports, resistances)
            rendered_levels = {"supports": supports, "resistances": resistances}

        elif strategy == "SWING":
            print("DEBUG: Executing SWING Strategy")
            # 3b. Swing Levels (Structure)
            supports, resistances = await asyncio.to_thread(SwingEngine.calculate_swing_levels, df)
            
            htf = "1D" if tf != "1D" else "1W"
            print(f"DEBUG: Fetching HTF Data for {htf}")
            hdf, _ = await asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, htf)
            if hdf.empty:
                print("DEBUG: HTF DF is empty, using current DF")
                hdf = df
            print("DEBUG: Getting Structure Bias")
            htf_trend = await asyncio.to_thread(InsightEngine.get_structure_bias, hdf)
            print("DEBUG: Running Swing Strategy Core")
            strategy_result = await asyncio.to_thread(SwingEngine.runSwingStrategy, df, sector_state, htf_trend, supports, resistances)
            rendered_levels = {"supports": supports, "resistances": resistances}

        elif strategy == "DEMAND_SUPPLY":
            print("DEBUG: Running DEMAND_SUPPLY Strategy")
            # 3c. Zones
            zones = await asyncio.to_thread(ZoneEngine.calculate_demand_supply_zones, df)
            strategy_result = await asyncio.to_thread(ZoneEngine.runDemandSupplyStrategy, df, sector_state, zones)
            
            # Format zones for frontend (as supports/resistances but with type='DEMAND'/'SUPPLY')
            # Rendered levels for Zones are the boundaries
            formatted_zones = []
            for z in zones:
                # Add to formatted list (rendering logic handled by frontend type check)
                formatted_zones.append(z)
            
            # For backward compatibility with some UI parts, split into S/R roughly
            s_zones = [z for z in zones if z['type'] == 'DEMAND' and z['price_high'] < cmp]
            r_zones = [z for z in zones if z['type'] == 'SUPPLY' and z['price_low'] > cmp]
            
            supports = sorted(s_zones, key=lambda x: x['price_high'], reverse=True)[:4]
            resistances = sorted(r_zones, key=lambda x: x['price_low'])[:4]
            
            rendered_levels = {"supports": supports, "resistances": resistances}

        if strategy_result is None: strategy_result = {}
        print(f"DEBUG: Strategy Result Bias: {strategy_result.get('bias')}")

        # 4. Parallelize MTF and AI
        higher_tfs = []
        if tf == "5m": higher_tfs = ["15m", "1H", "1D"]
        elif tf == "15m": higher_tfs = ["1H", "2H", "1D"]
        elif tf == "1H": higher_tfs = ["2H", "4H", "1D"]
        elif tf == "2H": higher_tfs = ["4H", "1D", "1W"]
        elif tf == "1D": higher_tfs = ["1W", "1M"]
        
        async def fetch_mtf_levels(htf_name):
            try:
                h_df, _ = await asyncio.to_thread(MarketDataService.get_ohlcv, norm_symbol, htf_name)
                if h_df.empty: return [], []
                
                hs, hr = [], []
                if strategy == "SR":
                    hs, hr = await asyncio.to_thread(SREngine.calculate_sr_levels, h_df)
                elif strategy == "SWING":
                    hs, hr = await asyncio.to_thread(SwingEngine.calculate_swing_levels, h_df)
                elif strategy == "DEMAND_SUPPLY":
                    h_zones = await asyncio.to_thread(ZoneEngine.calculate_demand_supply_zones, h_df)
                    hs = [z for z in h_zones if z['type'] == 'DEMAND']
                    hr = [z for z in h_zones if z['type'] == 'SUPPLY']
                else:
                    hs, hr = await asyncio.to_thread(SREngine.calculate_sr_levels, h_df)

                # Tag HTF logic
                for h in hs: h['timeframe'] = htf_name
                for h in hr: h['timeframe'] = htf_name
                return hs, hr
            except Exception as e:
                print(f"DEBUG: MTF error for {htf_name}: {e}")
                return [], []

        mtf_task = asyncio.gather(*(fetch_mtf_levels(h) for h in higher_tfs))
        insights_task = asyncio.to_thread(ai_engine.get_insights, df)
        
        # Await them individually to be safer
        mtf_results = await mtf_task
        ai_analysis = await insights_task
        if not ai_analysis: ai_analysis = {}
        
        mtf_levels = {"supports": [], "resistances": []}
        if mtf_results:
            for pair in mtf_results:
                if pair:
                    hs, hr = pair
                    mtf_levels["supports"].extend(hs)
                    mtf_levels["resistances"].extend(hr)

        # 5. Final Formatting
        ohlcv = []
        for i in range(len(df)):
            try:
                ohlcv.append({
                    "time": int(df.index[i].timestamp()),
                    "open": float(df['open'].iloc[i]),
                    "high": float(df['high'].iloc[i]),
                    "low": float(df['low'].iloc[i]),
                    "close": float(df['close'].iloc[i])
                })
            except: continue

        # 6. Additional Data
        fundamentals = await asyncio.to_thread(FundamentalService.get_fundamentals, norm_symbol)
        
        insights = {
            "inside_candle": bool(InsightEngine.is_inside_candle(df)),
            "retest": bool(InsightEngine.detect_retest(df, supports + resistances)),
            "ema_bias": InsightEngine.get_ema_bias(df),
            "hammer": bool(InsightEngine.detect_hammer(df)),
            "engulfing": InsightEngine.detect_engulfing(df),
            "upside_pct": float(round(((resistances[0]['price'] - cmp) / cmp * 100), 2)) if resistances else 0.0,
            "adx": round(InsightEngine.get_adx(df), 2),
            "structure": InsightEngine.get_structure_bias(df)
        }

        response_data = {
            "status": "success",
            "meta": {
                "symbol": norm_symbol,
                "tf": tf,
                "strategy": strategy,
                "cmp": float(round(cmp, 2)),
                "currency": currency,
                "last_update": datetime.now().strftime("%H:%M:%S")
            },
            "summary": {
                "nearest_support": float(round(supports[0]['price'], 2)) if supports else None,
                "nearest_resistance": float(round(resistances[0]['price'], 2)) if resistances else None,
                "market_regime": str(ai_analysis.get('regime', {}).get('market_regime', 'UNKNOWN')),
                "priority": str(ai_analysis.get('priority', {}).get('level', 'LOW')),
                "stop_loss": float(round(strategy_result.get('stopLoss', cmp * 0.98), 2)),
                "target": float(round(strategy_result.get('target', cmp * 1.05), 2)),
                "risk_reward": f"1:{round(float(strategy_result.get('riskReward', 2.0)), 2)}",
                "trade_signal": str(strategy_result.get('entryStatus', 'HOLD')),
                "trade_signal_reason": f"{strategy} Bias: {strategy_result.get('bias', 'NEUTRAL')}. Sector: {sector_state}.",
                "confidence": int(strategy_result.get('confidence', 0))
            },
            "strategy": strategy_result,
            "levels": {
                "primary": rendered_levels,
                "mtf": mtf_levels
            },
            "insights": insights,
            "ai_analysis": ai_analysis,
            "fundamentals": fundamentals,
            "ohlcv": ohlcv,
            "sector_info": {"name": sector_name, "state": sector_state}
        }
        return _json_serializable(response_data)
    except Exception as e:
<<<<<<< codex/check-and-fix-local-code-for-git-push-qlsf0r
        return {
            "status": "error",
            "message": f"Server Error: {str(e)}"
        }
=======
        import traceback
        print(f"CRITICAL API ERROR in get_dashboard: {e}")
        traceback.print_exc()
        return _json_serializable({
            "status": "error",
            "message": f"Server Error: {str(e)}",
            "traceback": traceback.format_exc()
        })


>>>>>>> main

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
        data, alerts = SectorService.get_rotation_data(days=60, timeframe=tf)
        return {
            "status": "success",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": data,
            "alerts": alerts
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/v1/momentum-hits")
async def get_momentum_hits(tf: str = "1D"):
    """
    Returns stocks with momentum hits (price and volume acceleration).
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener

        data = MomentumScreener.get_screener_data(timeframe=tf)
        return {
            "status": "success",
            "count": len(data),
            "data": data
        }
    except Exception as e:
        # Keep response shape stable so UI can render an empty-state instead of hanging.
        return {
            "status": "error",
            "count": 0,
            "data": [],
            "message": str(e)
        }

@app.get("/api/v1/market-summary")
async def get_market_summary(tf: str = "1D"):
    """
    Returns an aggregated AI market summary.
    """
    try:
        from app.services.screener_service import ScreenerService as MomentumScreener
        data = MomentumScreener.get_market_summary_data(timeframe=tf)
        return {
            "status": "success",
            "data": data
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

# Mount Frontend - Robust Path Finding
# Try specific paths for Docker/Render vs Local
try:
    # 1. Docker/Production Path (frontend copied to /app/frontend, main in /app/app/main.py)
    #    BASE_DIR is /app
    
    # Current File: .../app/main.py
    current_file = Path(__file__).resolve()
    
    # 1. Docker Path: /app/app/main.py -> /app/frontend
    # Parent of main.py is /app/app. Parent of that is /app.
    frontend_docker = current_file.parent.parent / "frontend"
    
    # 2. Local Path: .../backend/app/main.py -> .../frontend
    # Parent of main.py is app. Parent is backend. Parent is root.
    frontend_local = current_file.parent.parent.parent / "frontend"
    
    if frontend_docker.exists():
        app.mount("/", StaticFiles(directory=str(frontend_docker), html=True), name="frontend")
        print(f"Mounted frontend from Docker path: {frontend_docker}")
    elif frontend_local.exists():
        app.mount("/", StaticFiles(directory=str(frontend_local), html=True), name="frontend")
        print(f"Mounted frontend from Local path: {frontend_local}")
    else:
        print(f"Frontend directory not found at {frontend_docker} or {frontend_local}")

except Exception as e:
    print(f"Failed to mount frontend: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
