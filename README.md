# Tests of Markovity in BTC Market States and Short-Term Risk Forecasting

Work in progress. The aim is to test a Markov approximation under a fixed three-state representation and evaluate five-day risk probability forecasts. Job applications begin on October 10, regardless of whether the project produces positive results.

- [Sprint schedule and scope](research/sprint_plan_2026_10.md)
- [Draft research protocol, not yet frozen](research/protocol_2026_holdout_draft.md)
- [Current status and next steps](research/status.md)
- [October 2 data reconciliation findings](research/data_audit_2026_10_02.md)
- [Rerunnable data audit notebook](notebooks/00_data_audit.ipynb)
- [Main research notebook: BTC states and first passage](notebooks/01_states_and_first_passage.ipynb) (real development data; 2023 matrices, first-passage probabilities, a CK diagnostic, and outcome labels; predictive evaluation pending)

Research questions: Are BTC's fixed discrete states compatible with selected testable implications of a homogeneous first-order Markov model? Under prespecified local estimation rules, can the Markov model's probability of first reaching the risk state within five days outperform direct historical frequency? Failure to reject does not prove Markovity; structural departures and predictive value are evaluated separately.

## Data separation

The original source is Binance's official spot `1d` files on `data.binance.vision`. The 2020–2023 period is development data that has already been used. The planned reserved test period is 2024-01-01 through 2026-09-30. Until the protocol and code are committed and frozen, only sealed downloads, file verification, row counts, and date-gap checks are permitted; prices must not be read, returns computed, or charts drawn.

The downloader processes only the development period by default. When the test period is explicitly selected, it saves only ZIP files that pass SHA-256 verification and reads each row's timestamp field to produce calendar-coverage records; it does not export a test-period price CSV. Sealing here is separation through the workflow, not access control that cannot be bypassed.

```sh
# List the plan only: no network access or file writes
python3 tools/download_binance.py --dry-run

# Download development-period data
python3 tools/download_binance.py --partition development

# Explicitly download and seal test-period data; check timestamp coverage only
python3 tools/download_binance.py --partition holdout

# Unit tests with synthetic data; no real market data accessed
python3 -m unittest discover -s tests -p 'test_download_binance.py' -v
```

New data are stored in `data/development/` and `data/holdout_sealed/`, with calendar records in `data/metadata/`; the entire `data/` directory is excluded from Git. Missing months, missing days, or verification failures are reported as incomplete. SOL's pre-listing absence must be distinguished from gaps after listing. Missing records before the first observed data are marked as requiring confirmation; the downloader does not infer a listing date on its own.

Binance documentation states that monthly archives are generally published on the first Monday of each month, so the September 2026 archives may not all be available until October 5. If they have not been published, complete the development-period work first and later obtain the missing monthly archives from the same source; do not silently shorten the test period. Spot timestamps changed to microseconds starting on 2025-01-01, so the downloader must verify the magnitude, the date boundary between units, and UTC day boundaries. [Official data documentation](https://github.com/binance/binance-public-data)

## Research workflow

Continue extending the existing main notebook: development closing prices → causal states → the fixed 2023 transition matrix → implied five-day first-passage probabilities → a five-step CK structural diagnostic → outcome-label preparation for later rolling forecasts. The current 2023 calculation is in-sample and uses raw transition frequencies. It is not a rolling forecast or evidence of predictive improvement. Section 7 separately compares direct five-day endpoint transitions with the fifth power of the one-day matrix. Its weighted discrepancy is calibrated using 1,999 fitted-chain simulations with full refitting. The development CK result is T = 0.00082223, with an approximate unadjusted p-value of 0.8090 (1,617 of 1,999 simulated discrepancies at least as large; zero invalid simulations). This check did not identify an unusually large discrepancy under the fitted null. The planned joint Holm conclusion awaits the residence-time diagnostic. Neither nonrejection nor rejection establishes predictive value.

Core functions are defined directly in the main notebook, beside the relevant equations and before their use on real data. This keeps the complete research explanation in one file for an interview. Artificial examples and independent path-enumeration checks remain in `tests/test_markov.py`, which loads those same notebook definitions without running data-loading cells. Section 8 retains five-day event labels, keeps incomplete outcomes missing, and records the full maturity date. Historical labels can enter a forecast at t only when their outcome end date is at or before t. The next module completes the residence-time structural diagnostic. Then return to historical-frequency baselines and smoothed rolling predictions. Earlier development observations supply estimation history for later development forecasts; 2023 remains previously used validation. The descriptive matrix estimated from all of 2023 must not be used to claim forecasts issued earlier in that year.

With the notebook dependencies installed, run from the project root:

```sh
python -m unittest discover -s tests -v
python -m jupyter nbconvert --execute --to notebook --inplace notebooks/01_states_and_first_passage.ipynb
python -m jupyter nbconvert --to html notebooks/01_states_and_first_passage.ipynb
```

## Reference work

The data download and reconciliation CLIs require only the Python standard library. The optional notebook environment uses `requirements-notebook.txt`; after installation, run `python tools/build_data_audit_notebook.py` to rebuild the executed notebook and HTML. The data audit notebook rereads development-period CSVs and reads only safe date-summary JSON for the test period. Development CSV filenames include explicit date ranges, so a single-month download does not overwrite the complete development file.

The previous implementation is available in the local [reference project](../../ChatGPT/bitcoin/btcdyn_research/README.md). Its 2023 BTC Markov Brier score was approximately 0.2495, versus approximately 0.2481 for historical frequency; these are previously used results, not results from the new test period. The old trading strategies, option signals, and Sharpe optimization are outside this project's main scope.
