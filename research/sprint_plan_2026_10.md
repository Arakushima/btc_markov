# Project sprint before applications begin on October 10

Start submitting applications on October 10; the project may be described as work in progress. Graduation research takes priority. Spend approximately 1.5 hours per day on the project rather than extending work indefinitely to obtain favorable results. At the start of each session, report what has been completed today, what is blocked, and what comes next.

## Required minimum version

One clear research question, a protocol frozen in a commit, isolated data, a notebook that runs from start to finish, two structural diagnostics covering residence times and Chapman–Kolmogorov (CK) consistency, a Brier-score/calibration comparison of three predictors, and a one-page README that reports the results honestly. BTC is the primary experiment. ETH and SOL use exactly the same specification as secondary transfer checks. If time is short, complete BTC first; do not replace an unfavorable primary result with another asset.

Spectral features are appendix diagnostics only. Trading strategies, Sharpe optimization, options, HMMs, Koopman methods, new-feature searches, and semi-Markov extensions are outside the scope of this deadline.

## Planned deliverables by date

| Date | Deliverable for review |
|---|---|
| October 1 | Define the scope; review download entry points; prepare isolated downloads and checksum verification; draft the protocol |
| October 2 | Download development data; reconcile daily dates and prices for 2020–2023 against the advisor's CSV; only seal test data and check its calendar; initialize Git and make the first commit |
| October 3 | Use simulated chains to validate first-passage probabilities, CK, and residence-run boundary handling; explain the three predictors; do not inspect new prices |
| October 4 | Complete the protocol, scoring code, and key tests; freeze them in a commit and record the commit and file hashes; do not unseal the test set if any prerequisites remain incomplete |
| October 5 | Add any September monthly archives whose release was delayed; complete the development-period run and figures |
| October 6 | Review development results and prepare a three-minute introduction; hold the first mock interview; record fixes to implementation errors before unsealing rather than silently replacing the protocol |
| October 7 | Once all prerequisites are met, evaluate 2024–2026-09 once using the frozen workflow; save every prespecified comparison together, without selecting assets or months |
| October 8 | Check whether the evidence supports the conclusions; explain bias and uncertainty without tuning to test performance |
| October 9 | Complete the README's one-page research report, reproduction commands, and necessary figures; organize and publish the code; hold the second mock interview |
| October 10 | Describe the actual progress and results honestly on the resume and begin applications |

If time is short, reduce appendix work and secondary assets; do not bypass the protocol-freeze or data-completeness conditions. If the new-data evaluation is not completed in time, present the development results and state that evaluation on the new sample is pending. The application date does not change. Planned dates do not automatically launch tasks; work resumes when the user returns.

## Four corrections to the research framing

1. CK consistency and geometric residence times are necessary implications, but passing these checks does not prove first-order Markov behavior. Rejection of a homogeneous approximation may reflect time variation, omitted states, or history dependence; these possibilities must be distinguished.
2. Separate structural tests from predictive evaluation. Structural mismatch does not automatically establish predictive failure, and failure to outperform a baseline does not prove that the states contain no information.
3. Compare unconditional event frequency, direct five-day event frequency grouped by the current state, and Markov first-passage probabilities. Comparing the first two isolates state information; comparing the latter two examines whether the multistep model adds value.
4. Git commits, data hashes, and execution logs provide a traceable record; they cannot alone prove that a researcher never looked at the test data. The project will honestly describe the isolation procedures actually followed and any deviations.

## Learning and interview rhythm

After each module, the user first explains in their own words what it computes, why it is computed that way, and when it can fail. If this cannot be explained clearly, pause to work through the explanation instead of adding more functionality. Mock interviews begin with an unscripted three-minute presentation, followed by questions from the interviewer; specific questions are not shown in advance. This project does not replace applications, probability practice, or graduation work.

Immigration status, OPT, and employer requirements are not verified as part of this technical plan. Following the user's plan, confirm them separately with the school's DSO/OISS and individual employers.
