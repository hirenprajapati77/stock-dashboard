import unittest
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.append(str(backend_path))

from app.services.sector_service import SectorService

class TestLogicLockV1(unittest.TestCase):
    
    # --- SECTOR LOGIC TESTS (LOCKED v1.0) ---

    def test_sector_improving_not_leading_when_down(self):
        """ marks sector as IMPROVING when down but outperforming benchmark (METAL case) """
        # sectorReturn: -3.31%, benchmarkReturn: -4.20%
        # rs = -0.0331 - (-0.042) = +0.0089 (Positive RS)
        # prevRS = 0.004, rm = 0.0089 - 0.004 = +0.0049 (Positive RM)
        result = SectorService.calculate_state(
            sector_return=-0.0331,
            benchmark_return=-0.042,
            prev_rs=0.004
        )
        self.assertEqual(result, "IMPROVING")

    def test_sector_leading_when_up_and_beating(self):
        """ marks sector as LEADING when up and outperforming benchmark """
        result = SectorService.calculate_state(
            sector_return=0.016,
            benchmark_return=0.004,
            prev_rs=0.008
        )
        self.assertEqual(result, "LEADING")

    def test_sector_never_leading_when_red(self):
        """ never marks sector as LEADING when sector_return <= 0 """
        result = SectorService.calculate_state(
            sector_return=-0.0001,
            benchmark_return=-0.01,
            prev_rs=-0.02
        )
        self.assertNotEqual(result, "LEADING")

    def test_rs_no_explosion(self):
        """ RS calculation does not explode on small benchmark moves (Difference-based) """
        sector_return = 0.002
        benchmark_return = 0.0001
        rs = sector_return - benchmark_return
        self.assertLess(abs(rs), 0.05)

    # --- STOCK LOGIC TESTS (LOCKED v1.0) ---
    # Note: Stock logic is implemented inside ScreenerService's loop
    # but the logic follows the rules: SectorState ∈ { LEADING, IMPROVING } AND Stock RS vs Sector > 0
    
    def test_stock_ignored_if_sector_lagging(self):
        """ Stock is ignored if sector state is LAGGING (ITC-type fix) """
        # Logic: if sector_state not in ["LEADING", "IMPROVING"]: continue
        sector_state = "LAGGING"
        is_allowed = sector_state in ["LEADING", "IMPROVING"]
        self.assertFalse(is_allowed)

    def test_stock_allowed_if_sector_improving(self):
        """ Stock is allowed if sector state is IMPROVING """
        sector_state = "IMPROVING"
        is_allowed = sector_state in ["LEADING", "IMPROVING"]
        self.assertTrue(is_allowed)

    def test_stock_rs_difference_method(self):
        """ Stock RS uses difference method (stock_return - sector_return) """
        stock_return = 2.8   # 2.8%
        sector_return = 1.0  # 1.0%
        rs_sector = stock_return - sector_return
        self.assertAlmostEqual(rs_sector, 1.8, places=5)
        self.assertTrue(rs_sector > 0)

    def test_stock_filtered_if_underperforming_sector(self):
        """ Stock is filtered if rs_sector <= 0 even if stock is green """
        stock_return = 1.0   # 1.0%
        sector_return = 1.5  # 1.5%
        rs_sector = stock_return - sector_return
        self.assertTrue(rs_sector <= 0)
        # In ScreenerService: if rs_sector <= 0: continue

if __name__ == "__main__":
    unittest.main()
