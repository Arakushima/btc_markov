# Current status

Updated: 2026-10-03.

Data preparation completed on October 2: All 137 monthly development archives have been downloaded and verified. Across the three assets, all 4,160 daily closing prices exactly match the advisor's data, and the dates match as well. Some base-asset and quote-asset volumes, along with six SOL opening prices, differ; the cause has not been confirmed. The original files are retained, and the main study continues to use only the closing prices specified in the design. See `data_audit_2026_10_02.md` for the full account.

Test period: 96 monthly archives have been sealed. Each asset has 974 days from 2024-01-01 through 2026-08-31, and the dates checked so far are consecutive. The three monthly archives for 2026-09 returned 404. The target end date remains 2026-09-30, so the test period is not yet complete. Only timestamps in the sealed archives have been parsed; prices have not been decoded, states have not been fitted, and scores have not been computed.

Verification: All 35 offline tests for downloading, reconciliation, and calendar auditing passed. Version history is maintained in the initialized local Git repository; see `git log` for the first commit. That commit is not the protocol freeze commit. Raw data and caches are excluded from Git.

Still incomplete: The residence-time diagnostic specification and implementation, the joint Holm decision, predictive baselines and rolling scoring, protocol freezing, and the gate for the single evaluation run. The protocol remains DRAFT. The September archives will be added after their scheduled release; the missing month will not be used as a reason to unseal the test data early or shorten the test period.

Learning and implementation: The main notebook, `notebooks/01_states_and_first_passage.ipynb`, now includes the CK diagnostic before the separate prediction workflow. All 26 code cells executed. Sections 1–6 retain the descriptive 2023 matrix and model-implied probabilities. Section 7 estimates direct five-step endpoint transitions, compares them with the fifth power of the one-step estimate, and calibrates the declared weighted squared discrepancy using 1,999 homogeneous-chain simulations (seed 20261004), fixing the observed initial state and refitting on every path. The draft protocol records the scalar statistic, complete-path and sparse-row rules. Observed CK T = 0.00082223; 1,617 of 1,999 simulations had T at least as large, with zero invalid simulations. The approximate unadjusted p-value is 0.8090. This diagnostic did not identify an unusually large discrepancy under the fitted null, but it does not prove Markovity or predictive usefulness. The joint Holm conclusion is pending the residence-time diagnostic. Section 8 retains the event labels and maturity filter. All ten previous result tables are unchanged. All 35 research-math tests and all 70 project tests passed. HTML table contents were checked; the simulation-distribution figure was visually inspected for readable labels, units, and the observed-statistic marker. Full browser layout is not visually verified. The protocol remains DRAFT, and no holdout prices were read.

Next: Read section 7 in order: direct five-step counts, the discrepancy T, then its fitted-null simulation. Complete the residence-time statistic, boundary rules, simulation checks, and joint Holm comparison next. After the structural module, return to section 8 and implement the two historical-frequency baselines, smoothed rolling forecasts, and scoring. At each forecast date t, fit from the preceding 365-day window including t and use only outcomes fully matured by t; score using the later five-day outcome. The full-year 2023 descriptive matrix is not used to claim earlier forecasts. Both 2020–2022 and 2023 remain development data.

Fixed deadline: Start submitting applications on October 10. Graduation research takes priority. Unfavorable or incomplete project results will not delay applications.


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
