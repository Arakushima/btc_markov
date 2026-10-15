# BTC Markov states and five-day risk forecasts

Does a rolling three-state Markov model improve forecasts of a negative
standardized daily shock within five days? **The frozen BTC holdout evaluation
did not establish improvement over direct current-state historical frequency.**
The Markov Brier loss was slightly higher; the paired 95% difference interval
crossed zero. This is a probability-forecasting study, with no trading strategy
or Sharpe optimization.

## Method

Compute simple close-to-close returns divided by the sample standard deviation
of the strictly preceding 20 returns (`ddof=1`), without subtracting a mean from
the current return. Fixed thresholds −1 and +1 define states 0, 1 and 2. From
state 1 or 2, predict whether any of the next five daily states equals 0. This
is a standardized one-day negative shock, not cumulative loss or an intraday
barrier event.

Each origin uses a 365-day rolling window and three prespecified forecasters:

- Markov: Dirichlet-smoothed transition counts, then `1 - Q^5 @ 1`, where `Q`
  retains the non-risk states without renormalizing.
- Pooled frequency: add-one-smoothed frequency of mature historical events.
- Direct-state frequency: the same frequency conditional on the current state.

Historical labels require all five subsequent states to be observed and mature
at the information date. All models share eligibility and scoring dates. Brier
loss is primary; log loss and ten-bin calibration are secondary. The primary
comparison is BTC Markov versus direct-state frequency. Its paired stationary
calendar bootstrap uses 2,000 draws and mean block length 10, retains excluded
calendar positions, and conditions on the generated forecasts without refitting.

## Single holdout evaluation

Part A was frozen at `af49df367c9792054b7a9cd8a90951dd1719d22c` on October 3,
2026 in America/Chicago. The October 7 calendar lock retained September 30 as
the label endpoint: all three September archives passed the availability,
checksum and timestamp checks, so the predeclared August fallback was not used.
The one-shot evaluation ran successfully on **October 14**, using the existing
lock; its actual date is recorded rather than backdated.

Forecast origins: **2024-01-01 through 2026-09-25**, with labels through
2026-09-30. Each asset has 999 calendar origins. BTC has 871 scored origins and
128 exclusions, all because the origin is already in risk state 0. Here `n` counts
scored forecast origins, not independent observations; the five-day labels overlap. ETH/SOL have
863/862 scored origins and 136/137 such exclusions. There are no eligible origins
with unavailable labels.

| Asset | Scored origins | Markov Brier | Pooled Brier | Direct-state Brier |
|---|---:|---:|---:|---:|
| **BTC — primary** | **871** | **0.252584** | **0.251268** | **0.252060** |
| ETH — descriptive | 863 | 0.255352 | 0.252578 | 0.253331 |
| SOL — descriptive | 862 | 0.255315 | 0.254505 | 0.254213 |

For BTC, `delta = Brier_direct_state - Brier_Markov` is **−0.000524**, with
95% interval **[−0.005621, +0.004704]**. The frozen decision is **uncertain**:
neither improvement nor worse performance is established by this interval.
This is not an equivalence result or proof that the states contain no information.
All nine prespecified comparisons are retained; their intervals cross zero.
ETH/SOL and the secondary BTC comparisons do not replace the primary decision.

The [full evaluation report](results/holdout_evaluation/report.md) includes log
loss, every contrast and coverage. Asset subdirectories retain daily forecasts,
labels, losses, calibration, comparisons and bootstrap draws.
[Run status](results/holdout_evaluation/status.json) records the environment,
timestamps and source identities. The complete record is preserved; no methods
were changed after seeing these results.

## Development diagnostics and limits

2020–2023 was already used for development, including 2023 results that influenced
design. The 365-day window is a declared practical choice, not a proven optimum;
the provenance does not establish that its original choice was independent of
earlier results. Daily rolling estimates may use earlier holdout observations as
they become available, but the algorithm and decision rule remain frozen.

[Part B](research/protocol_part_b.md) checks homogeneous first-order Markov
implications on development data only. For 2023, CK has raw/adjusted p-values
0.809/0.809; residence times have 0.328/0.656 after the joint two-test Holm
correction. Neither is rejected. The eight auxiliary annual/pooled checks also
do not reject after their separate correction; see [all structural results](results/part_b_development/diagnostics.csv).
Non-rejection does not prove Markovity, and these diagnostics do not determine
predictive success or permit changes to [frozen Part A](research/protocol_part_a.md).

Five-day labels overlap, rolling estimates share history, and dependence may
extend beyond the fixed average block length. The bootstrap interval is an
approximation conditional on forecasts, not a correction for model selection.
Any new specification motivated by these outcomes needs a separately declared
study; this holdout can no longer be called unused for that specification.

## Code, data and inspection

The [main notebook](notebooks/01_states_and_first_passage.ipynb) keeps all core
mathematics inline: states and first passage, CK, labels, rolling prediction,
scoring, residence times and Holm. Its [reading copy](notebooks/01_states_and_first_passage.html)
contains the saved development outputs. The new Chinese learning manual covers
all 52 code cells, data tools, the gate and tests:
[Markdown](docs/code_guide_zh.md), [offline HTML](docs/code_guide_zh.html),
[complete source reference](docs/code_reference.html).

Source: Binance public spot monthly one-day archives; see the
[official archive documentation](https://github.com/binance/binance-public-data).
Development CSVs live in `data/development/`; held-out ZIPs remain separately
stored in `data/holdout_sealed/`. Raw data are ignored by Git. Timestamps change
from milliseconds to microseconds in January 2025. All 4,160 matched development
closes agree exactly with the advisor's CSV; some volume fields and six SOL opens
differ, with the cause unresolved. See the [data audit](research/data_audit_2026_10_02.md).

The gate loads only tagged notebook function definitions, checks frozen source
and Python/NumPy/pandas versions, and creates an exclusive run record before
price decoding. Failed records are retained. Hashes, Git history and the gate
provide an audit trail, not independent proof that nobody inspected the data.

Historical validation: 125 synthetic tests passed and all 52 notebook code cells
executed on development data. The Chinese manual was prepared before the formal
run. Subsequent output verification checks saved predictions, scores and bootstrap
draws without rerunning the model; see [current status](research/status.md).

To prepare a local environment, use Python 3.12.14 and install the recorded
dependencies in a virtual environment. Run these commands from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebook.txt
python -m unittest discover -s tests -v
```

Raw data and the advisor's original file are not distributed. For a development-only
rerun, download the public 2020–2023 data first, then execute the main notebook:

```sh
python tools/download_binance.py --partition development --start 2020-01 --end 2023-12
python -m jupyter nbconvert --execute --to notebook --inplace notebooks/01_states_and_first_passage.ipynb
```

The historical advisor reconciliation is retained as an audit record; reproducing
that separate comparison requires the original advisor file.

Use the freeze-matching environment for the read-only gate check:

```sh
python tools/part_a_gate.py dry-check --frozen-commit af49df367c9792054b7a9cd8a90951dd1719d22c
```

The formal evaluation has already completed. Inspect its saved outputs; do not
delete its directory or rerun `evaluate`. The prior local reference project
(`btcdyn_research`, not distributed here) used a different fitting rule, so its
already-viewed 2023 results are not comparable holdout evidence for this specification.
