#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import sys

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = ROOT / "backend" / "app" / "data" / "signal_archive.json"
OUT_REPORT = ROOT / "docs" / "sr_pro_filter_validation_report.md"
OUT_DAILY = ROOT / "backend" / "app" / "data" / "filter_validation_daily.json"
WINDOW = 100

sys.path.append(str((Path(__file__).resolve().parents[1] / "backend")))
from app.services.signal_filter_service import SignalFilterService


def _safe_load_json(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def _pct(num: float, den: float) -> float:
    return round((num / den) * 100, 2) if den else 0.0


def main() -> None:
    archive = _safe_load_json(ARCHIVE_PATH, [])
    if not isinstance(archive, list):
        archive = []

    signals = archive[:WINDOW]

    # Measurement-only enrichment: infer category using current filter logic when missing
    # (does not change filter logic/scoring; only enables post-rework assessment on legacy rows).
    enriched_signals = []
    for s in signals:
        row = dict(s)
        cat = str(row.get("filterCategory") or "").upper()
        if cat not in {"HIGH PROBABILITY", "MEDIUM", "LOW"}:
            meta = SignalFilterService.compute_filter_meta(row)
            row["inferredFilterCategory"] = meta.filterCategory
            row["inferredFilterScore"] = meta.filterScore
            row["inferredPriorityBoost"] = meta.priorityBoost
        enriched_signals.append(row)

    signals = enriched_signals

    totals = len(signals)
    wins = sum(1 for s in signals if (s.get("forward3dReturn") or 0) > 0)
    baseline_win_rate = _pct(wins, totals)

    categories = {
        "HIGH PROBABILITY": [],
        "MEDIUM": [],
        "LOW": [],
        "UNKNOWN": [],
    }

    for s in signals:
        cat = str(s.get("filterCategory") or "").upper()
        if cat not in {"HIGH PROBABILITY", "MEDIUM", "LOW"}:
            cat = str(s.get("inferredFilterCategory") or "UNKNOWN").upper()
        if cat not in categories:
            cat = "UNKNOWN"
        categories[cat].append(s)

    cat_rows = []
    for cat, rows in categories.items():
        total = len(rows)
        cat_wins = sum(1 for r in rows if (r.get("forward3dReturn") or 0) > 0)
        wr = _pct(cat_wins, total)
        avg_ret = round(mean([(r.get("forward3dReturn") or 0) for r in rows]), 2) if total else 0.0
        cat_rows.append((cat, total, cat_wins, wr, avg_ret))

    high_med = categories["HIGH PROBABILITY"] + categories["MEDIUM"]
    hm_total = len(high_med)
    hm_wins = sum(1 for r in high_med if (r.get("forward3dReturn") or 0) > 0)
    prioritized_win_rate = _pct(hm_wins, hm_total)
    win_rate_lift = round(prioritized_win_rate - baseline_win_rate, 2)

    high_total = len(categories["HIGH PROBABILITY"])
    med_low_total = len(categories["MEDIUM"]) + len(categories["LOW"])
    unknown_total = len(categories["UNKNOWN"])

    noise_reduction_pct = _pct(max(totals - high_total, 0), totals)
    high_share_pct = _pct(high_total, totals)


    # Daily session view (last 5 hitAsOf dates)
    by_day = defaultdict(list)
    for s in signals:
        day = str(s.get("hitAsOf") or "UNKNOWN").split(" ")[0]
        by_day[day].append(s)

    day_rows = []
    for day in sorted(by_day.keys(), reverse=True)[:5]:
        rows = by_day[day]
        d_total = len(rows)
        def _row_cat(r):
            c = str(r.get("filterCategory") or "").upper()
            if c in {"HIGH PROBABILITY", "MEDIUM", "LOW"}:
                return c
            return str(r.get("inferredFilterCategory") or "UNKNOWN").upper()

        d_high = sum(1 for r in rows if _row_cat(r) == "HIGH PROBABILITY")
        d_med = sum(1 for r in rows if _row_cat(r) == "MEDIUM")
        d_low = sum(1 for r in rows if _row_cat(r) == "LOW")
        d_wins = sum(1 for r in rows if (r.get("forward3dReturn") or 0) > 0)
        d_wr = _pct(d_wins, d_total)
        day_rows.append((day, d_total, d_high, d_med, d_low, d_wr))

    # Success criteria
    high_wr = next((r[3] for r in cat_rows if r[0] == "HIGH PROBABILITY"), 0.0)
    low_wr = next((r[3] for r in cat_rows if r[0] == "LOW"), 0.0)
    criteria = {
        "high_win_rate_ge_65": high_wr >= 65,
        "prioritized_gt_baseline": prioritized_win_rate > baseline_win_rate,
        "high_vs_low_separation": high_wr > low_wr,
        "high_selective_20_30pct": 20 <= high_share_pct <= 30,
    }

    if all([criteria["high_win_rate_ge_65"], criteria["prioritized_gt_baseline"], criteria["high_vs_low_separation"]]):
        final_decision = "LOCK"
    elif criteria["prioritized_gt_baseline"] or criteria["high_vs_low_separation"]:
        final_decision = "TUNE"
    else:
        final_decision = "REWORK"

    snapshot = {
        "window": WINDOW,
        "totalSignals": totals,
        "highProbabilitySignals": high_total,
        "mediumLowSignals": med_low_total,
        "unknownSignals": unknown_total,
        "baselineWinRate": baseline_win_rate,
        "prioritizedWinRate": prioritized_win_rate,
        "winRateLiftVsBaseline": win_rate_lift,
        "noiseReductionIfHighOnlyPct": noise_reduction_pct,
        "highSharePct": high_share_pct,
        "finalDecision": final_decision,
        "categoryMetrics": [
            {
                "category": c,
                "count": cnt,
                "wins": w,
                "winRate": wr,
                "avgReturn": avg,
            }
            for c, cnt, w, wr, avg in cat_rows
        ],
        "dailyRows": [
            {
                "date": d,
                "totalSignals": t,
                "high": h,
                "medium": m,
                "low": l,
                "winRate": wr,
            }
            for d, t, h, m, l, wr in day_rows
        ],
        "successCriteria": criteria,
    }

    existing_daily = _safe_load_json(OUT_DAILY, {})
    if not isinstance(existing_daily, dict):
        existing_daily = {}
    latest_day = day_rows[0][0] if day_rows else "NO_DATA"
    existing_daily[latest_day] = snapshot
    OUT_DAILY.parent.mkdir(parents=True, exist_ok=True)
    OUT_DAILY.write_text(json.dumps(existing_daily, indent=2), encoding="utf-8")

    lines = []
    lines.append("# S&R PRO – Filter Validation & Impact Measurement")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Measurement-only phase (no core/filter logic modifications).")
    lines.append(f"- Evaluation window: latest **{WINDOW}** archived completed signals.")
    lines.append("")
    lines.append("## Key Metrics")
    lines.append(f"- Total signals: **{totals}**")
    lines.append(f"- High Probability signals: **{high_total}**")
    lines.append(f"- Medium + Low signals: **{med_low_total}**")
    lines.append(f"- Unknown category signals (legacy pre-filter): **{unknown_total}**")
    lines.append(f"- HIGH share of total signals: **{high_share_pct}%**")
    lines.append(f"- Baseline win rate: **{baseline_win_rate}%**")
    lines.append(f"- Prioritized win rate (HIGH+MEDIUM): **{prioritized_win_rate}%**")
    lines.append(f"- Win-rate lift vs baseline: **{win_rate_lift} pp**")
    lines.append(f"- Noise reduction if using High-only view: **{noise_reduction_pct}%**")
    lines.append("")

    lines.append("## Win Rate by Filter Category")
    lines.append("| Category | Signals | Wins | Win Rate | Avg Return |")
    lines.append("|---|---:|---:|---:|---:|")
    for cat, cnt, w, wr, avg in cat_rows:
        lines.append(f"| {cat} | {cnt} | {w} | {wr}% | {avg}% |")
    lines.append("")

    lines.append("## Last 3–5 Session View")
    lines.append("| Session Date | Total | High | Medium | Low | Win Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for d, t, h, m, l, wr in day_rows:
        lines.append(f"| {d} | {t} | {h} | {m} | {l} | {wr}% |")
    lines.append("")

    lines.append("## Success Criteria Check")
    lines.append(f"- HIGH PROBABILITY win rate ≥ 65%: **{'PASS' if criteria['high_win_rate_ge_65'] else 'FAIL'}**")
    lines.append(f"- Prioritized win rate > baseline win rate: **{'PASS' if criteria['prioritized_gt_baseline'] else 'FAIL'}**")
    lines.append(f"- Clear separation (HIGH win rate > LOW win rate): **{'PASS' if criteria['high_vs_low_separation'] else 'FAIL'}**")
    lines.append(f"- HIGH category selectivity (20–30% target): **{'PASS' if criteria['high_selective_20_30pct'] else 'FAIL'}**")
    lines.append("")

    lines.append("## Final Decision")
    lines.append(f"- **{final_decision}**")
    lines.append("")

    lines.append("## Insights")
    if totals == 0:
        lines.append("- No completed archived signals available yet; continue collecting 3–5 sessions.")
    else:
        lines.append("- Use category-level win-rate spread and counts together to avoid overfitting to small samples.")
        lines.append("- UNKNOWN values shown here are legacy rows; inferred categories are applied for measurement-only re-validation.")
        lines.append("- Review win-rate lift trend daily; sustained positive lift is required before any weight tuning.")

    lines.append("")
    lines.append("## Next-Session Tracking Checklist")
    lines.append("- Record total/high/medium/low counts.")
    lines.append("- Record baseline and prioritized win rates.")
    lines.append("- Track lift trend and category separation stability over 3–5 sessions.")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT_REPORT}")
    print(f"wrote {OUT_DAILY}")


if __name__ == "__main__":
    main()
