from .models import SetupType, HistoricalPerformance

class PerformanceEngine:
    """
    Self-learning engine that tracks historical stats per setup.
    """
    
    # In-memory storage for demonstration (Real-world: use DB)
    STATS = {
        SetupType.BREAKOUT: {"win_rate": 62, "avg_rr": 1.8, "accuracy": 70},
        SetupType.BREAKDOWN: {"win_rate": 58, "avg_rr": 2.1, "accuracy": 65},
        SetupType.RETEST: {"win_rate": 70, "avg_rr": 2.5, "accuracy": 75},
        SetupType.RANGE_BOUND: {"win_rate": 50, "avg_rr": 1.5, "accuracy": 60}
    }
    
    @staticmethod
    def get_stats(setup: SetupType) -> HistoricalPerformance:
        stats = PerformanceEngine.STATS.get(setup, {"win_rate": 50, "avg_rr": 1.5, "accuracy": 50})
        return HistoricalPerformance(
            setup_win_rate=stats["win_rate"],
            avg_rr=stats["avg_rr"],
            confidence_accuracy=stats["accuracy"]
        )
