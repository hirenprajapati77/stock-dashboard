import os
import sys

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'app'))

import app.services.sector_service
from app.services.sector_service import SectorService
import json

def test():
    print(f"DEBUG: SectorService file: {app.services.sector_service.__file__}")
    print("Testing SectorService.get_rotation_data()...")
    try:
        data, alerts = SectorService.get_rotation_data(timeframe="1D")
        print(f"\nResult data keys: {list(data.keys())}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
