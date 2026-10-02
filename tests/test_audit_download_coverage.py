"""Metadata-only offline fixtures. No ZIP, CSV, prices, or network are read."""
from copy import deepcopy
import contextlib
from datetime import date
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "audit_download_coverage.py"
SPEC = importlib.util.spec_from_file_location("coverage_audit_tested", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture_documents():
    documents = {}
    for partition, (start, end) in audit.PERIODS.items():
        records = []
        for symbol in audit.SYMBOLS:
            for month in audit.months_between(start, end):
                filename = f"{symbol}-1d-{month}.zip"
                url = f"{audit.BASE_URL}/{symbol}/1d/{filename}"
                missing = ((partition == "development" and symbol == "SOLUSDT" and month < "2020-08")
                           or (partition == "holdout" and month == "2026-09"))
                record = {"symbol": symbol, "month": month, "partition": partition, "filename": filename,
                          "url": url, "checksum_url": url + ".CHECKSUM",
                          "archive_path": "/MACHINE_PRIVATE/never-open.zip", "checksum_path": "/MACHINE_PRIVATE/never-open.CHECKSUM",
                          "status": "missing_archive" if missing else "verified"}
                if missing:
                    record.update(error_code="http_404", http_status=404)
                else:
                    expected = audit.month_dates(month)
                    observed = [d for d in expected if not (symbol == "SOLUSDT" and d < "2020-08-11")]
                    record.update(sha256="a" * 64, coverage={
                        "rows": len(observed), "first_date": observed[0], "last_date": observed[-1],
                        "expected_start": expected[0], "expected_end": expected[-1], "expected_rows": len(expected),
                        "observed_dates": observed, "missing_dates": sorted(set(expected) - set(observed)),
                        "duplicate_dates": [], "out_of_range_dates": [], "non_midnight_rows": 0,
                        "timestamp_units": ["us" if month >= "2025-01" else "ms"],
                        "schema_scope": "timestamp_only" if partition == "holdout" else "full_kline"})
                records.append(record)
        documents[partition] = {"schema_version": 1, "requested_partition": partition,
                               "requested_start": "2020-01", "requested_end": "2026-09",
                               "complete_requested_range": False, "archive_count": len(records), "records": records}
    return documents


def record_for(documents, partition, symbol, month):
    return next(r for r in documents[partition]["records"] if r["symbol"] == symbol and r["month"] == month)


class CoverageAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.metadata = self.root / "metadata"
        self.metadata.mkdir()
        self.documents = fixture_documents()

    def write_documents(self):
        for partition, document in self.documents.items():
            (self.metadata / audit.METADATA_NAMES[partition]).write_text(json.dumps(document))

    def run_audit(self):
        self.write_documents()
        return audit.audit_metadata(self.metadata)

    def test_official_prelisting_exclusion_does_not_rewrite_raw_failure(self):
        manifest, coverage = self.run_audit()
        dev = coverage["partitions"]["development"]
        self.assertEqual(len(manifest["archives"]), 243)
        self.assertEqual(dev["status_counts"], {"missing_archive": 7, "verified": 137})
        self.assertFalse(dev["raw_complete_requested_range"])
        self.assertFalse(dev["recomputed_raw_requested_range_complete"])
        self.assertTrue(dev["eligible_requested_range_complete"])
        sol = dev["symbols"]["SOLUSDT"]
        self.assertEqual(sol["verified_archives"], 41)
        self.assertEqual(sol["first_observed_date"], "2020-08-11")
        self.assertEqual(sol["confirmed_prelisting_excluded_dates_count"], 223)
        self.assertEqual(sol["confirmed_prelisting_excluded_archive_months"], [f"2020-{n:02d}" for n in range(1, 8)])
        self.assertEqual(sol["missing_eligible_dates"], [])
        original_failure = next(r for r in manifest["archives"] if r["symbol"] == "SOLUSDT" and r["month"] == "2020-01")
        self.assertEqual(original_failure["status"], "missing_archive")
        self.assertIsNone(original_failure["sha256"])
        self.assertIn("partial trading day", coverage["official_prelisting_rule"]["treatment"])

    def test_interior_gap_is_not_excused_as_prelisting(self):
        record = record_for(self.documents, "development", "SOLUSDT", "2021-06")
        record["coverage"]["observed_dates"].remove("2021-06-15")
        record["coverage"]["rows"] -= 1
        record["coverage"]["missing_dates"] = ["2021-06-15"]
        _, coverage = self.run_audit()
        sol = coverage["partitions"]["development"]["symbols"]["SOLUSDT"]
        self.assertEqual(sol["interior_missing_dates"], ["2021-06-15"])
        self.assertEqual(sol["missing_eligible_dates"], ["2021-06-15"])
        self.assertFalse(sol["eligible_requested_range_complete"])
        self.assertFalse(sol["available_interval_contiguous"])

    def test_missing_holdout_tail_stays_incomplete_despite_continuous_available_prefix(self):
        _, coverage = self.run_audit()
        holdout = coverage["partitions"]["holdout"]
        self.assertEqual(holdout["status_counts"], {"missing_archive": 3, "verified": 96})
        self.assertFalse(holdout["eligible_requested_range_complete"])
        self.assertFalse(coverage["all_eligible_requested_ranges_complete"])
        for summary in holdout["symbols"].values():
            self.assertEqual(summary["requested_end"], "2026-09-30")
            self.assertEqual(summary["last_observed_date"], "2026-08-31")
            self.assertEqual(len(summary["missing_eligible_tail_dates"]), 30)
            self.assertTrue(summary["available_from_eligible_start_contiguous"])
            self.assertFalse(summary["eligible_requested_range_complete"])

    def test_plan_requires_all_exact_records_and_unique_asset_month_keys(self):
        original = deepcopy(self.documents)
        changes = [
            lambda d: d["development"]["records"].pop(),
            lambda d: d["development"]["records"].append(deepcopy(d["development"]["records"][0])),
            lambda d: d["development"]["records"][0].update(symbol="OTHER"),
            lambda d: d["development"]["records"][0].update(partition="holdout"),
            lambda d: d["development"].update(archive_count=1),
            lambda d: d["holdout"].update(requested_end="2026-08"),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.documents = deepcopy(original)
                change(self.documents)
                with self.assertRaises(audit.AuditError):
                    self.run_audit()

    def test_observed_dates_detect_duplicates_even_when_declared_summary_is_clean(self):
        record = record_for(self.documents, "development", "BTCUSDT", "2022-03")
        record["coverage"]["observed_dates"].insert(5, "2022-03-05")
        record["coverage"]["rows"] += 1
        manifest, coverage = self.run_audit()
        btc = coverage["partitions"]["development"]["symbols"]["BTCUSDT"]
        self.assertEqual(btc["duplicate_dates"], ["2022-03-05"])
        self.assertFalse(btc["eligible_requested_range_complete"])
        entry = next(r for r in manifest["archives"] if r["symbol"] == "BTCUSDT" and r["month"] == "2022-03")
        self.assertIn("reported_gaps_or_duplicates_disagree_with_observed_dates", entry["audit_issues"])

    def test_failed_record_with_full_dates_never_counts_as_verified(self):
        record = record_for(self.documents, "development", "BTCUSDT", "2022-04")
        record.update(status="failed", error_code="checksum_mismatch")
        manifest, coverage = self.run_audit()
        btc = coverage["partitions"]["development"]["symbols"]["BTCUSDT"]
        self.assertEqual(btc["verified_archives"], 47)
        self.assertEqual(len(btc["missing_eligible_dates"]), 30)
        self.assertFalse(btc["eligible_requested_range_complete"])
        entry = next(r for r in manifest["archives"] if r["symbol"] == "BTCUSDT" and r["month"] == "2022-04")
        self.assertEqual(entry["status"], "failed")

    def test_only_two_metadata_files_read_and_outputs_have_no_machine_paths(self):
        self.write_documents()
        allowed = {self.metadata / name for name in audit.METADATA_NAMES.values()}
        original_bytes = {path: path.read_bytes() for path in allowed}
        read_bytes = Path.read_bytes
        seen = []
        def guarded_read(path):
            self.assertIn(path, allowed, "Only the two metadata files may be read")
            seen.append(path)
            return read_bytes(path)
        output = self.root / "reports"
        with mock.patch.object(Path, "read_bytes", guarded_read), contextlib.redirect_stdout(io.StringIO()):
            code = audit.main(["--metadata-dir", str(self.metadata), "--output-dir", str(output)])
        self.assertEqual(code, 1)
        self.assertCountEqual(seen, allowed)
        for name in ["archive_manifest.json", "download_coverage_audit.json"]:
            text = (output / name).read_text()
            self.assertNotIn("MACHINE_PRIVATE", text)
            self.assertNotIn(str(self.metadata), text)
            self.assertNotIn("archive_path", text)
        for path, before in original_bytes.items():
            self.assertEqual(path.read_bytes(), before)

    def test_bad_plan_cli_is_nonzero_and_writes_no_reports(self):
        self.documents["holdout"]["records"].pop()
        self.write_documents()
        output = self.root / "reports"
        with contextlib.redirect_stdout(io.StringIO()):
            code = audit.main(["--metadata-dir", str(self.metadata), "--output-dir", str(output)])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
