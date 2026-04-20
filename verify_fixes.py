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
    
    print("\n--- Testing Trade Decision Logic: Recalibration (Fatigue Check) ---")
    
    # CASE 1: Classic Breakout (Should still work)
    t1_hit = {
        "symbol": "TATASTEEL",
        "price": 160.0,
        "technical": {
            "isBreakout": True,
            "vwap": 158.0,
            "momentumStrength": "STRONG"
        },
        "volRatio": 2.0,
        "sectorState": "LEADING",
        "stopLoss": 155.0,
        "target": 170.0
    }
    
    # CASE 2: Bounce Setup (Previously resulted in AVOID)
    # No retest or breakout here, just proximity to support
    t2_hit = {
        "symbol": "RELIANCE",
        "price": 2950.0,
        "nearest_support": 2920.0,
        "technical": {
            "vwap": 2940.0,
            "momentumStrength": "MODERATE"
        },
        "volRatio": 1.2,
        "sectorState": "IMPROVING",
        "stopLoss": 2910.0,
        "target": 3050.0
    }

    # CASE 3: Short Setup (New)
    t3_hit = {
        "symbol": "HDFCBANK",
        "price": 1450.0,
        "side": "SHORT",
        "nearest_resistance": 1470.0,
        "technical": {
            "vwap": 1460.0,
            "momentumStrength": "WEAK"
        },
        "volRatio": 1.5,
        "sectorState": "LAGGING",
        "stopLoss": 1480.0,
        "target": 1400.0
    }

    # CASE 4: Strong Engine Recommendation (Fatigue Reduction)
    # Low internal metrics but engine says STRONG_ENTRY
    t4_hit = {
        "symbol": "INFY",
        "price": 1500.0,
        "entryStatus": "STRONG_ENTRY",
        "technical": {
            "vwap": 1490.0,
            "momentumStrength": "WEAK"
        },
        "volRatio": 0.9,
        "sectorState": "NEUTRAL",
        "stopLoss": 1480.0,
        "target": 1550.0
    }

    test_cases = [t1_hit, t2_hit, t3_hit, t4_hit]
    enriched = TradeDecisionService.annotate_many(test_cases)
    
    for i, hit in enumerate(enriched):
        print(f"\n[Test Case {i+1}] {hit['symbol']}:")
        print(f"  Side: {hit.get('side')}")
        print(f"  Action: {hit.get('tradeDecisionTag')}")
        print(f"  Score: {hit.get('score')}")
        print(f"  Tags: {hit.get('reasonTags')}")
        if 'isBreakout' in hit.get('technical', {}):
             print(f"  Is Breakout: {hit['technical']['isBreakout']}")
        if i == 1: # Print bounce specific check
             print(f"  Is Bounce Detected: {'Bounce Found' in hit.get('reasonTags', [])}")

if __name__ == "__main__":
    asyncio.run(test_verification())
