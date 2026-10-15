# Saved holdout calibration and date-metadata QA

Assessment: Ready within the reviewed scope.

Scope: read-only reconstruction from the saved forecasts, labels, daily-loss flags, calibration, coverage and exclusion-count CSVs for BTCUSDT, ETHUSDT and SOLUSDT. Thresholds were read from the saved evaluation config. No raw archives or prices were opened; no notebook, gate, model fitting or evaluation was run.

Independent calculations used Python standard-library CSV/date/statistics operations, without calling project research helpers. Numerical comparison tolerance: 1e-12.

| Asset | Daily origins | Forecast eligible / scorable | Excluded | Empty calibration bins / 30 |
|---|---:|---:|---:|---:|
| BTCUSDT | 999 | 871 / 871 | 128 | 22 / 30 |
| ETHUSDT | 999 | 863 / 863 | 136 | 22 / 30 |
| SOLUSDT | 999 | 862 / 862 | 137 | 20 / 30 |

Checks performed:

- All forecast, label and loss calendars are unique, identical and consecutive: 999 origins, 2024-01-01 through 2026-09-25. All target end dates equal origin + 5 days and lie no later than 2026-09-30.
- Independently rebuilt all 10 fixed-width bins for each of the three models, using min(floor(10*q), 9) on the common scorable sample. All 90 stored bin rows reproduce counts, mean forecast and event rate. Empty bins retain n=0 and missing mean/event-rate values. Maximum absolute difference in nonempty-bin means: 1.11e-16.
- Reconstructed forecast eligibility and full reason combinations from state plus saved sample-size counts, then reproduced scorable flags, score-exclusion combinations, exclusion_counts.csv and coverage.csv. All excluded origins in these saved results are risk origins; label_unavailable among forecast-eligible origins is zero.
- All 2,997 history_start values equal origin - 364 days. Every saved latest historical label end is no later than its origin; it equals latest_label_origin + 5 days, and that historical origin stays within the declared rolling window.
- Eligibility obeys every saved threshold: at least 250 transition pairs; at least 20 source pairs in BOTH states 1 and 2; at least 100 matured non-risk labels; at least 20 matured labels in BOTH states 1 and 2. Total label counts equal the two state-specific counts. Excluded rows retain missing forecasts/losses; scorable rows have finite forecasts in [0,1] and finite losses.

Minimum saved sample-size metadata among forecast-eligible origins:

| Asset | Pairs | State 1 / 2 source pairs | Labels | State 1 / 2 labels |
|---|---:|---:|---:|---:|
| BTCUSDT | 364 | 253 / 39 | 306 | 251 / 38 |
| ETHUSDT | 364 | 250 / 45 | 300 | 248 / 45 |
| SOLUSDT | 364 | 235 / 50 | 304 | 232 / 49 |

Limit: this checks consistency of saved outputs and their date/sample-size metadata. It does not independently reconstruct every historical sample from raw state/price histories, validate outcome labels against underlying prices, or prove the absence of prior data exposure. Formal inference and loss/interval arithmetic are outside this bounded check.

No discrepancies found within the reviewed scope.
