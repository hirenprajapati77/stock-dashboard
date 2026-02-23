import pandas as pd

from app.engine.regime import MarketRegimeEngine


def test_detect_regime_returns_known_value_for_valid_dataframe():
    idx = pd.date_range("2025-01-01", periods=80, freq="D")
    # Mild uptrend with small noise
    close = pd.Series([100 + (i * 0.45) + ((-1) ** i) * 0.1 for i in range(80)], index=idx)
    df = pd.DataFrame({"close": close})

    regime = MarketRegimeEngine.detect_regime(df)

    assert regime in {
        "STRONG_UPTREND",
        "UPTREND",
        "RANGE",
        "WEAK_TREND",
        "STRONG_DOWNTREND",
        "UNKNOWN",
    }
    assert regime != "UNKNOWN"


def test_get_grade_maps_confidence_thresholds():
    assert MarketRegimeEngine.get_grade(95) == "A+"
    assert MarketRegimeEngine.get_grade(81) == "A"
    assert MarketRegimeEngine.get_grade(70) == "B"
    assert MarketRegimeEngine.get_grade(50) == "C"
    assert MarketRegimeEngine.get_grade(10) == "D"
