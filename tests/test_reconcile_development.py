"""Offline fixtures only; no Quant directory or live data access."""
import contextlib
import csv
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "reconcile_development.py"
SPEC = importlib.util.spec_from_file_location("tested_development_reconciler", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def values(day="2020-01-01", **changes):
    row = {"date": day, "open": "100", "high": "110", "low": "90", "close": "101",
           "volume": "12.50000000", "quote_volume": "1250.5", "taker_buy_quote": "650.25"}
    row.update(changes)
    return row


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # Normalize OS aliases such as /var -> /private/var before path checks.
        self.root = Path(self.temporary.name).resolve()
        self.development = self.root / "data" / "development"
        self.development.mkdir(parents=True)
        self.mentor = self.root / "mentor.csv"
        self.output = self.root / "results" / "data_audit"

    def fixtures(self, development=None, mentor=None):
        development = development or {symbol: [values()] for symbol in audit.SYMBOLS}
        mentor = mentor or {symbol: [values()] for symbol in audit.SYMBOLS}
        for symbol in audit.SYMBOLS:
            path = self.development / f"{symbol}_1d_2020-01_2023-12.csv"
            with path.open("w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["date", *audit.FIELDS])
                writer.writeheader()
                writer.writerows(development[symbol])
        with self.mentor.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["inst", "asof", *audit.FIELDS.values()])
            writer.writeheader()
            for symbol in audit.SYMBOLS:
                for row in mentor[symbol]:
                    writer.writerow({"inst": symbol, "asof": row["date"],
                                     **{target: row[source] for source, target in audit.FIELDS.items()}})
        return audit.AuditConfig(self.development, self.mentor, self.output)

    def test_exact_decimal_equality_field_mapping_and_input_hash(self):
        development = {symbol: [values(close="101.000", volume="12.500")] for symbol in audit.SYMBOLS}
        config = self.fixtures(development=development)
        before = self.mentor.read_bytes()
        code, report, differences = audit.reconcile(config)
        self.assertEqual(code, 0)
        self.assertEqual(differences, [])
        self.assertEqual(report["inputs"]["mentor"]["sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(report["assets"]["BTCUSDT"]["fields"]["quote_volume"]["exact_matches"], 1)
        self.assertEqual(self.mentor.read_bytes(), before)
        self.assertFalse(self.output.exists())

    def test_date_alignment_uses_keys_not_row_positions(self):
        rows = [values("2020-01-01", close="100"), values("2020-01-02", close="200")]
        development = {s: list(reversed(rows)) for s in audit.SYMBOLS}
        mentor = {s: rows for s in audit.SYMBOLS}
        config = self.fixtures(development, mentor)
        self.assertEqual(audit.reconcile(config)[0], 0)
        shifted = {s: [values("2020-01-02", close="100"), values("2020-01-03", close="200")] for s in audit.SYMBOLS}
        config = self.fixtures(shifted, mentor)
        code, report, _ = audit.reconcile(config)
        self.assertEqual(code, 1)
        btc = report["assets"]["BTCUSDT"]
        self.assertEqual(btc["common_dates"], 1)
        self.assertEqual(btc["fields"]["close"]["exact_mismatches"], 1)
        self.assertEqual(btc["missing_from_development"], ["2020-01-01"])
        self.assertEqual(btc["missing_from_mentor"], ["2020-01-03"])

    def test_duplicate_keys_are_reported_and_never_arbitrarily_chosen(self):
        duplicate = [values(), values(close="999")]
        config = self.fixtures(development={s: duplicate for s in audit.SYMBOLS})
        code, report, sample = audit.reconcile(config)
        self.assertEqual(code, 1)
        btc = report["assets"]["BTCUSDT"]
        self.assertEqual(btc["coverage"]["development"]["duplicates"][0]["count"], 2)
        self.assertEqual(btc["compared_unique_dates"], 0)
        self.assertEqual(btc["common_dates_excluded_due_to_duplicates"], ["2020-01-01"])
        self.assertTrue(any(row["kind"] == "duplicate_key_development" for row in sample))

    def test_future_development_or_mentor_date_rejected_before_any_numeric_conversion(self):
        for source in ("development", "mentor"):
            with self.subTest(source=source):
                rows = {s: [values(close="not-a-price")] for s in audit.SYMBOLS}
                future = {s: [values("2024-01-01", close="NEVER_PARSE_ME")] for s in audit.SYMBOLS}
                config = self.fixtures(future if source == "development" else rows,
                                       future if source == "mentor" else rows)
                with mock.patch.object(audit, "parse_decimal", side_effect=AssertionError("Prices must remain unconverted")):
                    with self.assertRaisesRegex(audit.InputRejected, "future_date_rejected"):
                        audit.reconcile(config)
                self.assertFalse(self.output.exists())

    def test_decimal_precision_and_within_tolerance_still_reported(self):
        left = "123456789012345678901234567890.00000000000000000001"
        right = "123456789012345678901234567890.00000000000000000000"
        development = {s: [values(close=left)] for s in audit.SYMBOLS}
        mentor = {s: [values(close=right)] for s in audit.SYMBOLS}
        config = self.fixtures(development, mentor)
        code, report, sample = audit.reconcile(config)
        self.assertEqual(code, 1)
        close = report["assets"]["BTCUSDT"]["fields"]["close"]
        self.assertEqual(close["exact_mismatches"], 1)
        self.assertEqual(close["outside_fixed_tolerance"], 0)
        self.assertEqual(Decimal(close["maximum_absolute_difference"]), Decimal("0.00000000000000000001"))
        self.assertTrue(sample[0]["within_tolerance"])
        # The aggregate must not silently round to Decimal's default 28 digits.
        fraction = "0.123456789012345678901234567890123456789"
        config = self.fixtures({s: [values(close="100" + fraction[1:])] for s in audit.SYMBOLS},
                               {s: [values(close="100")] for s in audit.SYMBOLS})
        _, report, _ = audit.reconcile(config)
        self.assertEqual(Decimal(report["assets"]["BTCUSDT"]["fields"]["close"]["sum_absolute_difference"]), Decimal(fraction))

    def test_internal_gaps_and_sol_unique_history_separate_from_listing_claims(self):
        full = [values("2020-08-11"), values("2020-08-12"), values("2020-08-13")]
        development = {s: full for s in audit.SYMBOLS}
        mentor = {s: full for s in audit.SYMBOLS}
        mentor["SOLUSDT"] = full[1:]
        development["BTCUSDT"] = [full[0], full[2]]
        code, report, _ = audit.reconcile(self.fixtures(development, mentor))
        self.assertEqual(code, 1)
        self.assertEqual(report["assets"]["BTCUSDT"]["coverage"]["development"]["gaps_within_observed_span"], ["2020-08-12"])
        sol = report["assets"]["SOLUSDT"]
        self.assertTrue(sol["summary"]["close_exact_on_compared_common_dates"])
        self.assertEqual(sol["missing_from_mentor"], ["2020-08-11"])
        self.assertEqual(sol["coverage"]["development"]["gaps_within_observed_span"], [])
        self.assertNotIn("listing_date", sol)

    def test_limited_difference_export_reports_truncation_without_changing_sources(self):
        development = {s: [values(close="102", volume="99")] for s in audit.SYMBOLS}
        base = self.fixtures(development=development)
        config = audit.AuditConfig(base.development_dir, base.mentor_csv, base.output_dir, 2)
        before = {p: p.read_bytes() for p in [self.mentor, *audit.input_paths(config).values()]}
        code, report, sample = audit.reconcile(config)
        self.assertEqual(code, 1)
        self.assertEqual(len(sample), 2)
        self.assertEqual(report["difference_records_total"], 6)
        self.assertTrue(report["difference_sample_truncated"])
        report_path, differences_path = audit.write_report(config, report, sample)
        with differences_path.open() as file:
            self.assertEqual(len(list(csv.DictReader(file))), 2)
        self.assertEqual(json.loads(report_path.read_text())["difference_records_saved"], 2)
        for path, payload in before.items():
            self.assertEqual(path.read_bytes(), payload)

    def test_no_latest_file_discovery_and_holdout_path_rejected(self):
        config = self.fixtures()
        exact = self.development / "BTCUSDT_1d_2020-01_2023-12.csv"
        latest = self.development / "BTCUSDT_1d_2020-01_2026-09.csv"
        exact.rename(latest)
        with self.assertRaisesRegex(audit.InputRejected, "required_input_file_missing"):
            audit.reconcile(config)
        with self.assertRaisesRegex(audit.InputRejected, "holdout_path_rejected"):
            audit.checked_path(self.root / "data" / "holdout_sealed" / "some.csv")

    def test_late_large_differences_remain_visible_after_csv_sample_is_full(self):
        days = ["2020-01-01", "2020-01-02", "2020-01-03"]
        development = {s: [values(day) for day in days] for s in audit.SYMBOLS}
        mentor = {s: [values(day) for day in days] for s in audit.SYMBOLS}
        development["BTCUSDT"][0]["close"] = "101.000000001"
        development["ETHUSDT"][2]["volume"] = "99"
        development["SOLUSDT"][0]["open"] = "100.01"
        development["SOLUSDT"][2]["open"] = "150"
        base = self.fixtures(development, mentor)
        config = audit.AuditConfig(base.development_dir, base.mentor_csv, base.output_dir, 1)
        code, report, sample = audit.reconcile(config)
        self.assertEqual(code, 1)
        self.assertEqual(len(sample), 1)
        self.assertEqual(sample[0]["asset"], "BTCUSDT")
        self.assertEqual(report["difference_records_total"], 4)
        self.assertTrue(report["difference_sample_truncated"])
        self.assertEqual(report["assets"]["SOLUSDT"]["fields"]["open"]["largest_difference"],
                         {"date": "2020-01-03", "development_value": "150", "mentor_value": "100", "absolute_difference": "50"})
        self.assertEqual(report["assets"]["ETHUSDT"]["fields"]["volume"]["largest_difference"]["absolute_difference"], "86.50000000")
        self.assertIsNone(report["assets"]["BTCUSDT"]["fields"]["open"]["largest_difference"])

    def test_input_and_output_symlinks_rejected(self):
        config = self.fixtures()
        alias = self.root / "mentor_alias.csv"
        alias.symlink_to(self.mentor)
        unsafe = audit.AuditConfig(config.development_dir, alias, config.output_dir)
        with self.assertRaisesRegex(audit.InputRejected, "symlink_path_rejected"):
            audit.reconcile(unsafe)
        destination = self.root / "actual_results"
        destination.mkdir()
        self.output.parent.mkdir(parents=True)
        self.output.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(audit.InputRejected, "symlink_path_rejected"):
            audit.reconcile(config)

    def test_cli_emits_clear_input_rejection_and_no_output_for_future_data(self):
        config = self.fixtures(development={s: [values("2025-01-01")] for s in audit.SYMBOLS})
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = audit.main(["--development-dir", str(config.development_dir), "--mentor-csv", str(config.mentor_csv),
                               "--output-dir", str(config.output_dir)])
        self.assertEqual(code, 2)
        self.assertIn("future_date_rejected", output.getvalue())
        self.assertFalse(config.output_dir.exists())


if __name__ == "__main__":
    unittest.main()
