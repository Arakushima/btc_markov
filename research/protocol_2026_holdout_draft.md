# Draft Protocol for a BTC Markov Approximation and Five-Day Risk Forecasting

Status: **DRAFT, not yet frozen. This document does not authorize reading test-period prices or evaluating the new sample.** This is a new research proposal. The previous 2023 results informed its design, so it cannot be presented as a proposal made before those results were seen. The target is to complete and commit the protocol and code by 2026-10-04, then schedule a single evaluation on the new sample.

## Research Questions and Data Boundaries

Structural question: Is the fixed three-state sequence compatible with the CK and residence-time implications of a homogeneous first-order Markov model? Predictive question: Can a prespecified local Markov estimator provide additional predictive value for the first negative shock within five days? Report these questions separately. Do not call failure to reject a proof, or treat structural rejection itself as the cause of predictive failure.

BTCUSDT is the primary asset; ETHUSDT/SOLUSDT are secondary checks under the same specification. The data source is fixed as the Binance public spot 1d archives. Development data end on 2023-12-31. Forecast origins for the new evaluation run from 2024-01-01 through 2026-09-25, and every label must have fully matured by 2026-09-30. Daily bars are labeled by the UTC calendar date of their open time. The information time for a forecast is after that daily bar has completed.

Before freezing, new ZIP archives may be downloaded and sealed, their SHA-256 checksums verified, and only their timestamps parsed to check row counts and gaps. Test-period price previews, return statistics, state frequencies, correlations, charts, and any model scores are prohibited. Reconciliation with the advisor's data is restricted to 2020–2023. If this test interval has already been used in other work, record what actually happened; do not continue to claim that it has been entirely unused in development.

## Proposed Fixed States and Target

Retain the definition from the previous experiment without searching over thresholds: divide the simple daily return r_t by the sample standard deviation sigma_t of the strictly preceding 20 returns (ddof=1). Set z_t=r_t/sigma_t, without subtracting a mean. The thresholds are fixed at −1 and +1; there are no quantiles to estimate from the test set. The state is unavailable when inputs are missing or volatility is zero.

State 0: z_t<=−1; state 1: −1<z_t<1; state 2: z_t>=1. Use the term "negative shock," not "crash," because one historical standard deviation does not imply a rare catastrophe.

Only forecast from states 1 and 2. Define tau_t=min{k>=1:S_(t+k)=0} and y_t=1{tau_t<=5}. This is a standardized single-day shock within the next five daily closes, not a cumulative loss, maximum drawdown, or intraday price touch. Require the full five-day label to mature even if a hit occurs earlier; do not include end-of-sample windows merely because a hit has already been observed.

## Proposed Three Probability Forecasters

The proposed primary analysis uses a **365-day rolling window with daily causal re-estimation**. What is frozen is the algorithmic specification below, not all parameter estimates permanently fixed at the end of 2023. At each test-period time t, use only information observed by that time. Earlier test-period observations may enter later estimates under the prespecified rules, but they may not be used to reselect models or parameters.

Within the window [t−364,t]:

1. Markov: Count only adjacent, complete state pairs, with both endpoints inside the window. Add Dirichlet(1,1,1) pseudocounts to each row. After obtaining P_t, remove the risk state to obtain Q_t and forecast q_t=1−e_(S_t)'Q_t^5 1. Require at least 250 pairs and at least 20 pairs originating from each non-risk state.
2. Unconditional historical frequency: Use only historical labels whose origins are non-risk states within the window and whose full five-day outcomes have matured by the close at t. Estimate (hits+1)/(labels+2), requiring at least 100 labels.
3. Direct state frequency: Use the same window and maturity rule, grouping historical labels whose origin state matches the current state. Estimate (hits within the group+1)/(labels within the group+2), requiring at least 20 labels in each non-risk group.

Score all three models on exactly the same eligible forecast origins. Report the shared exclusion reasons and calendar coverage. For Q_t^5, hold the current rolling parameter estimates constant over the five future steps. This is an approximation, not a guarantee that the future market mechanism remains unchanged. The main changes from the previous experiment are the addition of the direct state baseline and the decision to continue updating estimates after 2023. Record these reasons before viewing the new sample.

## Proposed Structural Diagnostics

Conduct the primary diagnostic first within the already-used fixed window from 2023-01-01 through 2023-12-31, assuming one fixed P within that window. Estimate the matrix using all valid adjacent pairs in the window. Do not conflate this diagnostic with the rolling P_t used for forecasting as if they formed one globally homogeneous chain. If auxiliary windows from 2020–2022 are needed, list them in the final protocol rather than selecting them after inspecting plots.

- CK (specified on October 3 before running this implementation): Use the fixed 2023 window, requiring all daily states to be observed. Estimate raw P_hat_1 from all 364 adjacent pairs and raw P_hat_5 from all 360 overlapping five-day endpoint pairs, with both endpoints inside the window. Let n_i^(5) be the number of five-step pairs starting at i. Use the single scalar T = sum_i [n_i^(5) / sum_r n_r^(5)] * sum_j [P_hat_5(i,j) - (P_hat_1^5)(i,j)]^2. Larger T means greater discrepancy. This weights rows by observed source frequency, placing less weight on rare states; it does not use Pearson expected-cell denominators. No threshold or statistic is selected from the resulting p-value. Being in state 0 at step five and reaching it at any point within five days remain distinct events.
- CK sparse-path rules: A missing date/state makes this complete-path diagnostic unavailable; do not bridge or interpolate it. Every one-step source row must have at least one pair so that raw P_hat_1 is defined. A five-step source row with zero pairs is displayed as undefined and contributes zero weight by explicit exclusion, not by multiplying NaN by zero. Apply exactly the same statistic and rules to each simulated path, including refitting both matrices and its own row weights. If any of the 1,999 simulations has an unobserved one-step source row, record the invalid count and withhold the p-value; do not discard, replace, or repeatedly simulate such paths. This conservative availability rule becomes more likely to withhold a result as the number of simulations increases. This is a development-stage specification on previously seen data, not independent preregistration.
- Residence times: Define a complete run from entry into a state. The treatment of runs truncated at the beginning or end, the statistic, and the minimum number of runs must be identical for observed and simulated chains. A homogeneous chain implies Pr(L_i>=ell)=P_ii^(ell−1), but the empirical distribution after removing truncated runs cannot be claimed to be an unbiased estimate of the population residence-time distribution.
- Null calibration: Simulate paths of the same length from the fitted homogeneous chain, fixing the observed initial state. For every simulation, refit the matrix, extract runs again, and recompute the same statistic. The proposal is to use 1,999 parametric bootstrap simulations with seed=20261004 and p=(1+number of simulated statistics at least as large as the observed statistic)/2000. Apply Holm correction to the two formal tests at significance level 0.05 once both p-values are available. Until the residence-time diagnostic is implemented, label the CK p-value unadjusted and do not issue the planned joint testing conclusion. This is an approximate composite-null test, not a finite-sample exact test.
- Spectral features: At most, report the second-largest eigenvalue modulus in an appendix. Do not assume reversibility or directly equate 1−|lambda_2| with the finite-time mixing speed of a general nonreversible chain.

**Still required before freezing:** The residence-time statistic, ell range, treatment of the beginning and end, and sparse-run rule; implementation of the same residence-time rules in simulated resamples; and the joint Holm decision once both diagnostics are available. This file must not be relabeled FROZEN until these details are complete and the simulation examples have passed their tests.

## Proposed New-Sample Scoring

The primary comparison is BTC Markov versus direct state frequency. Also report the difference versus unconditional frequency and the difference between direct state frequency and unconditional frequency. The primary score is the mean Brier loss, Brier=(q−y)^2, for which lower is better. Secondary outputs are log loss with probabilities clipped to [1e−12,1−1e−12], the event rate, the mean forecast, and a calibration table using ten fixed equal-width probability bins. ETH/SOL results are descriptive transfer checks, not substitutes for the primary BTC comparison.

Define the difference as baseline loss minus Markov loss, so positive values favor Markov. For the primary difference, use a paired stationary calendar-block bootstrap with mean block length 10 days, 2,000 resamples, and seed=20261007, reporting a 95% percentile interval. Preserve missing positions for ineligible dates and use the same resampled indices for all forecasters within each resample. This interval is conditional on the forecast paths already produced; it does not re-estimate models. Longer dependence induced by rolling windows is a limitation. Do not treat 10-day blocks as a universally sufficient theoretical guarantee. Report that this evaluation supports improvement only if the lower bound of the primary interval is greater than zero. If the interval crosses zero, report uncertainty, not equivalence or proof of no information.

Produce the prespecified primary comparison once for the full 2024–2026-09 period; do not select winners by year, asset, or a particular score. Label any post-hoc exploration separately as exploratory, and do not subsequently call this interval a new test set.

## Conditions for Freezing and a Single Evaluation

Before unsealing prices, commit the complete protocol, parameter configuration, scoring code, simulation tests, and development-data reconciliation records. Record the commit, input-archive SHA-256 checksums, and runtime environment. The evaluation script must check the working tree against the frozen version, refuse to reuse an existing evaluation record, and save all prespecified outputs, the code version, and input summaries together in one run. Implementation errors must remain in the log with corrections appended; do not delete earlier outputs and call a rerun the first evaluation. This evaluation gate has not yet been implemented.

Git history and sealed directories provide an audit trail, not independent proof that the data were never inspected. This research may be described as "frozen" or as having completed "one out-of-sample evaluation" only after the corresponding steps have actually been completed. The October 10 application does not depend on whether this stage is completed in time.

## Methodological References

- [Prinz et al. 2011, Markov models of molecular kinetics](https://www.bcp.fu-berlin.de/en/chemie/chemie/forschung/PhysTheoChem/agkeller/_Docs/Publications_pdf/Prinz2011.pdf): Model estimation and validation. The methods are borrowed here; their applicability to financial states still requires testing.
- [Shalizi, Inference for Markov Chains](https://stat.cmu.edu/~cshalizi/dst/18/lectures/22/lecture-22.html): Markov inference and parametric bootstrap.
- [Wolfer and Kontorovich 2019](https://arxiv.org/abs/1902.01224): Mixing-time estimation for general ergodic chains and issues of nonreversibility.
