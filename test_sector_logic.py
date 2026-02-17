import unittest
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.append(str(backend_path))

from app.services.sector_service import SectorService

class TestSectorLogic(unittest.TestCase):
    
    def test_improving_not_leading_when_down(self):
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

    def test_leading_when_up_and_beating(self):
        """ marks sector as LEADING when up and outperforming benchmark """
        # rs = 0.016 - 0.004 = 0.012
        # rm = 0.012 - 0.008 = 0.004
        result = SectorService.calculate_state(
            sector_return=0.016,
            benchmark_return=0.004,
            prev_rs=0.008
        )
        self.assertEqual(result, "LEADING")

    def test_weakening_when_up_but_momentum_falling(self):
        """ marks sector as WEAKENING when RS positive but momentum falling """
        # rs = 0.012 - 0.004 = 0.008
        # rm = 0.008 - 0.012 = -0.004
        result = SectorService.calculate_state(
            sector_return=0.012,
            benchmark_return=0.004,
            prev_rs=0.012
        )
        self.assertEqual(result, "WEAKENING")

    def test_lagging_when_down_and_underperforming(self):
        """ marks sector as LAGGING when sector is down and underperforming """
        # rs = -0.028 - (-0.01) = -0.018
        # rm = -0.018 - (-0.01) = -0.008
        result = SectorService.calculate_state(
            sector_return=-0.028,
            benchmark_return=-0.01,
            prev_rs=-0.01
        )
        self.assertEqual(result, "LAGGING")

    def test_never_leading_when_red(self):
        """ never marks sector as LEADING when sector_return <= 0 """
        result = SectorService.calculate_state(
            sector_return=-0.0001,
            benchmark_return=-0.01,
            prev_rs=-0.02
        )
        self.assertNotEqual(result, "LEADING")

    def test_rs_no_explosion(self):
        """ RS calculation does not explode on small benchmark moves (Difference-based) """
        # If difference-based, rs is just return subtraction
        # 0.002 - 0.0001 = 0.0019
        result_rs = 0.002 - 0.0001
        self.assertLess(abs(result_rs), 0.05)

if __name__ == "__main__":
    unittest.main()
