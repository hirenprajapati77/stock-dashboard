from __future__ import annotations

import logging

import pytest

from backend.app.services.trade_decision_service import TradeDecisionService


def make_hit(**overrides):
    hit = {
        "symbol": "TEST",
        "price": 100.0,
        "sectorState": "LEADING",
        "summary": {
            "cmp": 100.0,
            "nearest_support": 99.0,
            "nearest_resistance": 112.0,
            "target": 112.0,
            "market_regime": "STABLE",
        },
        "technical": {
            "adx": 30.0,
            "isBreakout": True,
            "retest": True,
            "volRatio": 2.0,
            "volHigh": False,
            "momentumStrength": "STRONG",
        },
        "ohlcv": [
            {"open": 97.0, "high": 99.0, "low": 96.5, "close": 98.0},
            {"open": 98.0, "high": 100.0, "low": 97.5, "close": 99.0},
            {"open": 99.0, "high": 101.0, "low": 98.5, "close": 100.0},
        ],
    }
    for key, value in overrides.items():
        if key in {"summary", "technical"}:
            hit[key].update(value)
        else:
            hit[key] = value
    return hit


def test_invalid_setup_returns_no_trade():
    result = TradeDecisionService.compute_trade_score(
        make_hit(
            summary={
                "nearest_support": None,
                "nearest_resistance": None,
                "target": None,
                "market_regime": "RANGE",
            },
            technical={
                "adx": 10.0,
                "isBreakout": False,
                "retest": False,
                "volRatio": 0.8,
                "momentumStrength": "WEAK",
            },
            sectorState="NEUTRAL",
        )
    )

    assert result["action"] == "NO TRADE"
    assert result["isValidTrade"] is False
    assert "Avoid entering this trade." in result["explanation"]


def test_valid_setup_returns_buy():
    result = TradeDecisionService.compute_trade_score(make_hit())

    assert result["action"] == "BUY"
    assert result["isValidTrade"] is True
    assert result["rr"] >= TradeDecisionService.BUY_RR
    assert result["grade"] in {"A+", "A", "B", "C", "D"}


def test_performance_weighted_scoring_boosts_strong_setup_and_sector():
    adaptive = {
        "setupProfiles": {
            "BREAKOUT_RETEST": {
                "label": "BREAKOUT_RETEST",
                "trades": 18,
                "winRate": 68.0,
                "weight": 1.16,
                "confidenceAdjustment": 6.0,
            }
        },
        "sectorProfiles": {
            "BANK": {
                "label": "BANK",
                "trades": 20,
                "winRate": 61.0,
                "recentPnLPct": 12.0,
                "weight": 1.12,
                "confidenceAdjustment": 2.0,
            }
        },
        "thresholds": {
            "buyConfidence": 70.0,
            "watchConfidence": 60.0,
            "topPickConfidence": 70.0,
            "topPickRR": 2.0,
        },
    }

    result = TradeDecisionService.compute_trade_score(make_hit(sector="BANK"), adaptive_intelligence=adaptive)

    assert result["score"] > result["rankingComponents"]["baseScore"]
    assert result["rankingComponents"]["confidenceAdjustment"] > 0
    assert result["trustSignals"]["setupWinRate"] == 68.0
    assert result["trustSignals"]["sectorPerformancePct"] == 12.0
    assert "68% historical success rate" in result["trustSignals"]["trustMessage"]


def test_confidence_calibration_penalizes_recent_underperformance():
    adaptive = {
        "setupProfiles": {
            "BREAKOUT_RETEST": {
                "label": "BREAKOUT_RETEST",
                "trades": 12,
                "winRate": 38.0,
                "weight": 0.88,
                "confidenceAdjustment": -8.0,
            }
        },
        "sectorProfiles": {
            "BANK": {
                "label": "BANK",
                "trades": 12,
                "winRate": 41.0,
                "recentPnLPct": -6.0,
                "weight": 0.9,
                "confidenceAdjustment": -4.0,
            }
        },
        "thresholds": {
            "buyConfidence": 76.0,
            "watchConfidence": 64.0,
            "topPickConfidence": 76.0,
            "topPickRR": 2.2,
        },
    }

    result = TradeDecisionService.compute_trade_score(make_hit(sector="BANK"), adaptive_intelligence=adaptive)

    assert result["confidence"] < result["rankingComponents"]["baseConfidence"]
    assert result["adaptiveThresholds"]["buyConfidence"] == 76.0
    assert result["trustSignals"]["confidenceAdjustment"] < 0
    assert result["topPickEligible"] is False


def test_low_rr_setup_is_rejected_for_execution():
    result = TradeDecisionService.compute_trade_score(
        make_hit(
            summary={
                "nearest_support": 99.5,
                "nearest_resistance": 100.4,
                "target": 100.4,
            }
        )
    )

    assert result["action"] != "BUY"
    assert result["rr"] < TradeDecisionService.BUY_RR


def test_missing_support_returns_no_trade():
    result = TradeDecisionService.compute_trade_score(
        make_hit(summary={"nearest_support": None, "nearest_resistance": 112.0}, ohlcv=[])
    )

    assert result["action"] == "NO TRADE"
    assert result["nearestSupport"] is None


def test_annotate_many_enforces_trade_contract_fields():
    trade = TradeDecisionService.annotate_many([make_hit()])[0]

    for key in ("action", "confidence", "score", "entry", "stop_loss", "target", "rr", "explanation", "execution_plan"):
        assert key in trade

    assert trade["execution_plan"]["entry"] == trade["entry"]
    assert trade["execution_plan"]["stop_loss"] == trade["stop_loss"]
    assert trade["execution_plan"]["target"] == trade["target"]


def test_ranking_engine_sorts_and_limits_to_top_three(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    hits = [
        {
            "symbol": f"T{i}",
            "action": "BUY",
            "confidence": 80 + i,
            "score": 70 + i,
            "sectorState": "LEADING",
            "rr": 2.5,
            "executionPlan": {"riskRewardToT1": 2.5},
        }
        for i in range(5)
    ]

    top = TradeDecisionService.select_top_trades(hits, market_context={"lowConviction": False, "message": "ok"})

    assert [item["symbol"] for item in top] == ["T4", "T3", "T2"]
    assert len(top) == 3
    assert "Selected top trade #1" in caplog.text


def test_execution_plan_calculates_entry_stop_target_and_position_size():
    scored = TradeDecisionService.compute_trade_score(make_hit())
    plan = TradeDecisionService.build_plan(
        {**make_hit(), **scored},
        account_balance=50_000.0,
        risk_pct=0.02,
    )

    assert plan["entry"] == 112.0
    assert plan["stopLoss"] == 99.0
    assert plan["target1"] >= 125.0
    assert plan["positionSizeUnits"] == 76
    assert plan["capitalAtRisk"] == 1000.0


def test_fail_safe_returns_no_trade_when_calculation_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        TradeDecisionService,
        "_resolve_support_resistance",
        classmethod(lambda cls, hit, entry: (_ for _ in ()).throw(RuntimeError("boom"))),
    )

    result = TradeDecisionService.compute_trade_score(make_hit())

    assert result["action"] == "NO TRADE"
    assert result["explanation"] == "System unable to validate setup"
    assert result["trustSignals"]["performanceMultiplier"] == 1.0


def test_rejected_trade_is_logged(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)

    TradeDecisionService.compute_trade_score(
        make_hit(
            summary={"nearest_support": None, "nearest_resistance": None, "market_regime": "RANGE"},
            technical={"adx": 5.0, "isBreakout": False, "retest": False},
        )
    )

    assert "Trade rejected for TEST" in caplog.text
