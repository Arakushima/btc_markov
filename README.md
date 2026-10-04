# BTC Markov states and five-day risk forecasts

Can a rolling three-state Markov approximation improve the probability forecast
of a negative standardized daily shock within five days? BTC is primary;
ETH/SOL are identical-specification descriptive transfer checks. No trading or
Sharpe optimization is performed.

[Part A](research/protocol_part_a.md) fixes prediction and the single holdout
evaluation. [Part B](research/protocol_part_b.md) contains development-only CK,
residence-time, and joint Holm diagnostics. Part B may finish after Part A freezes
and cannot change its methods. See [current status](research/status.md) for the
actual freeze commit, validation, and next teaching step. Applications start
October 10 regardless of completion or outcome.

## Methods and current evidence

Define daily return divided by the strictly preceding 20-return sample standard
deviation, with states separated by fixed thresholds -1 and +1. For each
non-risk origin, use a 365-day rolling window and compare:

- Dirichlet-smoothed transition estimates and the killed-kernel probability
  `1 - Q^5 @ 1`.
- Beta-smoothed pooled historical event frequency.
- Beta-smoothed event frequency conditional on the current state.

Historical labels require all five days to mature. All models share the same
eligible origins. Brier loss is primary; log loss and calibration are secondary.
The primary comparison is BTC Markov versus direct-state frequency, with a
paired stationary calendar bootstrap (2,000 draws; mean block length 10 days).
Improvement requires a primary 95% interval wholly above zero for baseline loss
minus Markov loss.

**Development replay only — not untouched testing:** BTC origins January 1 to
December 26, 2023, with outcomes through December 31. There are 360 calendar
origins, 321 scored non-risk origins, and 39 risk-origin exclusions.

| Forecaster | Brier loss | Log loss |
|---|---:|---:|
| Markov | 0.253410 | 0.700223 |
| Pooled frequency | 0.255005 | 0.703592 |
| Direct-state frequency | 0.255398 | 0.704392 |

The primary Brier difference is +0.001988, with a 95% interval
[-0.003013, +0.007037]. This is uncertain under the declared rule; it does not
establish improvement. No parameters were changed in response to this replay.
The 2023 CK discrepancy is 0.00082223 with an approximate unadjusted p=0.8090;
residence times and the joint Holm conclusion remain pending. These checks do
not prove Markovity or determine predictive success.

## Reproduce and inspect

The [main notebook](notebooks/01_states_and_first_passage.ipynb) keeps all core
math inline. Section 9 implements rolling forecasts; section 10 scores them.
The [HTML reading copy](notebooks/01_states_and_first_passage.html) contains saved
development outputs. All 40 code cells executed; numerical tables and embedded
figures were checked. Full HTML browser layout was not visually inspected.

With `requirements-notebook.txt` installed, run from the repository root:

```sh
python -m unittest discover -s tests -v
python -m jupyter nbconvert --execute --to notebook --inplace notebooks/01_states_and_first_passage.ipynb
python -m jupyter nbconvert --to html notebooks/01_states_and_first_passage.ipynb
```

The notebook reads only the explicit 2020–2023 development CSV. Tests use
synthetic inputs and load tagged function definitions without executing data
loading or analysis cells. The gate similarly loads the frozen Part A functions;
its separate Python file handles hashes, dates, input ingestion, and audit records,
not forecasting mathematics.

## Data separation and the single evaluation

Source: Binance public spot monthly daily-bar archives on `data.binance.vision`.
2020–2023 has already been used for development. Across BTC/ETH/SOL, all 4,160
matched development closes agree with the advisor's CSV; some volume fields
and six SOL opens differ. See the [data audit](research/data_audit_2026_10_02.md).

The planned holdout ends September 30, 2026 (origins through September 25).
**Predeclared fallback:** if any September monthly archive is unavailable at the
October 7 check, all three assets end August 31 (origins through August 26), and
the report states this. Checksum errors and calendar gaps block the run; they do
not select a shorter period. Until the dated gate, only sealed downloads,
checksums, and timestamp-only checks are allowed. Git and the gate are an audit
trail, not independent proof that nobody inspected the data.

Development data live in `data/development/`; holdout ZIPs remain in
`data/holdout_sealed/`; all raw data are ignored by Git. Spot timestamps change
from milliseconds to microseconds at January 1, 2025. The downloader validates
units and dates. [Official archive documentation](https://github.com/binance/binance-public-data).

```sh
python tools/download_binance.py --dry-run
python tools/download_binance.py --partition development
python tools/download_binance.py --partition holdout
```

The committed freeze's exact hash is recorded in `research/status.md`. Replace
`FROZEN_COMMIT` below with that hash. Dry-check reads no market archives. The
calendar lock is allowed only on October 7, 2026 in America/Chicago; evaluation
may then run once. A missed lock must be documented as a deviation rather than
backdated. No unattended run is scheduled.

```sh
python tools/part_a_gate.py dry-check --frozen-commit FROZEN_COMMIT
# Only on the scheduled date; timestamp/checksum checks and September availability.
python tools/part_a_gate.py lock-calendar --frozen-commit FROZEN_COMMIT
# Single evaluation; retained failures and existing records forbid silent retries.
python tools/part_a_gate.py evaluate --frozen-commit FROZEN_COMMIT
```

The previous [reference project](../../ChatGPT/bitcoin/btcdyn_research/README.md)
used a different, frozen-at-2022 fitting rule and lacks this direct-state primary
baseline. Its already-viewed 2023 scores are not comparable holdout evidence for
this specification. Current design provenance is recorded in Part A.
