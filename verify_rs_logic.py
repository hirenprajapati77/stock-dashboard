import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.append(str(backend_path))

try:
    from app.services.sector_service import SectorService
    import json
    from datetime import datetime

    def test_logic():
        print(f"--- Sector Intelligence Logic Test ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
        
        # Test with 1D timeframe
        results, alerts = SectorService.get_rotation_data(timeframe="1D")
        
        if not results:
            print("ERROR: No results returned from SectorService.")
            return

        print(f"\nVerification Results for '1D' Timeframe:")
        print(f"{'Sector':<20} | {'Return':<8} | {'RS':<8} | {'State':<12} | {'Commentary Snippet'}")
        print("-" * 80)
        
        sorted_results = sorted(results.items(), key=lambda x: x[1]['rank'])
        
        for name, data in sorted_results:
            last_hist = data['history'][-1] if data['history'] else {'rs': 0}
            metrics = data['metrics']
            rs_val = last_hist['rs']
            state = metrics['state']
            
            # Note: We need to pull the return from the history or trace back
            # For this debug, we can just look at the mapping
            print(f"{name:<20} | {'N/A':<8} | {rs_val*100:>7.2f}% | {state:<12} | {data['commentary'][:50]}...")

        # Sanity Checks
        leading_count = sum(1 for d in results.values() if d['metrics']['state'] == "LEADING")
        exploding_rs = sum(1 for d in results.values() if abs(d['history'][-1]['rs']) > 0.5) # Over 50% RS diff is rare/suspicious for index
        
        print("\n--- Analytics Check ---")
        print(f"Total Sectors: {len(results)}")
        print(f"Leading Sectors: {leading_count} (Should be <= 3)")
        print(f"Exploding RS Bug Check: {exploding_rs} cases (Should be 0)")
        
        if leading_count > 3:
            print("WARNING: Logic might be overly optimistic (Too many LEADING).")
        if exploding_rs > 0:
            print("WARNING: RS values still look too high/exploding.")

    if __name__ == "__main__":
        test_logic()

except Exception as e:
    import traceback
    print(f"Test failed: {e}")
    traceback.print_exc()
