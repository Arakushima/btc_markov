# Independent QA of saved evaluation scores

Inspected the saved evaluation outputs only. No notebook, model, gate, or evaluate command was executed; no price archive was opened and no project file was modified. The independent calculations used Python standard-library `csv`, `datetime`, and `math`, not the research implementation.

Status is `completed`; completion is recorded as `2026-10-14T21:39:23.851555+00:00`. All three assets have the same 999 consecutive, unique forecast-origin dates, 2024-01-01 through 2026-09-25. Every saved label endpoint is exactly origin + 5 days and no later than 2026-09-30. The saved calendar decision has `fallback=false` and agrees with the status bounds.

## Recomputed score evidence

Brier loss was recomputed as `(q-y)^2`; log loss as `-y*log(q_clip)-(1-y)*log1p(-q_clip)` with the saved `log_clip=1e-12`. Only eligible origins with a binary saved target were scored. The table below is independently calculated from forecasts and labels.

| Asset | Model | n | Brier | Log loss | Event rate | Mean forecast |
|---|---|---:|---:|---:|---:|---:|
| BTCUSDT | markov | 871 | 0.252584176763 | 0.698357100241 | 0.469575200918 | 0.486653835822 |
| BTCUSDT | pooled | 871 | 0.251267620975 | 0.695737468126 | 0.469575200918 | 0.462335871503 |
| BTCUSDT | state | 871 | 0.252059868117 | 0.697403387042 | 0.469575200918 | 0.461392553147 |
| ETHUSDT | markov | 863 | 0.255352211862 | 0.703939702433 | 0.465816917729 | 0.503555279071 |
| ETHUSDT | pooled | 863 | 0.252577537142 | 0.698339351545 | 0.465816917729 | 0.476102867700 |
| ETHUSDT | state | 863 | 0.253330551081 | 0.699870957661 | 0.465816917729 | 0.476464430701 |
| SOLUSDT | markov | 862 | 0.255314985838 | 0.703862655132 | 0.468677494200 | 0.491377830101 |
| SOLUSDT | pooled | 862 | 0.254505256016 | 0.702302604008 | 0.468677494200 | 0.468027168338 |
| SOLUSDT | state | 862 | 0.254212856875 | 0.701807352833 | 0.468677494200 | 0.467446840280 |

All saved daily Brier/log-loss values and all summary n/score/event-rate/mean-forecast fields agree at absolute tolerance 1e-12. Maximum observed daily numerical difference: 5.55e-17; maximum summary numerical difference: 2.22e-16. The report contains the matching six-decimal score values.

## Calendar, common masks, and exclusions

| Asset | Calendar origins | Eligible = scored | Forecast excluded | Eligible but label unavailable | Positive targets | Reconstructed five-day labels |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 999 | 871 | 128 | 0 | 409 | 866 |
| ETHUSDT | 999 | 863 | 136 | 0 | 402 | 858 |
| SOLUSDT | 999 | 862 | 137 | 0 | 404 | 857 |

- Within each asset, all three models have precisely the same scored dates: every scored row has all six finite losses, and every excluded row has all six losses missing. Different assets need not have identical scored dates.
- Every forecast exclusion is `risk_origin`; the independently reconstructed reason counts match `exclusion_counts.csv`. There are no missing-label exclusions or threshold failures. The three coverage categories sum to 999 for each asset.
- Forecast and label origin states, saved targets in labels/daily losses, and the score-exclusion reasons agree row by row. Risk-origin labels are missing with `risk_origin` status; all non-risk labels are binary and `available`.
- Eligibility was also reconstructed from each saved origin state and sample count using the saved configuration thresholds. History starts equal origin minus 364 days; latest historical label ends equal their origin plus five days, never exceed the forecast origin, and their origin lies within the history window.
- Wherever the next five states are present in the saved forecast calendar, event labels were independently reconstructed by checking for state 0 among the next five rows, excluding the current state. All reconstructed labels agree.

## Scope and finding

73,431 row/field assertions were checked; 0 discrepancies were found. This is a consistency and arithmetic audit of saved artifacts, not a second model evaluation or an independent reconstruction from prices. The final five forecast origins need states from September 26–30, which are not saved as origin rows; their five-day endpoint/maturity metadata was checked, but their event content could not be independently reconstructed from these CSVs. Bootstrap intervals and frozen-source provenance are outside this score audit.
