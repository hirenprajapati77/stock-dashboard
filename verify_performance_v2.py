import sys
import os
import time
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from app.services.screener_service import ScreenerService
from app.services.constituent_service import ConstituentService

def test_screener_performance():
    print("Testing ScreenerService Performance & Caching...")
    
    # 1. First run (Cold)
    start_time = time.time()
    data1 = ScreenerService.get_screener_data("Daily")
    end_time = time.time()
    print(f"First run (Cold) took: {end_time - start_time:.2f} seconds")
    print(f"Results found: {len(data1)}")
    
    # 2. Second run (Should be from cache)
    start_time = time.time()
    data2 = ScreenerService.get_screener_data("Daily")
    end_time = time.time()
    print(f"Second run (Cached) took: {end_time - start_time:.4f} seconds")
    
    if (end_time - start_time) < 0.1:
        print("SUCCESS: Caching is working.")
    else:
        print("FAILURE: Caching is NOT working.")

    # 3. Check for specific symbols
    symbols = [h['symbol'] for h in data1]
    if "M&M" in symbols:
        print("SUCCESS: M&M.NS is being correctly screened.")
    else:
        print("WARNING: M&M.NS not found in screener results (might not have momentum hits).")

    if "DISHMAN" in symbols:
        print("FAILURE: DISHMAN still present in results.")
    else:
        print("SUCCESS: DISHMAN removed.")

    # 4. Verify data types (Internal JSON check)
    if data1:
        hit = data1[0]
        print(f"Sample Hit: {hit['symbol']} at {hit['price']} ({hit['change']}%)")
        # Check if any value is numpy
        import numpy as np
        for k, v in hit.items():
            if isinstance(v, (np.generic, np.ndarray)):
                print(f"FAILURE: Key '{k}' still has numpy type: {type(v)}")
                return
        print("SUCCESS: All data types are JSON serializable (no numpy detected).")

if __name__ == "__main__":
    test_screener_performance()
