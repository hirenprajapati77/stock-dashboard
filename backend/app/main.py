from __future__ import annotations

from importlib import import_module

_root_main = import_module("main")

app = _root_main.app
_build_trade_signal = _root_main._build_trade_signal
_resolve_summary_levels = _root_main._resolve_summary_levels
