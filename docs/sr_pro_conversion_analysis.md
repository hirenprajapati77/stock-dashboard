# S&R PRO – Conversion Optimization (Performance Analysis Phase)

## Data Sources Used
- `/api/v1/signal-performance` response snapshot: `success`
- `backend/app/data/signal_performance_daily.json`: 1 day(s) available
- `backend/app/data/screener_fallback.json`: 22 current signals used for segmentation

## Core Daily Metrics
- Average Early Setups per day: **0.00**
- Average Entry Ready signals per day: **2.00**
- Average Strong Entry signals per day: **0.00**
- Conversion Early → Entry Ready: **0.00%**
- Conversion Entry Ready → Strong Entry: **0.00%**

> Note: Only one daily record is currently available and Early Setups are zero, so Early→Entry conversion is directional only (not statistically robust).

## Segment Analysis — Sector
| Segment | Signals | Entry Ready | Strong Entry | Entry→Strong Conv% | Win Rate%* | Resolved |
|---|---:|---:|---:|---:|---:|---:|
| PHARMA | 7 | 0 | 0 | 0.00 | 33.33 | 6 |
| ENERGY | 7 | 1 | 0 | 0.00 | 0.00 | 2 |
| IT | 5 | 0 | 0 | 0.00 | 0.00 | 5 |
| FMCG | 3 | 1 | 0 | 0.00 | 0.00 | 2 |

## Segment Analysis — Volume Strength (WEAK / MODERATE / STRONG)
| Segment | Signals | Entry Ready | Strong Entry | Entry→Strong Conv% | Win Rate%* | Resolved |
|---|---:|---:|---:|---:|---:|---:|
| MODERATE | 17 | 1 | 0 | 0.00 | 16.67 | 12 |
| STRONG | 5 | 1 | 0 | 0.00 | 0.00 | 3 |

## Segment Analysis — Momentum Type (1D / 2D / 3D)
| Segment | Signals | Entry Ready | Strong Entry | Entry→Strong Conv% | Win Rate%* | Resolved |
|---|---:|---:|---:|---:|---:|---:|
| 1D | 18 | 1 | 0 | 0.00 | 18.18 | 11 |
| 2D | 4 | 1 | 0 | 0.00 | 0.00 | 4 |

## Structured Insights
- **No sector currently shows positive Entry Ready → Strong Entry conversion** (all are 0.00% because there are no Strong Entry signals in snapshot).
- **Volume conversion is currently flat (0.00%) across buckets**, but realized win rate is higher in **MODERATE (16.67%)** vs **STRONG (0.00%)** on available outcomes.
- **Momentum conversion is also flat (0.00%)**, while realized win rate is better for **1D momentum (18.18%)** versus **2D momentum (0.00%)** in current data.
- Strong Entry tags are sparse overall (0 in current snapshot), indicating the system is currently conservative on escalation.
- For the next filtering phase, prioritize segments with both better conversion tendency and meaningful sample sizes (avoid tiny buckets).

*Win Rate uses `forward3dReturn > 0` where outcomes are available in snapshot rows.*