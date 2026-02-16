from app.main import _build_trade_signal, _resolve_summary_levels


def test_resolve_summary_levels_falls_back_to_mtf_when_primary_support_missing():
    cmp = 1437.10
    primary_supports = []
    primary_resistances = [{'price': 1440.23}]
    mtf = {
        'supports': [{'price': 1421.01}, {'price': 1300.47}],
        'resistances': [{'price': 1547.72}],
    }

    support, resistance = _resolve_summary_levels(cmp, primary_supports, primary_resistances, mtf)

    assert support == 1421.01
    assert resistance == 1440.23


def test_build_trade_signal_rules():
    assert _build_trade_signal('Bullish', 1.8)[0] == 'BUY'
    assert _build_trade_signal('Caution', 0.9)[0] == 'SELL'
    assert _build_trade_signal('Neutral', None)[0] == 'HOLD'
