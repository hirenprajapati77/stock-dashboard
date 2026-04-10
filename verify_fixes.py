import sys
import os
from pathlib import Path

# Add backend to path
curr_dir = Path(__file__).resolve().parent
if str(curr_dir / "backend") not in sys.path:
    sys.path.append(str(curr_dir / "backend"))

import asyncio
from app.services.trade_decision_service import TradeDecisionService
from app.services.fundamentals import FundamentalService
from app.services.market_data import MarketDataService

async def test_verification():
    print("--- Testing Fundamental Restoration (Proxy) ---")
    symbol = "RELIANCE"
    # Set proxy URL if not set
    if not os.getenv("FYERS_AUTH_PROXY_URL"):
         print("WARNING: FYERS_AUTH_PROXY_URL not set. Proxy methods will fail.")
    
    funda = FundamentalService.get_fundamentals(symbol)
    if funda:
        print(f"Fundamentals for {symbol}:")
        print(f"  MCAP: {funda.get('market_cap')}")
        print(f"  PE: {funda.get('pe_ratio')}")
        print(f"  Sector: {funda.get('sector')}")
    else:
        print(f"Fundamentals for {symbol}: Not available (Proxy might be offline or URL missing)")
    
    print("\n--- Testing Trade Decision Logic Restoration ---")
    mock_hit = {
        "symbol": "TATASTEEL",
        "price": 160.0,
        "technical": {
            "vwap": 158.0,
            "atrExpansion": 2.5,
            "stopDistance": 1.5,
            "swingLow": 155.0,
            "recentHigh": 161.0,
            "momentumStrength": "STRONG"
        },
        "volRatio": 2.0,
        "entryTag": "ENTRY_READY",
        "filterCategory": "HIGH PROBABILITY",
        "sectorState": "LEADING",
        "score": 75
    }
    
    enriched = TradeDecisionService.annotate_many([mock_hit])
    hit = enriched[0]
    plan = hit.get("executionPlan", {})
    
    print(f"Annotated Hit for {hit['symbol']}:")
    print(f"  Trade Tag: {hit.get('tradeDecisionTag')}")
    print(f"  Execution Plan:")
    print(f"    Entry: {plan.get('entry')}")
    print(f"    SL: {plan.get('stopLoss')}")
    print(f"    Target: {plan.get('target1')}")
    print(f"    RR: {plan.get('riskRewardToT1')}")

if __name__ == "__main__":
    asyncio.run(test_verification())
