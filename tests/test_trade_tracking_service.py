from __future__ import annotations

from pathlib import Path

from backend.app.services.observability_service import ObservabilityService
from backend.app.services.trade_tracking_service import TradeTrackingService


def make_trade(action: str = "BUY", **overrides):
    hit = {
        "symbol": "ABC",
        "action": action,
        "score": 82,
        "confidence": 78,
        "price": 100.0,
        "rr": 2.0,
        "sector": "BANK",
        "setupType": "BREAKOUT_RETEST",
        "hitAsOf": "2026-03-15T00:00:00+00:00",
        "forward3dReturn": 3.5 if action == "BUY" else None,
        "executionPlan": {
            "entry": 100.0,
            "stopLoss": 98.0,
            "target1": 103.0,
            "confirmationMode": "PULLBACK_HOLD",
            "entryType": "Pullback entry",
            "riskRewardToT1": 1.5,
        },
    }
    hit.update(overrides)
    return hit


def test_trade_logging_persists_required_fields(tmp_path, monkeypatch):
    log_path = tmp_path / "trade_log.json"
    obs_path = tmp_path / "observability.json"
    monkeypatch.setattr(TradeTrackingService, "LOG_FILE", log_path)
    monkeypatch.setattr(ObservabilityService, "LOG_FILE", obs_path)

    TradeTrackingService.log_trades([make_trade()], market_context={"regime": "TREND"}, mode="safe")
    rows = TradeTrackingService._load()

    assert len(rows) == 1
    row = rows[0]
    for key in ("symbol", "action", "score", "confidence", "entry", "stop_loss", "target", "rr", "market_context", "mode", "timestamp"):
        assert key in row
    assert row["market_context"]["regime"] == "TREND"
    assert row["mode"] == "safe"
    assert row["outcome"] == "HIT_TARGET"


def test_trade_outcomes_cover_target_expired_and_no_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(TradeTrackingService, "LOG_FILE", tmp_path / "trade_log.json")
    monkeypatch.setattr(ObservabilityService, "LOG_FILE", tmp_path / "observability.json")

    hits = [
        make_trade(symbol="WIN", forward3dReturn=4.0),
        make_trade(symbol="LOSS", forward3dReturn=-3.0),
        make_trade(symbol="EXP", forward3dReturn=0.5),
        make_trade(
            symbol="NOENTRY",
            price=95.0,
            hitAsOf="2026-03-10T00:00:00+00:00",
            forward3dReturn=None,
            executionPlan={"entry": 100.0, "stopLoss": 98.0, "target1": 103.0, "confirmationMode": "BREAKOUT_TRIGGER", "riskRewardToT1": 1.5},
        ),
    ]

    TradeTrackingService.log_trades(hits, market_context={"regime": "TREND"}, mode="aggressive")
    rows = {row["symbol"]: row for row in TradeTrackingService._load()}

    assert rows["WIN"]["outcome"] == "HIT_TARGET"
    assert rows["LOSS"]["outcome"] == "HIT_STOP_LOSS"
    assert rows["EXP"]["outcome"] == "EXPIRED"
    assert rows["NOENTRY"]["outcome"] == "NO_ENTRY_TRIGGERED"


def test_performance_metrics_and_alerts_include_observability(tmp_path, monkeypatch):
    monkeypatch.setattr(TradeTrackingService, "LOG_FILE", tmp_path / "trade_log.json")
    monkeypatch.setattr(ObservabilityService, "LOG_FILE", tmp_path / "observability.json")

    TradeTrackingService.log_trades(
        [
            make_trade(symbol="WIN1", forward3dReturn=4.0),
            make_trade(symbol="WIN2", forward3dReturn=3.6),
            make_trade(symbol="LOSS1", forward3dReturn=-3.0),
            make_trade(action="NO TRADE", symbol="SKIP1"),
            make_trade(action="NO TRADE", symbol="SKIP2"),
            make_trade(action="NO TRADE", symbol="SKIP3"),
            make_trade(action="NO TRADE", symbol="SKIP4"),
        ],
        market_context={"regime": "RANGE"},
        mode="safe",
    )
    ObservabilityService.record_api_failure("/api/v1/momentum-hits", "boom")
    ObservabilityService.record_missing_data("momentum_hits", {"tf": "1D"})
    ObservabilityService.record_fail_safe("TradeDecisionService", {"symbol": "ABC"})

    perf = TradeTrackingService.get_performance()

    assert perf["winRate"] > 0
    assert perf["avgRRAchieved"] != 0
    assert perf["bestPerformingSetup"]["label"] == "BREAKOUT_RETEST"
    assert any(item["label"] == "BANK" for item in perf["performanceBySector"])
    assert perf["observability"]["apiFailures"] == 1
    assert perf["observability"]["missingDataCases"] == 1
    assert perf["observability"]["failSafeTriggers"] == 1
    assert perf["strategyInsights"]["suggestedFocusAreas"]


def test_adaptive_intelligence_surfaces_underperforming_setup_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr(TradeTrackingService, "LOG_FILE", tmp_path / "trade_log.json")
    monkeypatch.setattr(ObservabilityService, "LOG_FILE", tmp_path / "observability.json")

    rows = []
    for idx in range(8):
        rows.append({
            "tradeKey": f"BAD_{idx}",
            "symbol": f"BAD{idx}",
            "action": "BUY",
            "outcome": "HIT_STOP_LOSS" if idx < 6 else "EXPIRED",
            "realizedRR": -1.0 if idx < 6 else -0.2,
            "pnlPct": -2.5 if idx < 6 else -0.3,
            "setupType": "BREAKOUT",
            "sector": "AUTO",
            "timestamp": f"2026-03-{20-idx:02d}T00:00:00+00:00",
        })
    for idx in range(5):
        rows.append({
            "tradeKey": f"GOOD_{idx}",
            "symbol": f"GOOD{idx}",
            "action": "BUY",
            "outcome": "HIT_TARGET",
            "realizedRR": 1.8,
            "pnlPct": 3.8,
            "setupType": "BREAKOUT_RETEST",
            "sector": "BANK",
            "timestamp": f"2026-03-{10-idx:02d}T00:00:00+00:00",
        })

    TradeTrackingService._save(rows)

    perf = TradeTrackingService.get_performance()
    adaptive = perf["adaptiveIntelligence"]

    assert adaptive["setupProfiles"]["BREAKOUT"]["underperforming"] is True
    assert any(alert["type"] == "SETUP_UNDERPERFORMING" for alert in perf["alerts"])
    assert any("Reduce size" in item or "Lean into" in item for item in adaptive["focusAreas"])
