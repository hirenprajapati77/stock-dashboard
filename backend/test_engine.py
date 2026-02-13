import numpy as np
import pandas as pd

from app.engine.confidence import ConfidenceEngine
from app.engine.sr import SREngine
from app.engine.swing import SwingEngine
from app.engine.zones import ZoneEngine


def _build_sample_ohlcv(rows: int = 240) -> pd.DataFrame:
    """Create deterministic OHLCV data so engine tests don't depend on network."""
    idx = pd.date_range("2024-01-01", periods=rows, freq="D")
    base = 100 + np.sin(np.linspace(0, 12 * np.pi, rows)) * 5 + np.linspace(0, 20, rows)

    df = pd.DataFrame(
        {
            "open": base + 0.2,
            "high": base + 1.5,
            "low": base - 1.5,
            "close": base,
            "volume": np.linspace(100_000, 250_000, rows),
        },
        index=idx,
    )
    return df


def test_engine_with_synthetic_data():
    """Validates core engine stages end-to-end on predictable sample data."""
    df = _build_sample_ohlcv()

    sh, sl = SwingEngine.get_swings(df)
    assert isinstance(sh, list)
    assert isinstance(sl, list)

    atr = ZoneEngine.calculate_atr(df).iloc[-1]
    assert atr > 0

    all_swings = sh + sl
    zones = ZoneEngine.cluster_swings(all_swings, atr)
    assert isinstance(zones, list)

    cmp = df["close"].iloc[-1]
    supports, resistances = SREngine.classify_levels(zones, cmp)
    assert isinstance(supports, list)
    assert isinstance(resistances, list)

    if supports:
        support = supports[0]
        avg_vol = float(df["volume"].tail(50).mean())
        score = ConfidenceEngine.calculate_score(support, "1D", atr, df.index[-1], avg_vol)
        label = ConfidenceEngine.get_label(score)

        assert 0 <= score <= 100
        assert label in {"Weak", "Moderate", "Strong", "Very Strong"}
