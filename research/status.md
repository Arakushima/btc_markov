# Current status

Updated: 2026-10-03 (America/Chicago).

## Part A: implementation validated; freeze record follows

The predictive protocol is separated from development-only structural diagnostics.
Part A now contains two mature-label historical-frequency baselines, a smoothed
365-day rolling Markov forecaster, shared eligibility, Brier/log-loss/calibration,
paired stationary calendar-bootstrap intervals, the decision rule, and the
single-run evaluation gate. Part B residence times and Holm are not freeze
prerequisites. Core calculations remain inline in the main notebook.

Validation: all **101 synthetic project tests passed** (35 data/audit checks,
23 shared Part A feature/label/hitting checks, 14 prediction/scoring checks,
17 gate checks, and 12 Part B raw-MLE/CK checks). The 35 original mathematical
test bodies are unchanged and each retained once after splitting the test files.
All 40 main-notebook code cells executed top-to-bottom on development data only;
20 saved tables and two figures are present. The original 11 research functions
and 13 result tables are unchanged. Figure labels, intervals, and zero reference
were visually inspected; full HTML browser layout was not visually inspected.

BTC development replay (origins January 1–December 26, 2023; outcomes through
December 31): 360 calendar origins, 321 scored, 39 risk-origin exclusions.
Brier losses: Markov 0.253410, pooled 0.255005, direct-state 0.255398.
The primary baseline-minus-Markov difference is +0.001988; the paired 95%
interval is [-0.003013, +0.007037]. The interval includes zero: the result is
uncertain under the declared rule, not evidence of established improvement.
These are previously used development data. No specification was changed in
response to the replay. The CK diagnostic remains T=0.00082223, unadjusted
approximate p=0.8090; residence times and joint Holm remain pending.

The exact freeze commit and dry-check result will be recorded here immediately
after committing the manifest and its protected inputs. The committed manifest
protects the Part A function projection, protocol, config, gate, shared and
predictive/gate tests, requirements, and development reconciliation record.
Part B cells, tests, and prose may continue changing without altering that scope.

## Data boundary and scheduled evaluation

No real holdout prices have been read or evaluated. Data preparation remains:
137 verified development archives; all 4,160 matched closes agree with the
advisor's CSV. Some volume fields and six SOL opens differ, with cause unconfirmed.
96 holdout archives through August 31, 2026 remain sealed, with 974 consecutive
dates per asset in timestamp-only audits. September archives were unavailable
at the earlier download; their current availability has not been rechecked.

The October 7 gate locks a shared endpoint from fresh archive-availability,
checksum, and timestamp evidence only. If any September archive is unavailable,
use labels through August 31 and origins through August 26 for all assets,
and disclose the fallback. Otherwise use labels through September 30 and origins
through September 25. Corruption, gaps, or network uncertainty block evaluation.
The dated lock must be made on October 7 in America/Chicago; it cannot be
retroactively inferred. No automation or unattended evaluation is scheduled.

Next learning step: read notebook section 9, starting with the mature-label
pooled and current-state frequency baselines, then the smoothed rolling Markov
forecast; section 10 explains common scoring and uncertainty. Finish Part B
later using development data only. Frozen Part A cannot be tuned from Part B
findings or subsequent holdout outcomes. Start applications October 10 regardless
of results or completion. Graduation research remains the priority.

## Follow-up ideas recorded on October 2, 2026

The user suggested exploring noisy dynamical systems and stochastic differential equations (SDEs) later. This records an interest, not an implementation commitment, and adds no deliverables to the current job-search sprint.

- The current three-state Markov model is already stochastic. An SDE extension could consider continuous-time, continuous-state dynamics, such as dX_t = b(X_t) dt + a(X_t) dW_t. The financial interpretation of X_t and the coefficient forms have not been selected.
- One possible follow-up question is to start with simulated paths from a known SDE, discretize them, and examine when a Markov approximation is valid, how coarse-graining introduces memory, and how first-passage probabilities are affected. This is a candidate direction, not an established BTC model.
- Even if the full diffusion process is Markov, its aggregated discrete states need not be. First hitting along a continuous path and first arrival in a daily closing state in the current project are different events. Any future comparison must explicitly align observation times and event definitions.
- Keep the current main study and test-data isolation rules unchanged. If the current test results are later used to design a new model, that data period cannot serve as an unused test set for the new model.

Learning and discussion: Understand one module before implementing it. A question about the rationale for a design is not a request to change that design. State labels remain 0, 1, and 2. Project files are written in English; conversations with the user remain in Chinese.

Possible later reading:

- [Goodman, Lesson 5: SDE and PDE](https://math.nyu.edu/~goodman/teaching/StochCalc2018/notes/Lesson5.pdf): Diffusion processes, generators, and forward/backward equations.
- [Nartallo-Kaluarachchi, Coarse-graining Brownian dynamics](https://www.maths.ox.ac.uk/node/80941): Moving from SDE trajectories to discrete-state approximations, and the memory that coarse-graining may introduce. The methodological questions are relevant; this source does not establish that financial data follow a diffusion model.
