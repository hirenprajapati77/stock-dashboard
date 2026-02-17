
import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from app.services.screener_service import ScreenerService

async def test_summary():
    print("Testing Market Summary Aggregation...")
    data = ScreenerService.get_market_summary_data(timeframe="1D")
    
    print("\n--- Market Summary Results ---")
    print(f"Market Return: {data['marketReturn']}%")
    print(f"Leading Sectors ({len(data['leadingSectors'])}): {data['leadingSectors']}")
    print(f"Improving Sectors ({len(data['improvingSectors'])}): {data['improvingSectors']}")
    print(f"Lagging Sectors ({len(data['laggingSectors'])}): {data['laggingSectors']}")
    print(f"Top Stocks ({len(data['topStocks'])}): {[h['symbol'] for h in data['topStocks']]}")
    
    if data['marketReturn'] != 0.0 or any([data['leadingSectors'], data['improvingSectors']]):
        print("\n✅ Verification SUCCESS: Data aggregated correctly.")
    else:
        print("\n⚠️ Verification WARNING: Some data might be missing (check sector states).")

if __name__ == "__main__":
    asyncio.run(test_summary())
