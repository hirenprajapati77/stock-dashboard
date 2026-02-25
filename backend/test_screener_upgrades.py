import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from app.services.screener_service import ScreenerService
import json

def test_screener_output():
    print("Testing Screener Data Upgrades...")
    hits = ScreenerService.get_screener_data(timeframe="1D")
    
    if not hits:
        print("No hits found (this is normal if market is closed or no criteria met).")
    else:
        print(f"Found {len(hits)} hits.")
        first_hit = hits[0]
        
        # Check required fields
        required_fields = ["forward3dReturn", "confidence"]
        for field in required_fields:
            if field in first_hit:
                print(f"✓ Found field: {field} = {first_hit[field]}")
            else:
                print(f"✗ Missing field: {field}")
        
        # Check confidence grade
        if first_hit.get("confidence") in ["A", "B", "C", "D"]:
            print(f"✓ Confidence '{first_hit['confidence']}' is a valid grade.")
        else:
            print(f"✗ Invalid confidence grade: {first_hit.get('confidence')}")

        # Check qualityScore in technical
        qs = first_hit.get("technical", {}).get("qualityScore")
        if qs is not None:
             print(f"✓ Found qualityScore: {qs}")
        else:
             print("✗ Missing qualityScore in technical")

def test_summary_output():
    print("\nTesting Market Summary Upgrades...")
    summary = ScreenerService.get_market_summary_data(timeframe="1D")
    
    if "momentumLeaders" in summary:
        print("✓ Found 'momentumLeaders' in summary.")
        leaders = summary["momentumLeaders"]
        print(json.dumps(leaders, indent=2))
        
        # Check for expected keys
        for key in ["topSector", "topQualityStock", "topVolumeStock"]:
            if key in leaders:
                print(f"✓ Found leader key: {key}")
            else:
                print(f"✗ Missing leader key: {key}")
    else:
        print("✗ Missing 'momentumLeaders' in summary.")

    # Check that we didn't break existing summary
    expected_keys = ["marketReturn", "globalCuesPositive", "leadingSectors", "topStocks"]
    for key in expected_keys:
        if key in summary:
            print(f"✓ Found existing summary key: {key}")
        else:
            print(f"✗ Missing existing summary key: {key}")

if __name__ == "__main__":
    try:
        test_screener_output()
        test_summary_output()
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()
