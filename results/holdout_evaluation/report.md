# Part A prediction evaluation

Primary asset: BTCUSDT. ETHUSDT and SOLUSDT are descriptive secondary checks.

Frozen commit: `af49df367c9792054b7a9cd8a90951dd1719d22c`.
Calendar decision: 2026-10-08T01:44:39.672897+00:00 (October 7 in America/Chicago).
Forecast origins: 2024-01-01 through 2026-09-25; complete labels through 2026-09-30.

All three September archives passed fresh availability, checksum and timestamp checks. The full prespecified September endpoint was retained.

## Primary BTC decision

Comparison: Markov versus direct current-state historical frequency. Positive Brier loss difference favors Markov.
Recorded decision: **uncertain**. Brier difference: -0.0005243086455897541; 95% interval: [-0.005621175117573444, 0.004704458129279632].

The paired calendar-block interval conditions on the generated forecast paths and does not refit models. It does not correct model selection, establish Markovity, or make the secondary assets independent replications. An interval crossing zero indicates uncertainty, not equivalence.

## BTCUSDT

All three prespecified forecasters:

```text
          n     brier  log_loss  event_rate  mean_forecast
model                                                     
markov  871  0.252584  0.698357    0.469575       0.486654
pooled  871  0.251268  0.695737    0.469575       0.462336
state   871  0.252060  0.697403    0.469575       0.461393
```

All prespecified paired comparisons:

```text
                  delta_brier  ci_lower  ci_upper    n  invalid_resamples   decision
comparison                                                                          
markov_vs_state     -0.000524 -0.005621  0.004704  871                  0  uncertain
markov_vs_pooled    -0.001317 -0.005851  0.003154  871                  0  uncertain
state_vs_pooled     -0.000792 -0.002369  0.000836  871                  0  uncertain
```

Coverage:

```text
 calendar_origins  forecast_eligible  scorable  forecast_excluded  label_unavailable
              999                871       871                128                  0
```

Full daily forecasts, labels, losses, calibration, bootstrap draws and exclusion-reason counts are retained in `BTCUSDT/`.

## ETHUSDT

All three prespecified forecasters:

```text
          n     brier  log_loss  event_rate  mean_forecast
model                                                     
markov  863  0.255352  0.703940    0.465817       0.503555
pooled  863  0.252578  0.698339    0.465817       0.476103
state   863  0.253331  0.699871    0.465817       0.476464
```

All prespecified paired comparisons:

```text
                  delta_brier  ci_lower  ci_upper    n  invalid_resamples   decision
comparison                                                                          
markov_vs_state     -0.002022 -0.007760  0.002963  863                  0  uncertain
markov_vs_pooled    -0.002775 -0.008383  0.001975  863                  0  uncertain
state_vs_pooled     -0.000753 -0.001775  0.000204  863                  0  uncertain
```

Coverage:

```text
 calendar_origins  forecast_eligible  scorable  forecast_excluded  label_unavailable
              999                863       863                136                  0
```

Full daily forecasts, labels, losses, calibration, bootstrap draws and exclusion-reason counts are retained in `ETHUSDT/`.

## SOLUSDT

All three prespecified forecasters:

```text
          n     brier  log_loss  event_rate  mean_forecast
model                                                     
markov  862  0.255315  0.703863    0.468677       0.491378
pooled  862  0.254505  0.702303    0.468677       0.468027
state   862  0.254213  0.701807    0.468677       0.467447
```

All prespecified paired comparisons:

```text
                  delta_brier  ci_lower  ci_upper    n  invalid_resamples   decision
comparison                                                                          
markov_vs_state     -0.001102 -0.004907  0.002606  862                  0  uncertain
markov_vs_pooled    -0.000810 -0.004274  0.002391  862                  0  uncertain
state_vs_pooled      0.000292 -0.001980  0.002617  862                  0  uncertain
```

Coverage:

```text
 calendar_origins  forecast_eligible  scorable  forecast_excluded  label_unavailable
              999                862       862                137                  0
```

Full daily forecasts, labels, losses, calibration, bootstrap draws and exclusion-reason counts are retained in `SOLUSDT/`.
