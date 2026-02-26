import sys
import json
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from app.services.screener_service import ScreenerService

def main():
    print("Fetching Full Market Summary JSON...")
    summary = ScreenerService.get_market_summary_data(timeframe="1D")
    print("\n--- START JSON ---")
    print(json.dumps(summary, indent=2))
    print("--- END JSON ---\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
