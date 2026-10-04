# Project instructions

This project supports a math PhD's QR application. The application start date is
2026-10-10 regardless of research progress. Each session starts with one concise
Chinese update: completed work, current blocker, next step. Graduation research
takes priority; keep the project small enough to explain at a whiteboard.

Read `research/status.md`, `research/sprint_plan_2026_10.md`, and the current
protocol before continuing. Read the protocol index and both parts. Part A freeze status is recorded in status.md; Part B may remain in development after Part A freezes.

## Holdout boundary

- 2020–2023 has already been used for development, including 2023 results from
  the reference project. Never relabel 2023 as untouched testing.
- Until Part A and its evaluation code are frozen in a commit and the
  documented evaluation gate is satisfied, do not inspect or compute anything
  from prices dated 2024-01-01 through 2026-09-30.
- Before that gate, only archive download/checksums and timestamp-only row,
  duplicate and calendar-gap checks are permitted. No price previews, returns,
  distributions, state frequencies, plots, model fitting or scoring on holdout.
- Keep holdout archives separate in `data/holdout_sealed`. Do not load a combined
  development/holdout CSV and then filter after inspection. Reconciliation with
  the mentor CSV is limited to 2020–2023.
- Once frozen, evaluate the predeclared holdout procedure once and retain the
  complete record. Do not tune from its outcomes or delete failed run records.
  Necessary implementation corrections must be recorded honestly.

## Scope and interpretation

Main asset BTC, secondary identical-specification ETH/SOL. Part A: five-day first-passage probability prediction. Part B: Markov
structure diagnostics on development data only. Part B completion is not a
freeze or execution prerequisite for Part A.
Compare Markov, pooled frequency and direct current-state frequency. No trading
strategy, Sharpe optimization or extra model search in this sprint.

No rejection does not prove Markovity; rejection of a homogeneous approximation
does not by itself explain forecast failure. Git history is an audit trail, not
independent proof that nobody inspected data. State only milestones actually
completed. The reference project is `../../ChatGPT/bitcoin/btcdyn_research`.


## Language and collaboration

Write all project files in English, including documentation, code comments,
notebook explanations, output labels, and generated reading copies. Continue
user-facing conversation in Chinese. Preserve this convention in future work.
Teach one module at a time. The October 3 user instruction prioritizes implementing
and freezing all Part A methods now; resume step-by-step teaching afterwards. A question about a design choice is
not itself a request to change that choice; explain the rationale and retain
reasonable defaults unless the user asks for a change. State labels remain 0, 1, 2.

Keep core research calculations inside the main notebook, defined in the order
they are explained and used, so an interview walkthrough stays in one file.
Do not extract them into a separate Python module unless the user requests it.
Synthetic tests may remain separate and should exercise the notebook definitions.

## Independent freeze scopes

Part A core function cells are tagged part-a-functions in the main notebook.
After freezing, preserve that code projection and the gate-protected files exactly.
Part B cells and documentation may be edited using development data only.
Follow the predeclared September archive fallback in protocol_part_a.md; never
choose a shorter interval based on price values, scores, corruption, or gaps.
