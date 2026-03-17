# S&R PRO – Filter Validation & Impact Measurement

## Scope
- Measurement-only phase (no core/filter logic modifications).
- Evaluation window: latest **100** archived completed signals.

## Key Metrics
- Total signals: **15**
- High Probability signals: **0**
- Medium + Low signals: **15**
- Unknown category signals (legacy pre-filter): **0**
- HIGH share of total signals: **0.0%**
- Baseline win rate: **13.33%**
- Prioritized win rate (HIGH+MEDIUM): **0.0%**
- Win-rate lift vs baseline: **-13.33 pp**
- Noise reduction if using High-only view: **100.0%**

## Win Rate by Filter Category
| Category | Signals | Wins | Win Rate | Avg Return |
|---|---:|---:|---:|---:|
| HIGH PROBABILITY | 0 | 0 | 0.0% | 0.0% |
| MEDIUM | 0 | 0 | 0.0% | 0.0% |
| LOW | 15 | 2 | 13.33% | -1.73% |
| UNKNOWN | 0 | 0 | 0.0% | 0.0% |

## Last 3–5 Session View
| Session Date | Total | High | Medium | Low | Win Rate |
|---|---:|---:|---:|---:|---:|
| 2026-02-27 | 1 | 0 | 0 | 1 | 0.0% |
| 2026-02-26 | 1 | 0 | 0 | 1 | 0.0% |
| 2026-02-25 | 6 | 0 | 0 | 6 | 16.67% |
| 2026-02-24 | 1 | 0 | 0 | 1 | 0.0% |
| 2026-02-23 | 1 | 0 | 0 | 1 | 100.0% |

## Success Criteria Check
- HIGH PROBABILITY win rate ≥ 65%: **FAIL**
- Prioritized win rate > baseline win rate: **FAIL**
- Clear separation (HIGH win rate > LOW win rate): **FAIL**
- HIGH category selectivity (20–30% target): **FAIL**

## Final Decision
- **REWORK**

## Insights
- Use category-level win-rate spread and counts together to avoid overfitting to small samples.
- UNKNOWN values shown here are legacy rows; inferred categories are applied for measurement-only re-validation.
- Review win-rate lift trend daily; sustained positive lift is required before any weight tuning.

## Next-Session Tracking Checklist
- Record total/high/medium/low counts.
- Record baseline and prioritized win rates.
- Track lift trend and category separation stability over 3–5 sessions.