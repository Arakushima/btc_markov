# Current status

Updated: 2026-10-14 (America/Chicago).

## Part A: FROZEN; single holdout evaluation completed

The predictive protocol is separated from development-only structural diagnostics.
Part A now contains two mature-label historical-frequency baselines, a smoothed
365-day rolling Markov forecaster, shared eligibility, Brier/log-loss/calibration,
paired stationary calendar-bootstrap intervals, the decision rule, and the
single-run evaluation gate. Part B residence times and Holm are not freeze
prerequisites. Core calculations remain inline in the main notebook.

Validation: all **125 synthetic project tests passed** after Part B completion.
The Part A gate dry-check remains valid. All 52 main-notebook code cells
executed top-to-bottom on development data only, with 4 embedded figures.
The frozen Part A function projection and protected files are unchanged; its
saved forecast, scoring, comparison, and calibration tables match the prior run.
Part B figures were visually inspected. Full HTML browser layout was not
visually inspected; the HTML reading copy was regenerated from saved outputs.

BTC development replay (origins January 1–December 26, 2023; outcomes through
December 31): 360 calendar origins, 321 scored, 39 risk-origin exclusions.
Brier losses: Markov 0.253410, pooled 0.255005, direct-state 0.255398.
The primary baseline-minus-Markov difference is +0.001988; the paired 95%
interval is [-0.003013, +0.007037]. The interval includes zero: the result is
uncertain under the declared rule, not evidence of established improvement.
These are previously used development data. No specification was changed in
response to the replay. Part B now adds residence times and joint Holm decisions; see its completed record below.

Frozen commit: **`af49df367c9792054b7a9cd8a90951dd1719d22c`** (October 3, America/Chicago).
The frozen gate dry-check passed without opening market archives or prices.
This is the Part A freeze; Part B has now been completed on development data only. The single holdout evaluation completed on October 14 using the existing October 7 calendar lock. The committed manifest
protects the Part A function projection, protocol, config, gate, shared and
predictive/gate tests, requirements, and development reconciliation record.
Part B cells, tests, and prose may continue changing without altering that scope.

## Calendar decision and completed evaluation

The October 7 calendar lock was recorded at 2026-10-08T01:44:39.672897+00:00
(October 7 in America/Chicago). All three September archives passed fresh
availability, checksum and timestamp checks. `label_end=2026-09-30`,
`origin_start=2024-01-01`, `origin_end=2026-09-25`, `fallback=false`.
The decision and original attempt record remain in their respective result folders.

At the user's explicit request on October 14, a comprehensive Chinese code manual
was completed and saved before evaluation. Its preparation manifest and the run
invocation record preserve that ordering. The frozen source/environment dry-check
passed. `evaluate` was then invoked exactly once and exited successfully.
`results/holdout_evaluation/status.json` records start 2026-10-14T21:39:11.759339+00:00
and completion 2026-10-14T21:39:23.851555+00:00. The delayed run used the already
locked calendar; no dates, methods, protected files or environment requirements
were changed, and no calendar check was backdated.

All 236 input archives matched the lock. BTC/ETH/SOL each have 999 calendar
origins and respectively 871/863/862 scored origins. The other 128/136/137
origins are excluded because their current state is 0; no eligible labels are
unavailable. All eight prespecified tables and exclusion-reason counts are
saved for each asset, with the full report and provenance records.

| Asset | Markov Brier | Pooled Brier | Direct-state Brier |
|---|---:|---:|---:|
| BTC (primary) | 0.252584 | 0.251268 | 0.252060 |
| ETH (descriptive) | 0.255352 | 0.252578 | 0.253331 |
| SOL (descriptive) | 0.255315 | 0.254505 | 0.254213 |

Primary BTC baseline-minus-Markov Brier difference: **-0.0005243086**;
paired 95% interval **[-0.0056211751, +0.0047044581]**. Decision: **uncertain**.
The point estimate favors direct-state frequency, but the interval establishes
neither superiority nor inferiority under the frozen rule. All nine reported
contrast intervals cross zero, with no invalid bootstrap draws. No result was
used to change the method or to substitute a secondary asset for BTC.

Independent post-run checks recompute scores from saved forecasts and labels,
verify coverage and calibration, and reproduce interval quantiles from the saved
bootstrap draws. They do not refit models or run another holdout evaluation.
The detailed validation and invocation evidence are retained under
`results/part_a_evaluation_validation/`.

Data preparation provenance remains unchanged: 137 development archives, all
4,160 matched closes agreeing with the advisor CSV, and unresolved differences
in some volume fields and six SOL opens. Earlier download/audit reports remain
historical snapshots. The formal run includes the three September archives
verified at locking. The directory name `holdout_sealed` is retained for source
traceability; after the completed evaluation the period is no longer unused.

## Part B: completed development diagnostics (October 4)

The October 4 user requested running Part B first, then resuming step-by-step
learning. All core mathematics remains inline; new sections 11–12 preserve the
existing section order. Fixed the residence statistic, boundary rules, minimum
counts, simulation rules, annual/pooled windows, and separate Holm families
before the new real-data calculations. Local pre-run records document this
order and implementation corrections; these are not independent preregistration.

| 2023 diagnostic | Discrepancy | Raw approximate p | Holm-adjusted p |
|---|---:|---:|---:|
| CK | 0.00082223 | 0.8090 | 0.8090 |
| Residence | 0.00056047 | 0.3280 | 0.6560 |

Neither primary implication is rejected at the declared 0.05 level. This is non-rejection, not evidence that the process is proven Markov. None of the eight auxiliary diagnostics rejects after their separate Holm adjustment.

Saved all ten diagnostic rows and the simulated statistics, run counts, boundary
audit, survival curves, and manifest in `results/part_b_development/`. See
`research/protocol_part_b.md` for exact methods and limitations. The geometric
curve is a model reference: excluding boundary runs favors short runs, an effect
repeated in every simulation. The exploratory family covers 2020, 2021, 2022,
and the pooled 2020–2023 window; it is separate from the primary two-test family.
No result changes Part A or substitutes for predictive evaluation.

Next learning step: use `docs/code_guide_zh.md` or its offline HTML reading copy.
The prior conversation reached residence simulation; resume at In[47]–In[52]
(curves, Holm and auxiliary windows), then connect the completed holdout result
to the Part A comparison rule. The manual covers all 52 main cells, the five
audit cells, every utility script, the configuration/gate, and test responsibilities,
with a complete source reference. Its original pre-evaluation version is preserved.

The October 10 application-start deadline has passed; this project now has a
completed result that can be stated honestly. Actual application status is not
inferred here. Graduation research remains the priority. The October 14 evaluation
was user-directed; no unattended or repeat evaluation occurred.

## Follow-up ideas recorded on October 2, 2026

The user suggested exploring noisy dynamical systems and stochastic differential equations (SDEs) later. This records an interest, not an implementation commitment, and adds no deliverables to the current job-search sprint.

- The current three-state Markov model is already stochastic. An SDE extension could consider continuous-time, continuous-state dynamics, such as dX_t = b(X_t) dt + a(X_t) dW_t. The financial interpretation of X_t and the coefficient forms have not been selected.
- One possible follow-up question is to start with simulated paths from a known SDE, discretize them, and examine when a Markov approximation is valid, how coarse-graining introduces memory, and how first-passage probabilities are affected. This is a candidate direction, not an established BTC model.
- Even if the full diffusion process is Markov, its aggregated discrete states need not be. First hitting along a continuous path and first arrival in a daily closing state in the current project are different events. Any future comparison must explicitly align observation times and event definitions.
- Keep the current main study and test-data isolation rules unchanged. If the current test results are later used to design a new model, that data period cannot serve as an unused test set for the new model.

Learning and discussion: Understand one module before implementing it. A question about the rationale for a design is not a request to change that design. State labels remain 0, 1, and 2. Project research files are written in English; conversations remain Chinese. The user explicitly requested a Chinese learning manual on October 14; that manual is the documented language exception.

Possible later reading:

- [Goodman, Lesson 5: SDE and PDE](https://math.nyu.edu/~goodman/teaching/StochCalc2018/notes/Lesson5.pdf): Diffusion processes, generators, and forward/backward equations.
- [Nartallo-Kaluarachchi, Coarse-graining Brownian dynamics](https://www.maths.ox.ac.uk/node/80941): Moving from SDE trajectories to discrete-state approximations, and the memory that coarse-graining may introduce. The methodological questions are relevant; this source does not establish that financial data follow a diffusion model.
