"""Offline tests: all network access is replaced by byte fixtures."""
import contextlib
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "download_binance.py"
SPEC = importlib.util.spec_from_file_location("tested_binance_downloader", SCRIPT)
dl = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dl
SPEC.loader.exec_module(dl)


def timestamp(day, unit=None):
    unit = unit or ("us" if day >= date(2025, 1, 1) else "ms")
    seconds = int((datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) - dl.EPOCH).total_seconds())
    return str(seconds * (1_000_000 if unit == "us" else 1000)).encode("ascii")


def row(day, *, unit=None, opaque_holdout=False):
    opening = timestamp(day, unit)
    if opaque_holdout:
        return opening + b",\xff\xfeSEALED_PRICE_DO_NOT_DECODE\n"
    scale = 1_000_000 if (unit or ("us" if day.year >= 2025 else "ms")) == "us" else 1000
    closing = str(int(opening) + 86400 * scale - 1).encode("ascii")
    return b",".join([opening, b"1", b"2", b"0.5", b"1.5", b"2", closing,
                      b"3", b"1", b"1", b"1.5", b"0"]) + b"\n"


def fixture(item, *, omit=(), duplicate=None, opaque_holdout=False, start_day=1, raw=None):
    first, last = dl.month_bounds(item["month"])
    lines = []
    for number in range(start_day, last.day + 1):
        if number in omit:
            continue
        value = row(first.replace(day=number), opaque_holdout=opaque_holdout)
        lines.append(value)
        if number == duplicate:
            lines.append(value)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(item["filename"].removesuffix(".zip") + ".csv", b"".join(lines) if raw is None else raw)
    zipped = payload.getvalue()
    checksum = f"{hashlib.sha256(zipped).hexdigest()}  {item['filename']}\n".encode("ascii")
    return {item["url"]: zipped, item["checksum_url"]: checksum}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "data"

    def config(self, **kwargs):
        return dl.DownloadConfig(self.root, start="2020-01", end="2020-01", symbols=("BTCUSDT",), **kwargs)

    def run_fake(self, config, mapping):
        calls, messages = [], []
        def fetch(url):
            calls.append(url)
            value = mapping[url]
            if isinstance(value, Exception):
                raise value
            return value
        code, metadata = dl.run_download(config, fetch=fetch, sleep=lambda _: None, log=messages.append)
        return code, metadata, calls, messages

    def test_default_plan_never_includes_holdout(self):
        plan = dl.build_plan(dl.DownloadConfig(self.root))
        self.assertEqual(len(plan), 3 * 48)
        self.assertEqual(max(i["month"] for i in plan), "2023-12")
        self.assertTrue(all(i["partition"] == "development" for i in plan))
        holdout = dl.build_plan(dl.DownloadConfig(self.root, partition="holdout"))
        self.assertEqual(len(holdout), 3 * 33)
        self.assertEqual(min(i["month"] for i in holdout), "2024-01")

    def test_dry_run_is_read_only_and_fetch_is_never_called(self):
        fetch = mock.Mock(side_effect=AssertionError("Network must not run"))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = dl.main(["--dry-run", "--output-dir", str(self.root)], fetch=fetch)
        self.assertEqual(code, 0)
        self.assertFalse(self.root.exists())
        fetch.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["counts"], {"development": 144, "holdout": 0})

    def test_checksum_verified_cache_and_development_export(self):
        config = self.config()
        item = dl.build_plan(config)[0]
        code, metadata, calls, _ = self.run_fake(config, fixture(item))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        exported = (self.root / "development" / "BTCUSDT_1d_2020-01_2020-01.csv").read_text()
        self.assertEqual(exported.splitlines()[0], ",".join(dl.CSV_COLUMNS))
        self.assertEqual(len(exported.splitlines()), 32)
        with mock.patch.object(dl, "fetch_url", side_effect=AssertionError("No network")):
            code, cached, calls, _ = self.run_fake(config, {})
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertEqual(cached["records"][0]["source"], "cache")
        self.assertEqual(metadata["records"][0]["coverage"]["missing_dates"], [])

    def test_bad_checksum_and_corrupted_cache_fail_before_parsing(self):
        config = self.config()
        item = dl.build_plan(config)[0]
        mapping = fixture(item)
        mapping[item["checksum_url"]] = b"0" * 64 + b"  " + item["filename"].encode() + b"\n"
        code, metadata, _, _ = self.run_fake(config, mapping)
        self.assertEqual(code, 1)
        self.assertEqual(metadata["records"][0]["error_code"], "checksum_mismatch")
        self.assertFalse((self.root / "development" / "BTCUSDT_1d_2020-01_2020-01.csv").exists())
        self.run_fake(config, fixture(item))
        Path(item["archive_path"]).write_bytes(b"corrupt cached content")
        code, metadata, calls, _ = self.run_fake(config, {})
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertEqual(metadata["records"][0]["error_code"], "checksum_mismatch")

    def test_ms_us_midnight_and_boundary_mismatch(self):
        for day, unit in [(date(2024, 12, 31), "ms"), (date(2025, 1, 1), "us")]:
            self.assertEqual(dl.timestamp_date(timestamp(day, unit)), (day, unit))
        for day, wrong in [(date(2024, 12, 31), "us"), (date(2025, 1, 1), "ms")]:
            with self.assertRaisesRegex(dl.SafeFailure, "boundary_mismatch"):
                dl.timestamp_date(timestamp(day, wrong))
        with self.assertRaisesRegex(dl.SafeFailure, "non_midnight"):
            dl.timestamp_date(str(int(timestamp(date(2024, 1, 1))) + 1).encode())

    def test_holdout_never_decodes_opaque_price_bytes_or_exports_csv(self):
        config = dl.DownloadConfig(self.root, partition="holdout", start="2025-01", end="2025-01", symbols=("BTCUSDT",))
        item = dl.build_plan(config)[0]
        with mock.patch.object(dl, "_development_row", side_effect=AssertionError("Holdout must stay sealed")):
            code, metadata, _, messages = self.run_fake(config, fixture(item, opaque_holdout=True))
        self.assertEqual(code, 0)
        self.assertEqual(metadata["records"][0]["coverage"]["rows"], 31)
        self.assertEqual(metadata["records"][0]["coverage"]["timestamp_units"], ["us"])
        self.assertFalse(list(self.root.rglob("*.csv")))
        self.assertEqual(metadata["development_csv_outputs"], [])
        self.assertNotIn("SEALED_PRICE", json.dumps(metadata) + " ".join(messages))
        self.assertTrue(Path(item["archive_path"]).is_file())
        self.assertIn("holdout_sealed", item["archive_path"])

    def test_duplicate_missing_day_bad_schema_and_empty_fail(self):
        config = self.config()
        item = dl.build_plan(config)[0]
        for options, error in [({"duplicate": 4}, "duplicate_dates"),
                               ({"raw": b""}, "empty_archive"),
                               ({"raw": timestamp(date(2020, 1, 1)) + b",bad\n"}, "invalid_development_schema")]:
            with self.subTest(error=error):
                payload = fixture(item, **options)[item["url"]]
                with self.assertRaisesRegex(dl.SafeFailure, error):
                    dl.scan_archive(payload, item)
        code, metadata, _, _ = self.run_fake(config, fixture(item, omit=(15,)))
        self.assertEqual(code, 1)
        self.assertEqual(metadata["symbols"][0]["missing_days_after_first_observation"], ["2020-01-15"])
        self.assertFalse((self.root / "development" / "BTCUSDT_1d_2020-01_2020-01.csv").exists())

    def test_sol_leading_404_is_pending_prelisting_but_internal_gap_is_not(self):
        config = dl.DownloadConfig(self.root, start="2020-01", end="2020-02", symbols=("SOLUSDT",))
        first, second = dl.build_plan(config)
        missing = urllib.error.HTTPError(first["url"], 404, "not found", {}, None)
        mapping = {first["url"]: missing, **fixture(second, start_day=10)}
        code, metadata, calls, _ = self.run_fake(config, mapping)
        self.assertEqual(code, 1)
        self.assertEqual(calls.count(first["url"]), 1)
        summary = metadata["symbols"][0]
        self.assertEqual(summary["leading_missing_months"], ["2020-01"])
        self.assertEqual(summary["prelisting_status"], "possible_prelisting_requires_manual_confirmation")
        self.assertEqual(summary["missing_days_after_first_observation"], [])
        self.assertTrue((self.root / "development" / "SOLUSDT_1d_2020-01_2020-02.csv").is_file())
        payload = fixture(second, start_day=10, omit=(20,))[second["url"]]
        coverage, _ = dl.scan_archive(payload, second)
        summary = dl.summarize_symbol([{"symbol": "SOLUSDT", "month": "2020-01", "partition": "development", "status": "missing_archive"},
            {"symbol": "SOLUSDT", "month": "2020-02", "partition": "development", "status": "verified", "coverage": coverage}])
        self.assertEqual(summary["missing_days_after_first_observation"], ["2020-02-20"])
        self.assertFalse(summary["development_csv_eligible"])

    def test_latest_month_404_has_action_and_nonzero_status(self):
        config = dl.DownloadConfig(self.root, partition="holdout", start="2026-09", end="2026-09", symbols=("BTCUSDT",))
        item = dl.build_plan(config)[0]
        code, metadata, calls, messages = self.run_fake(config, {
            item["url"]: urllib.error.HTTPError(item["url"], 404, "not found", {}, None)})
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("2026-10-05", metadata["records"][0]["action"])
        self.assertIn("does not implement", " ".join(messages))

    def test_network_errors_retry_but_exhaustion_is_safe(self):
        waits = []
        fetch = mock.Mock(side_effect=[urllib.error.URLError("secret server text"), b"ok"])
        self.assertEqual(dl.fetch_with_retry("fixture", fetch, retries=3, backoff=.5, sleep=waits.append), b"ok")
        self.assertEqual(waits, [.5])
        fetch = mock.Mock(side_effect=urllib.error.URLError("secret server text"))
        with self.assertRaisesRegex(dl.SafeFailure, "^network_error$"):
            dl.fetch_with_retry("fixture", fetch, retries=2, backoff=0, sleep=lambda _: None)
        self.assertEqual(fetch.call_count, 2)

    def test_missing_checksum_is_not_prelisting_and_wrong_filename_fails(self):
        config = self.config()
        item = dl.build_plan(config)[0]
        mapping = fixture(item)
        mapping[item["checksum_url"]] = urllib.error.HTTPError(item["checksum_url"], 404, "missing", {}, None)
        code, metadata, _, _ = self.run_fake(config, mapping)
        self.assertEqual(code, 1)
        self.assertEqual(metadata["records"][0]["error_code"], "checksum_unavailable")
        self.assertEqual(metadata["symbols"][0]["leading_missing_months"], [])
        with self.assertRaisesRegex(dl.SafeFailure, "invalid_checksum_format"):
            dl.checksum_digest(b"0" * 64 + b"  other.zip", item["filename"])

    def test_small_range_export_preserves_existing_full_development_csv(self):
        full_config = dl.DownloadConfig(self.root, symbols=("BTCUSDT",))
        mapping = {}
        for item in dl.build_plan(full_config):
            mapping.update(fixture(item))
        code, metadata, _, _ = self.run_fake(full_config, mapping)
        self.assertEqual(code, 0)
        full_path = self.root / "development" / "BTCUSDT_1d_2020-01_2023-12.csv"
        original = full_path.read_bytes()
        self.assertEqual(len(original.splitlines()), 1462)
        self.assertEqual(metadata["development_csv_outputs"], [str(full_path.resolve())])

        # January is cached: a narrow rerun writes its own file without fetching.
        code, metadata, calls, _ = self.run_fake(self.config(), {})
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        narrow_path = self.root / "development" / "BTCUSDT_1d_2020-01_2020-01.csv"
        self.assertEqual(len(narrow_path.read_bytes().splitlines()), 32)
        self.assertEqual(metadata["development_csv_outputs"], [str(narrow_path.resolve())])
        self.assertEqual(full_path.read_bytes(), original)

    def test_all_partition_csv_name_uses_only_effective_development_range(self):
        config = dl.DownloadConfig(self.root, partition="all", start="2023-12", end="2024-01", symbols=("BTCUSDT",))
        mapping = {}
        for item in dl.build_plan(config):
            mapping.update(fixture(item, opaque_holdout=item["partition"] == "holdout"))
        code, metadata, _, _ = self.run_fake(config, mapping)
        self.assertEqual(code, 0)
        expected = self.root / "development" / "BTCUSDT_1d_2023-12_2023-12.csv"
        self.assertEqual(metadata["development_csv_outputs"], [str(expected.resolve())])
        self.assertEqual(len(expected.read_bytes().splitlines()), 32)
        self.assertEqual(list(self.root.rglob("*.csv")), [expected])

    def test_partition_symlink_is_rejected_before_fetch_or_cache_read(self):
        development = self.root / "development"
        development.mkdir(parents=True)
        (self.root / "holdout_sealed").symlink_to(development, target_is_directory=True)
        config = dl.DownloadConfig(self.root, partition="holdout", start="2025-01", end="2025-01", symbols=("BTCUSDT",))
        fetch = mock.Mock(side_effect=AssertionError("Must reject before network"))
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("Must reject before cache reads")):
            code, metadata = dl.run_download(config, fetch=fetch, log=lambda _: None)
        self.assertEqual(code, 1)
        self.assertEqual(metadata["error_code"], "unsafe_output_path")
        fetch.assert_not_called()
        self.assertEqual(list(development.iterdir()), [])
        self.assertFalse((self.root / "metadata").exists())

    def test_cache_checksum_csv_and_metadata_symlinks_are_rejected_before_fetch(self):
        cases = ("archive", "checksum", "csv", "metadata", "archives")
        for target in cases:
            with self.subTest(target=target):
                root = Path(self.temporary.name) / target
                config = dl.DownloadConfig(root, start="2020-01", end="2020-01", symbols=("BTCUSDT",))
                item = dl.build_plan(config)[0]
                outside = Path(self.temporary.name) / (target + "_outside")
                if target in {"metadata", "archives"}:
                    outside.mkdir()
                    path = root / "metadata" if target == "metadata" else root / "development" / "archives"
                else:
                    outside.write_bytes(b"outside data must not be read")
                    path = {"archive": Path(item["archive_path"]),
                            "checksum": Path(item["checksum_path"]),
                            "csv": root / "development" / "BTCUSDT_1d_2020-01_2020-01.csv"}[target]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(outside, target_is_directory=target in {"metadata", "archives"})
                fetch = mock.Mock(side_effect=AssertionError("Must reject before network"))
                with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("Must reject before cache reads")):
                    code, metadata = dl.run_download(config, fetch=fetch, log=lambda _: None)
                self.assertEqual(code, 1)
                self.assertEqual(metadata["error_code"], "unsafe_output_path")
                fetch.assert_not_called()

    def test_output_root_itself_may_be_a_symlink(self):
        actual = Path(self.temporary.name) / "actual_root"
        actual.mkdir()
        self.root.symlink_to(actual, target_is_directory=True)
        config = self.config()
        item = dl.build_plan(config)[0]
        code, metadata, _, _ = self.run_fake(config, fixture(item))
        self.assertEqual(code, 0)
        expected = actual / "development" / "BTCUSDT_1d_2020-01_2020-01.csv"
        self.assertTrue(expected.is_file())
        self.assertEqual(metadata["development_csv_outputs"], [str(expected.resolve())])


if __name__ == "__main__":
    unittest.main()
