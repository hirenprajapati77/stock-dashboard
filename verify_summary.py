
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
    print(f"Global Cues Positive: {data.get('globalCuesPositive')}")
    print(f"Gift Nifty Positive: {data.get('giftNiftyPositive')}")
    print(f"Top Stocks ({len(data['topStocks'])}): {[h['symbol'] for h in data['topStocks']]}")
    
    required_fields = ['marketReturn', 'globalCuesPositive', 'giftNiftyPositive', 'leadingSectors', 'improvingSectors', 'topStocks']
    missing = [f for f in required_fields if f not in data]
    
    if not missing:
        print("\n✅ Verification SUCCESS: All required fields for the Summary Pack are present.")
    else:
        print(f"\n❌ Verification FAILED: Missing fields: {missing}")

if __name__ == "__main__":
    asyncio.run(test_summary())
