# Independent QA of saved Part A evaluation intervals

Scope: read-only checks of records already saved under `results/holdout_evaluation`. No model, notebook, or gate was rerun; no raw market archive or price file was opened. This checks saved numerical and provenance consistency, not independent proof of prior non-access or every executed guard.

## Result

**PASS.** All nine paired contrasts agree with saved daily losses and bootstrap draws. The frozen BTC primary comparison is `markov_vs_state`; its recorded and independently reconstructed decision is **uncertain**. Its point estimate favors the direct-state baseline, but the interval includes zero, so the prespecified rule supports neither improvement nor worse performance. All nine intervals include zero. ETH/SOL remain descriptive secondary checks.

| Asset | Contrast | Baseline-minus-compared delta | 95% linear-percentile interval | Scored origins | Invalid draws | Decision |
|---|---|---:|---|---:|---:|---|
| BTCUSDT | markov_vs_state | -0.000524308646 | [-0.005621175118, +0.004704458129] | 871 | 0 | uncertain |
| BTCUSDT | markov_vs_pooled | -0.001316555788 | [-0.005850603433, +0.003154428210] | 871 | 0 | uncertain |
| BTCUSDT | state_vs_pooled | -0.000792247143 | [-0.002368691584, +0.000836382956] | 871 | 0 | uncertain |
| ETHUSDT | markov_vs_state | -0.002021660781 | [-0.007760082387, +0.002962600295] | 863 | 0 | uncertain |
| ETHUSDT | markov_vs_pooled | -0.002774674720 | [-0.008383447438, +0.001975211872] | 863 | 0 | uncertain |
| ETHUSDT | state_vs_pooled | -0.000753013939 | [-0.001775381753, +0.000204474879] | 863 | 0 | uncertain |
| SOLUSDT | markov_vs_state | -0.001102128963 | [-0.004906846390, +0.002606477161] | 862 | 0 | uncertain |
| SOLUSDT | markov_vs_pooled | -0.000809729822 | [-0.004273607054, +0.002390677766] | 862 | 0 | uncertain |
| SOLUSDT | state_vs_pooled | +0.000292399141 | [-0.001980228219, +0.002616670374] | 862 | 0 | uncertain |

## Checks performed

- Recomputed each delta as the mean of same-date saved Brier loss of the baseline minus the compared model. Verified the three loss columns share exactly the saved scorable mask and agree with summary Brier means and sample sizes.
- Verified each asset retains the complete 999-day forecast calendar, January 1, 2024 through September 25, 2026. Scored/excluded counts are BTC 871/128, ETH 863/136, SOL 862/137; every coverage table reports zero eligible-but-label-unavailable origins.
- Verified exactly 2,000 uniquely numbered bootstrap rows (0–1999), all three expected contrast columns, and zero missing/nonfinite draws for each contrast. Recomputed .025 and .975 quantiles using NumPy linear interpolation; checked saved interval bounds and invalid counts.
- Applied the frozen sign rule independently: lower endpoint strictly above zero supports improvement; upper endpoint strictly below zero supports worse performance; otherwise a valid interval is uncertain.
- Maximum absolute discrepancies: delta 0; CI endpoint 4.34e-18; summary Brier mean 0. All are below 1e-14.
- Verified every asset has all eight prespecified output CSV files plus exclusion_counts.csv. No output columns beyond those actually saved are assumed.

## Provenance checks

- Status is `completed`. Frozen commit: `af49df367c9792054b7a9cd8a90951dd1719d22c`; execution HEAD: `66df3bfb891ba3c76ab6d69905a291e0b5be5b16`.
- Freeze created: `2026-10-04T03:49:32.573770+00:00` (Chicago `2026-10-03T22:49:32.573770-05:00`).
- Calendar locked: `2026-10-08T01:44:39.672897+00:00` (Chicago `2026-10-07T20:44:39.672897-05:00`). This is the October 7 lock; it was not created on the evaluation day.
- Actual evaluation start: `2026-10-14T21:39:11.759339+00:00` (Chicago `2026-10-14T16:39:11.759339-05:00`). Completion: `2026-10-14T21:39:23.851555+00:00` (Chicago `2026-10-14T16:39:23.851555-05:00`). This was a delayed October 14 execution using the existing lock, not an October 7 evaluation.
- The copied calendar decision and freeze manifest byte hashes exactly match status.json. The decision references the same freeze manifest hash, frozen commit, and protected gate hash. The copied input list exactly equals the locked list: 236 unique asset-month archives.
- All three September availability records say verified/HTTP 200 and their archive hashes match the corresponding input-list entries. Fallback is false. The common label endpoint is September 30, 2026; the last origin is September 25. These checks compare saved receipts only; archive contents were not rehashed in this QA.
- Runtime versions match the copied freeze manifest for the required Python/NumPy/pandas versions: 3.12.14 / 2.3.5 / 2.2.3. Saved config specifies 2,000 draws, mean block 10 calendar days, seed 20261007, and 95% intervals.

## Interpretation and limits

- No numerical inconsistency or provenance mismatch was found within the checked saved records.
- Negative BTC Markov-versus-state delta is not evidence of improvement. Because its interval crosses zero, it is also insufficient for the frozen rule to conclude worse performance. Non-significance is not equivalence.
- These intervals condition on generated forecasts and use the prescribed calendar-block approximation; they do not refit models, correct specification search, establish Markovity, or make secondary assets independent replications.
- The stored bootstrap CSV contains contrast means, not resampled indices or per-draw scorable denominators. This QA validates its quantiles and availability, but cannot independently reconstruct the paired index generation solely from these saved outputs.
- This review did not independently reconstruct forecasts, labels, state features, or archive contents, and did not verify the Git ancestry against the live repository. Those remain matters of the recorded frozen gate and separate implementation/data checks.
