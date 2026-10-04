# October 2 Data Download and Development-Period Reconciliation

This round checked data provenance, dates, and field consistency; it did not perform model selection or evaluate the new test set. Development-period data use Binance's official monthly spot daily candlesticks, compared day by day with the mentor-provided `AFP_binance_spots.csv`. The new test period remains sealed. The September monthly archives have not yet been downloaded successfully, so the test-period data cannot be described as complete.

## Development data support the planned close-price model

| Asset | Date range | Days | Date keys versus mentor data | Exact close-price matches |
|---|---|---:|---|---:|
| BTCUSDT | 2020-01-01 through 2023-12-31 | 1,461 | Identical | 1,461 / 1,461 |
| ETHUSDT | 2020-01-01 through 2023-12-31 | 1,461 | Identical | 1,461 / 1,461 |
| SOLUSDT | 2020-08-11 through 2023-12-31 | 1,238 | Identical | 1,238 / 1,238 |

The comparison uses the original decimal values, without first converting to floating point and rounding. All 4,160 closing prices across the three assets match exactly, as do the high and low prices. The close-price series used by the planned model therefore remain unchanged over the common development period.

BTC/ETH opening prices match. SOL opening prices differ on 6 days, with a maximum absolute difference of 0.0104 USDT. Trading volume and quote-asset volume differ across all three assets, with some differences far exceeding decimal representation error; they cannot all be attributed to rounding noise. The maximum absolute daily trading-volume difference is approximately 3,200.89 BTC for BTC, 56,043.77 ETH for ETH, and 191,522.86 SOL for SOL. These numbers are differences between the two development datasets, not the trading volumes themselves or any model results.

The causes of the discrepancies have not been confirmed. This round does not modify the mentor data, combine fields from the two sources into a third dataset, or change tolerances to eliminate differences. Subsequent primary research will use closing prices from the official archives. The original protocol already constructs states solely from close-to-close returns, so this choice is not a feature selection decision made after observing the field discrepancies. Any future study of volume must separately explain and resolve these differences.

## SOL's pre-listing absence has a documented explanation

Binance's official announcement scheduled SOL/USDT trading to open at **2020-08-11 06:00 UTC**. The first archived date is consistent with that schedule. The absence of monthly archives for this pair from January through July 2020 and daily records for August 1–10 reflects the period before the pair was listed; these dates should not be filled with zeros or interpolated. August 11 is a partial trading day: retain its closing observation and document that fact. Full UTC trading days begin the following day. [Official announcement](https://www.binance.com/en/support/announcement/detail/cf77f566c9b64cc791fc152679175de8)

The downloader's raw log checks whether every month starting in January 2020 exists, so it returns `complete_requested_range=false`. The coverage audit preserves that original result and separately assesses continuity during the actual trading period using the official listing date. It does not alter the original log to disguise a failure as a success.

## Only calendar coverage was checked for the new test period

The BTC/ETH/SOL monthly archives from 2024-01 through 2026-08 have been downloaded and verified with SHA-256: 32 monthly archives per asset. The three requests for 2026-09 returned HTTP 404. The target end date remains 2026-09-30; the evaluation interval has not been shortened to fit the data already available.

Binance documentation states that monthly archives are provided on the first Monday of each month. On that basis, the September archives may be available on October 5; this is not a guarantee of the actual upload time. Under the sprint schedule, obtain the missing archives then and recheck timestamp coverage. [Official archive documentation](https://github.com/binance/binance-public-data)

The sealed-data check used only the timestamp bytes before the first comma in each record. It did not decode or export OHLC/volume, or compute returns, states, distributions, or scores for the new period. ZIP files remain in `data/holdout_sealed/`; `data/` is excluded from Git. Checksums establish that downloaded files match their declared digests; they do not establish that exchange records are completely error-free or that a model is valid.

Additional provenance note: while verifying the listing announcement, a search engine returned snippets from unrelated pages containing market-price text. Those pages were not opened, and that content was not used in model design or calculations. The claim here concerns separation of the test archives and research workflow, not that every participant has never encountered isolated market information from the new period.

## Evidence and reproduction

The reconciliation and coverage tools save field-level results, a limited sample of differences, source URLs, and archive digests. The code, result tables, and calendar audit are included in the first Git commit; raw data remain in an ignored directory. The first commit marks the start of version tracking for the project, not the freezing of the experimental protocol.

Commands to rerun development-period reconciliation, from the project root:

```sh
python3 tools/reconcile_development.py \
  --development-dir data/development \
  --mentor-csv /Users/zhangzhenyi/Documents/ChatGPT/bitcoin/CTA_public/AFP_binance_spots.csv \
  --output-dir results/data_audit

python3 tools/audit_download_coverage.py \
  --metadata-dir data/metadata \
  --output-dir results/data_audit
```

The key distinction to explain independently today: **complete dates, successful file verification, and agreement with another source are three different checks.** This round supports continuing the close-price research; the volume fields and the unpublished tail of the test period each retain explicit limitations.
