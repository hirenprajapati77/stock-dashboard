from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import pandas as pd
import requests
import uvicorn
import os
from datetime import datetime

from app.services.market_data import MarketDataService
from app.services.fundamentals import FundamentalService
from app.services.screener import ScreenerService
from app.services.sector_service import SectorService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.insights import InsightEngine
from app.engine.confidence import ConfidenceEngine
from app.ai.engine import AIEngine

app = FastAPI(title="Support & Resistance Dashboard")
ai_engine = AIEngine()


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

def detect_levels_for_df(df: pd.DataFrame, tf: str):
    cmp = df['close'].iloc[-1]
    sh, sl = SwingEngine.get_swings(df)
    atr = ZoneEngine.calculate_atr(df).iloc[-1]
    all_swings = sh + sl
    zones = ZoneEngine.cluster_swings(all_swings, atr)
    supports, resistances = SREngine.classify_levels(zones, cmp)
    
    last_date = df.index[-1]
    avg_vol = float(df['volume'].tail(50).mean())
    
    for s in supports:
        s['confidence'] = ConfidenceEngine.calculate_score(s, tf, atr, last_date, avg_vol)
        s['label'] = ConfidenceEngine.get_label(s['confidence'])
        s['timeframe'] = tf
        
    for r in resistances:
        r['confidence'] = ConfidenceEngine.calculate_score(r, tf, atr, last_date, avg_vol)
        r['label'] = ConfidenceEngine.get_label(r['confidence'])
        r['timeframe'] = tf
        
    return supports, resistances

@app.get("/api/v1/dashboard")
async def get_dashboard(response: Response, symbol: str = "RELIANCE", tf: str = "1D"):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    try:
        # 0. Normalize Symbol
        norm_symbol = MarketDataService.normalize_symbol(symbol)

        # 1. Get Data
        df, currency = MarketDataService.get_ohlcv(norm_symbol, tf)
        if df.empty:
            return {"status": "error", "message": f"No data found for {symbol}. Try another symbol or timeframe."}
            
        cmp = df['close'].iloc[-1]
        
        # 2. Extract Levels (Primary)
        supports, resistances = detect_levels_for_df(df, tf)
        
        # 3. Extract MTF Levels
        higher_tfs = []
        if tf == "5m": higher_tfs = ["15m", "1H", "1D"]
        elif tf == "15m": higher_tfs = ["1H", "2H", "1D"]
        elif tf == "1H": higher_tfs = ["2H", "4H", "1D"]
        elif tf == "2H": higher_tfs = ["4H", "1D", "1W"]
        elif tf == "4H": higher_tfs = ["1D", "1W", "1M"]
        elif tf == "75m": higher_tfs = ["1D", "1W", "1M"]
        elif tf == "1D": higher_tfs = ["1W", "1M"]
        elif tf == "1W": higher_tfs = ["1M"]
        
        mtf_levels = {"supports": [], "resistances": []}
        for htf in higher_tfs:
            try:
                hdf, _ = MarketDataService.get_ohlcv(norm_symbol, htf)
                hs, hr = detect_levels_for_df(hdf, htf)
                mtf_levels["supports"].extend(hs)
                mtf_levels["resistances"].extend(hr)
            except Exception as e:
                print(f"MTF error for {htf}: {e}")
                
        # 4. Get Insights
        # Get Global AI Insights
        ai_analysis = ai_engine.get_insights(df)
        
        # Get Fundamentals
        fundamentals = FundamentalService.get_fundamentals(norm_symbol)

        insights = {
            "inside_candle": bool(InsightEngine.is_inside_candle(df)),
            "retest": bool(InsightEngine.detect_retest(df, supports + resistances)),
            "ema_bias": InsightEngine.get_ema_bias(df),
            "hammer": bool(InsightEngine.detect_hammer(df)),
            "engulfing": InsightEngine.detect_engulfing(df),
            "upside_pct": float(round(((resistances[0]['price'] - cmp) / cmp * 100), 2)) if resistances else 0.0
        }

        nearest_support, nearest_resistance = _resolve_summary_levels(cmp, supports, resistances, mtf_levels)
        stop_loss = float(round((nearest_support * 0.99), 2)) if nearest_support is not None else float(round(cmp * 0.98, 2))

        rr_ratio_value = None
        if nearest_support is not None and nearest_resistance is not None:
            downside = cmp - nearest_support
            upside = nearest_resistance - cmp
            if downside > 0 and upside > 0:
                rr_ratio_value = round(upside / downside, 2)

        rr_display = f"1:{rr_ratio_value:.1f}" if rr_ratio_value is not None else "1:2.0"
        trade_signal, trade_signal_reason = _build_trade_signal(insights["ema_bias"], rr_ratio_value)
        
        # 5. Format OHLCV for Chart
        ohlcv = []
        for i in range(len(df)):
            ohlcv.append({
                "time": int(df.index[i].timestamp()),
                "open": float(round(df['open'].iloc[i], 2)),
                "high": float(round(df['high'].iloc[i], 2)),
                "low": float(round(df['low'].iloc[i], 2)),
                "close": float(round(df['close'].iloc[i], 2))
            })

        # 6. Response Structure
        return {
            "meta": {
                "symbol": norm_symbol,
                "tf": tf,
                "cmp": float(round(cmp, 2)),
                "currency": currency,
                "last_update": datetime.now().strftime("%H:%M:%S"),
                "data_version": "v1.4.3"
            },
            "summary": {
                "nearest_support": float(round(nearest_support, 2)) if nearest_support is not None else None,
                "nearest_resistance": float(round(nearest_resistance, 2)) if nearest_resistance is not None else None,
                "market_regime": str(ai_analysis.get('regime', {}).get('market_regime', 'UNKNOWN')),
                "priority": str(ai_analysis.get('priority', {}).get('level', 'LOW')),
                "stop_loss": float(stop_loss),
                "risk_reward": str(rr_display),
                "risk_reward_value": float(rr_ratio_value) if rr_ratio_value is not None else None,
                "trade_signal": str(trade_signal),
                "trade_signal_reason": str(trade_signal_reason)
            },
            "levels": {
                "primary": {
                    "supports": supports,
                    "resistances": resistances
                },
                "mtf": mtf_levels
            },
            "insights": insights,
            "ai_analysis": ai_analysis,
            "fundamentals": fundamentals,
            "ohlcv": ohlcv
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Server Error: {str(e)}"
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
