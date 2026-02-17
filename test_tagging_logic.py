import unittest
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.append(str(backend_path))

from app.services.screener_service import ScreenerService

class TestTaggingLogic(unittest.TestCase):
    
    def test_entry_ignored_if_sector_lagging(self):
        """ marks ENTRY as AVOID if sector is LAGGING even if stock is green """
        # sectorState: LAGGING, stockActive: True
        tag = ScreenerService.get_entry_tag(
            stock_active=True,
            sector_state="LAGGING",
            price_above_vwap=True,
            breakout_confirmed=True,
            vol_ratio=2.5
        )
        self.assertEqual(tag, "AVOID")

    def test_entry_ready_conditions(self):
        """ marks ENTRY_READY when all conditions align """
        # sectorState: LEADING, stockActive: True, aboveVWAP: True, breakout: True, vol: 2.0
        tag = ScreenerService.get_entry_tag(
            stock_active=True,
            sector_state="LEADING",
            price_above_vwap=True,
            breakout_confirmed=True,
            vol_ratio=2.0
        )
        self.assertEqual(tag, "ENTRY_READY")

    def test_entry_wait_conditions(self):
        """ marks WAIT when setup is good but confirmation pending """
        # breakout_confirmed: False
        tag = ScreenerService.get_entry_tag(
            stock_active=True,
            sector_state="LEADING",
            price_above_vwap=True,
            breakout_confirmed=False,
            vol_ratio=1.6
        )
        self.assertEqual(tag, "WAIT")

    def test_exit_on_lagging_sector(self):
        """ marks EXIT if sector turns LAGGING """
        tag = ScreenerService.get_exit_tag(
            price_below_vwap=False,
            vol_drop=False,
            sector_state="LAGGING"
        )
        self.assertEqual(tag, "EXIT")

    def test_exit_on_vwap_breach(self):
        """ marks EXIT if price below VWAP and volume drops """
        tag = ScreenerService.get_exit_tag(
            price_below_vwap=True,
            vol_drop=True,
            sector_state="LEADING"
        )
        self.assertEqual(tag, "EXIT")

    def test_risk_level_low(self):
        """ marks risk LOW for high vol in leading sector """
        risk = ScreenerService.get_risk_level(
            sector_state="LEADING",
            vol_ratio=2.5,
            vol_high=False
        )
        self.assertEqual(risk, "LOW")

    def test_risk_level_high_on_volatility(self):
        """ marks risk HIGH if volatility is high """
        risk = ScreenerService.get_risk_level(
            sector_state="LEADING",
            vol_ratio=2.5,
            vol_high=True
        )
        self.assertEqual(risk, "HIGH")

if __name__ == "__main__":
    unittest.main()
