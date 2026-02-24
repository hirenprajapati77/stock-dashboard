import sys
import os
import json
import asyncio

# Add path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.services.sector_service import SectorService
from backend.app.services.screener_service import ScreenerService

def test_predictive_system():
    print("--- Testing Sector Intelligence Upgrade ---")
    sectors, alerts = SectorService.get_rotation_data(timeframe="1D", include_constituents=True)
    
    if not sectors:
        print("FAILURE: No sector data returned.")
        return

    # Check for new fields in first sector
    first_sector = next(iter(sectors.values()))
    metrics = first_sector.get('metrics', {})
    
    fields = ['accelerationScore', 'breadthScore', 'rotationScore']
    for field in fields:
        if field in metrics:
            print(f"SUCCESS: Found {field}: {metrics[field]}")
        else:
            print(f"FAILURE: Missing {field} in sector metrics.")

    # Check ranking
    sorted_names = sorted(sectors.keys(), key=lambda n: sectors[n]['metrics']['rotationScore'], reverse=True)
    top_sector = sorted_names[0]
    if sectors[top_sector]['rank'] == 1:
        print(f"SUCCESS: Sector ranking follows RotationScore correctly (Top: {top_sector})")
    else:
        print(f"FAILURE: Sector ranking mismatch.")

    print("\n--- Testing Stock Selection Upgrade ---")
    hits = ScreenerService.get_screener_data(timeframe="1D")
    
    if not hits:
        print("NOTE: No momentum hits currently found (market might be flat).")
    else:
        first_hit = hits[0]
        tech = first_hit.get('technical', {})
        if 'qualityScore' in tech:
            print(f"SUCCESS: Found qualityScore: {tech['qualityScore']}")
        else:
            print("FAILURE: Missing qualityScore in stock technical metrics.")
            
        if 'structureBias' in tech:
            print(f"SUCCESS: Found structureBias: {tech['structureBias']}")
            
        if first_hit['entryTag'] in ["STRONG_ENTRY", "ENTRY_READY", "WATCHLIST", "AVOID"]:
            print(f"SUCCESS: Found updated entryTag: {first_hit['entryTag']}")
        else:
            print(f"FAILURE: Unexpected entryTag: {first_hit['entryTag']}")

if __name__ == "__main__":
    test_predictive_system()
