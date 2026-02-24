from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import pandas as pd
import requests
import uvicorn
import os

# ... (imports)

app = FastAPI(title="Support & Resistance Dashboard")
from app.services.fundamentals import FundamentalService
from app.services.screener import ScreenerService
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine
from app.engine.sr import SREngine
from app.engine.insights import InsightEngine
from app.engine.confidence import ConfidenceEngine
from app.ai.engine import AIEngine

app = FastAPI(title="Support & Resistance Dashboard")
ai_engine = AIEngine()

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
        if 'quotes' in data:
            for item in data['quotes']:
                results.append({
                    "symbol": item.get('symbol'),
                    "shortname": item.get('shortname', item.get('longname', '')),
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
async def get_dashboard(symbol: str = "RELIANCE", tf: str = "1D", strategy: str = "SR"):
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
        
        # 3. Get Sector State for guards
        from app.services.sector_service import SectorService
        from app.services.constituent_service import ConstituentService
        
        sector_name = ConstituentService.get_sector_for_ticker(norm_symbol)
        sector_state = "NEUTRAL"
        if sector_name:
            rotation_data, _ = SectorService.get_rotation_data(timeframe=tf)
            if sector_name in rotation_data:
                sector_state = rotation_data[sector_name]['metrics']['state']
        
        # 4. Strategy Dispatcher
        strategy_result = {}
        if strategy == "SR":
            strategy_result = SREngine.runSRStrategy(df, sector_state, supports, resistances)
        elif strategy == "SWING":
            # Get 1D for structure/trend if needed, or use current DF
            htf = "1D" if tf != "1D" else "1W"
            hdf, _ = MarketDataService.get_ohlcv(norm_symbol, htf)
            htf_trend = InsightEngine.get_structure_bias(hdf)
            strategy_result = SwingEngine.runSwingStrategy(df, sector_state, htf_trend, supports, resistances)
        elif strategy == "DEMAND_SUPPLY":
            zones = ZoneEngine.calculate_demand_supply_zones(df)
            strategy_result = ZoneEngine.runDemandSupplyStrategy(df, sector_state, zones)
            
        # 5. Extract MTF Levels
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
                
        # 6. Get Insights
        ai_analysis = ai_engine.get_insights(df)
        fundamentals = FundamentalService.get_fundamentals(norm_symbol)

        insights = {
            "inside_candle": InsightEngine.is_inside_candle(df),
            "retest": InsightEngine.detect_retest(df, supports + resistances),
            "ema_bias": InsightEngine.get_ema_bias(df),
            "hammer": InsightEngine.detect_hammer(df),
            "engulfing": InsightEngine.detect_engulfing(df),
            "upside_pct": float(round(((resistances[0]['price'] - cmp) / cmp * 100), 2)) if resistances else 0.0,
            "adx": round(InsightEngine.get_adx(df), 2),
            "structure": InsightEngine.get_structure_bias(df)
        }
        
        # 7. Format OHLCV for Chart
        ohlcv = [{
            "time": int(df.index[i].timestamp()),
            "open": float(round(df['open'].iloc[i], 2)),
            "high": float(round(df['high'].iloc[i], 2)),
            "low": float(round(df['low'].iloc[i], 2)),
            "close": float(round(df['close'].iloc[i], 2))
        } for i in range(len(df))]

        # 8. Response Structure
        return {
            "meta": {
                "symbol": norm_symbol,
                "tf": tf,
                "strategy": strategy,
                "cmp": float(round(cmp, 2)),
                "data_version": "v1.4.0"
            },
            "summary": {
                "nearest_support": float(round(supports[0]['price'], 2)) if supports else None,
                "nearest_resistance": float(round(resistances[0]['price'], 2)) if resistances else None,
                "market_regime": ai_analysis.get('regime', {}).get('market_regime', 'UNKNOWN'),
                "priority": ai_analysis.get('priority', {}).get('level', 'LOW'),
                "stop_loss": strategy_result.get('stopLoss', cmp * 0.98),
                "risk_reward": f"1:{strategy_result.get('riskReward', 2.0)}",
                "trade_signal": strategy_result.get('entryStatus', 'HOLD'),
                "trade_signal_reason": f"{strategy} Bias: {strategy_result.get('bias', 'NEUTRAL')}. Sector: {sector_state}.",
                "confidence": strategy_result.get('confidence', 0)
            },
            "strategy": strategy_result,
            "levels": {
                "primary": {"supports": supports, "resistances": resistances},
                "mtf": mtf_levels
            },
            "insights": insights,
            "ai_analysis": ai_analysis,
            "fundamentals": fundamentals,
            "sector_info": {"name": sector_name, "state": sector_state},
            "ohlcv": ohlcv
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": f"Server Error: {str(e)}",
            "traceback": traceback.format_exc()
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
