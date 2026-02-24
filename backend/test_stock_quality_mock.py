import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.services.screener_service import ScreenerService

def test_stock_logic_mock():
    print("--- Testing Stock Quality Scoring (Mocked) ---")

    # Case 1: High Quality — strong RS, high vol, bullish, good ATR, good acc
    score1 = ScreenerService.calculate_quality_score(
        rs_sector=2.5, stock_acc=0.03, vol_ratio=2.5,
        structure_bias="BULLISH", rr=2.0, atr_expansion=1.5
    )
    tag1 = ScreenerService.get_entry_tag(score1, "LEADING", True)
    print(f"High Quality: Score={score1}, Tag={tag1}")
    assert score1 >= 80, f"High quality should be STRONG_ENTRY, got {score1}"
    assert tag1 == "STRONG_ENTRY"

    # Case 2: WATCHLIST — meaningful RS, breakeven acc, moderate vol
    score2 = ScreenerService.calculate_quality_score(
        rs_sector=1.5, stock_acc=0.02, vol_ratio=1.8,
        structure_bias="BULLISH", rr=2.0, atr_expansion=1.2
    )
    tag2 = ScreenerService.get_entry_tag(score2, "LEADING", True)
    print(f"Watchlist Quality: Score={score2}, Tag={tag2}")
    assert score2 >= 65, f"Medium-good setup should be at least ENTRY_READY, got {score2}"
    assert tag2 in ["ENTRY_READY", "STRONG_ENTRY"]

    # Case 3: AVOID — low RS, lagging sector
    score3 = ScreenerService.calculate_quality_score(
        rs_sector=-1.0, stock_acc=-0.02, vol_ratio=0.8,
        structure_bias="BEARISH", rr=1.0, atr_expansion=0.9
    )
    tag3 = ScreenerService.get_entry_tag(score3, "LAGGING", True)
    print(f"Poor Quality / Lagging: Score={score3}, Tag={tag3}")
    assert tag3 == "AVOID"

    # Case 4: WATCHLIST threshold
    score4 = ScreenerService.calculate_quality_score(
        rs_sector=0.5, stock_acc=0.005, vol_ratio=1.5,
        structure_bias="NEUTRAL", rr=1.8, atr_expansion=1.1
    )
    tag4 = ScreenerService.get_entry_tag(score4, "IMPROVING", True)
    print(f"Borderline: Score={score4}, Tag={tag4}")
    # Accept WATCHLIST or above for borderline
    assert tag4 in ["WATCHLIST", "ENTRY_READY", "STRONG_ENTRY"], f"Unexpected tag: {tag4}"

    print("\nSUCCESS: All mock stock logic assertions passed!")

if __name__ == "__main__":
    test_stock_logic_mock()
