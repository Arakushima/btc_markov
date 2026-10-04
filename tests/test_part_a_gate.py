"""Synthetic gate tests: temporary Git repositories and ZIPs; no live network."""
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.error
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "part_a_gate.py"
SPEC = importlib.util.spec_from_file_location("tested_part_a_gate", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
OCT3 = datetime(2026, 10, 3, 17, tzinfo=timezone.utc)
OCT7 = datetime(2026, 10, 7, 17, tzinfo=timezone.utc)
OCT8 = datetime(2026, 10, 8, 17, tzinfo=timezone.utc)


def function_source(*, fail=False):
    if fail:
        return "def evaluate_asset(close, origin_start, origin_end, config):\n    raise RuntimeError('synthetic failure')\n"
    return '''def evaluate_asset(close, origin_start, origin_end, config):
    output = {name: pd.DataFrame({'origin_end': [origin_end]}) for name in %s}
    output['forecasts']['exclusion_reason'] = ''
    output['daily_losses']['score_exclusion_reason'] = ''
    output['summary'] = pd.DataFrame({'brier': [0.2, 0.2, 0.2], 'n': [1, 1, 1]}, index=['markov','pooled','state'])
    output['comparisons'] = pd.DataFrame({'delta_brier': [0.,0.,0.], 'ci_lower': [-.1,-.1,-.1],
        'ci_upper': [.1,.1,.1], 'decision': ['uncertain','uncertain','uncertain']},
        index=['markov_vs_state','markov_vs_pooled','state_vs_pooled'])
    return output
''' % (repr(gate.OUTPUTS),)


def synthetic_archive(symbol, month, *, opaque=False, omit=None, wrong_unit=False):
    first = date.fromisoformat(month + "-01")
    following = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    start = max(first, date(2020, 8, 11)) if symbol == "SOLUSDT" and month == "2020-08" else first
    rows = []
    for text in gate._days(start, following - gate.timedelta(days=1)):
        if text == omit:
            continue
        day = date.fromisoformat(text)
        us = day >= date(2025, 1, 1)
        if wrong_unit:
            us = not us
        multiplier = 86_400_000_000 if us else 86_400_000
        timestamp = str((day - date(1970, 1, 1)).days * multiplier).encode()
        suffix = b",\xffSEALED_NO_DECODE\n" if opaque else b",1,2,0.5,1.5,1,0,1,1,1,1,0\n"
        rows.append(timestamp + suffix)
    filename, _, _ = gate._archive_identity(symbol, month)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename[:-4] + ".csv", b"".join(rows))
    payload = out.getvalue()
    checksum = (hashlib.sha256(payload).hexdigest() + "  " + filename + "\n").encode()
    return payload, checksum


class PartAGateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name in gate.PROTECTED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic protected input\n")
        shutil.copyfile(SCRIPT, self.root / "tools/part_a_gate.py")
        (self.root / gate.CONFIG).write_text("{}\n")
        self.write_notebook()
        self.git("init", "-q")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("config", "user.name", "Synthetic Test")
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic starting inputs")
        gate.freeze(self.root, clock=lambda: OCT3)
        self.git("add", gate.MANIFEST)
        self.git("commit", "-qm", "synthetic Part A freeze")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE).decode()

    def write_notebook(self, *, source=None, other="raise RuntimeError('untagged must never run')"):
        path = self.root / gate.NOTEBOOK
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"cells": [
            {"cell_type": "code", "metadata": {"tags": [gate.TAG]}, "source": source or function_source()},
            {"cell_type": "code", "metadata": {}, "source": other}]}))

    def populate_inputs(self, *, end="2026-08-31", opaque=False):
        for symbol in gate.ASSETS:
            first = date(2020, 8, 1) if symbol == "SOLUSDT" else date(2020, 1, 1)
            for month in gate._months(first, date.fromisoformat(end)):
                _, relative, _ = gate._archive_identity(symbol, month)
                payload, checksum = synthetic_archive(symbol, month, opaque=opaque)
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                Path(str(path) + ".CHECKSUM").write_bytes(checksum)

    def fetch_fixture(self, *, missing=(), bad_checksum=(), missing_checksum=(), gaps=(), opaque=False):
        fixtures = {}
        for symbol in gate.ASSETS:
            _, _, url = gate._archive_identity(symbol, "2026-09")
            if symbol in missing:
                fixtures[url] = urllib.error.HTTPError(url, 404, "synthetic missing", {}, None)
            else:
                payload, checksum = synthetic_archive(symbol, "2026-09", opaque=opaque,
                    omit="2026-09-15" if symbol in gaps else None)
                fixtures[url] = payload
                if symbol in bad_checksum:
                    checksum = b"0" * 64 + b"  " + f"{symbol}-1d-2026-09.zip".encode()
                if symbol in missing_checksum:
                    checksum = urllib.error.HTTPError(url, 404, "synthetic missing checksum", {}, None)
                fixtures[url + ".CHECKSUM"] = checksum
        def fetch(url):
            value = fixtures[url]
            if isinstance(value, Exception):
                raise value
            return value
        return fetch

    def lock(self, **kwargs):
        return gate.lock_calendar(self.root, self.commit, clock=lambda: OCT7, fetch=self.fetch_fixture(**kwargs))

    def test_freeze_and_dry_check_read_no_archives_or_analysis_cells(self):
        with mock.patch.object(gate, "preflight_inputs", side_effect=AssertionError("no archive read")):
            result = gate.verify_freeze(self.root, self.commit)
            namespace = gate.load_part_a_functions(self.root)
        self.assertEqual(result["frozen_commit"], self.commit)
        self.assertIn("evaluate_asset", namespace)
        self.assertNotIn("close", namespace)

    def test_only_function_definitions_with_no_definition_time_side_effects(self):
        for source in ["x = 1\n" + function_source(),
                       "@print('bad')\n" + function_source(),
                       "def bad(x=print('bad')):\n    pass\n" + function_source()]:
            with self.subTest(source=source):
                self.write_notebook(source=source)
                with self.assertRaises(gate.GateError):
                    gate.load_part_a_functions(self.root)

    def test_part_b_only_working_and_committed_changes_are_allowed(self):
        self.write_notebook(other="# new Part B diagnostic\nraise RuntimeError('still not run')")
        (self.root / "research/part_b_notes.md").write_text("New Part B notes")
        gate.verify_freeze(self.root, self.commit)
        self.git("add", gate.NOTEBOOK, "research/part_b_notes.md")
        self.git("commit", "-qm", "continue Part B")
        checked = gate.verify_freeze(self.root, self.commit)
        self.assertNotEqual(checked["head_commit"], self.commit)

    def test_protected_file_and_function_projection_drift_are_refused(self):
        config = self.root / gate.CONFIG
        before = config.read_bytes()
        config.write_text('{"changed":true}')
        with self.assertRaisesRegex(gate.GateError, "drifted"):
            gate.verify_freeze(self.root, self.commit)
        config.write_bytes(before)
        self.write_notebook(source=function_source() + "\n# changed Part A projection\n")
        with self.assertRaisesRegex(gate.GateError, "projection"):
            gate.verify_freeze(self.root, self.commit)

    def test_freeze_versions_are_recorded_and_runtime_drift_is_refused(self):
        manifest = json.loads((self.root / gate.MANIFEST).read_text())
        self.assertEqual(manifest["created_chicago_date"], "2026-10-03")
        self.assertTrue(all(name in manifest["environment"] for name in ["python", "numpy", "pandas"]))
        self.assertIn("tests/test_part_a_shared.py", manifest["protected_sha256"])
        self.assertNotIn("tests/test_markov.py", manifest["protected_sha256"])
        changed = gate._environment()
        changed["numpy"] = "synthetic_drift"
        with mock.patch.object(gate, "_environment", return_value=changed):
            with self.assertRaisesRegex(gate.GateError, "environment"):
                gate.verify_freeze(self.root, self.commit)

    def test_manifest_mutation_and_nonancestor_commit_are_refused(self):
        manifest = self.root / gate.MANIFEST
        before = manifest.read_bytes()
        manifest.write_bytes(before + b"\n")
        with self.assertRaisesRegex(gate.GateError, "manifest"):
            gate.verify_freeze(self.root, self.commit)
        manifest.write_bytes(before)
        self.git("checkout", "--orphan", "unrelated")
        self.git("add", ".")
        self.git("commit", "-qm", "unrelated history")
        with self.assertRaises(gate.GateError):
            gate.verify_freeze(self.root, self.commit)

    def test_early_date_and_late_calendar_lock_refuse_before_price_or_network_read(self):
        with mock.patch.object(gate, "_read_close", side_effect=AssertionError("price read")):
            with self.assertRaisesRegex(gate.GateError, "before"):
                gate.evaluate(self.root, self.commit, clock=lambda: OCT3)
        for clock in [lambda: OCT3, lambda: OCT8]:
            fetch = mock.Mock(side_effect=AssertionError("network"))
            with self.assertRaisesRegex(gate.GateError, "only on"):
                gate.lock_calendar(self.root, self.commit, clock=clock, fetch=fetch)
            fetch.assert_not_called()
        self.assertFalse((self.root / gate.RUN_DIRECTORY).exists())

    def test_ms_us_units_and_timestamp_only_checks(self):
        for month, unit in [("2024-12", "ms"), ("2025-01", "us")]:
            payload, checksum = synthetic_archive("BTCUSDT", month, opaque=True)
            info = gate.inspect_archive(payload, checksum, "BTCUSDT", month)
            self.assertEqual(info["timestamp_units"], [unit])
        payload, checksum = synthetic_archive("BTCUSDT", "2025-01", wrong_unit=True)
        with self.assertRaisesRegex(gate.GateError, "unit"):
            gate.inspect_archive(payload, checksum, "BTCUSDT", "2025-01")

    def test_fresh_archive_404_locks_shared_august_end_without_decoding_prices(self):
        self.populate_inputs(opaque=True)
        with mock.patch.object(gate, "_read_close", side_effect=AssertionError("price read")):
            decision = self.lock(missing=("ETHUSDT",), opaque=True)
        self.assertEqual(decision["label_end"], "2026-08-31")
        self.assertEqual(decision["origin_end"], "2026-08-26")
        self.assertEqual(len(decision["input_archives"]), 233)
        self.assertTrue(all(entry["month"] <= "2026-08" for entry in decision["input_archives"]))
        self.assertEqual({entry["symbol"] for entry in decision["input_archives"]}, set(gate.ASSETS))
        self.assertFalse((self.root / gate.RUN_DIRECTORY).exists())
        with self.assertRaisesRegex(gate.GateError, "already exists"):
            self.lock(missing=("ETHUSDT",), opaque=True)

    def test_available_september_locks_full_shared_interval(self):
        self.populate_inputs(opaque=True)
        decision = self.lock(opaque=True)
        self.assertFalse(decision["fallback"])
        self.assertEqual(decision["label_end"], "2026-09-30")
        self.assertEqual(decision["origin_end"], "2026-09-25")
        self.assertEqual(len(decision["input_archives"]), 236)

    def test_bad_checksum_is_not_missing_archive_fallback_and_attempt_is_retained(self):
        self.populate_inputs(opaque=True)
        with self.assertRaisesRegex(gate.GateError, "checksum"):
            self.lock(bad_checksum=("BTCUSDT",), missing=("ETHUSDT",), opaque=True)
        self.assertFalse((self.root / gate.CALENDAR_RECORD).exists())
        attempts = list((self.root / "results/part_a_calendar_attempts").glob("*.json"))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(attempts[0].read_text())["status"], "failed")

    def test_missing_checksum_and_calendar_gaps_do_not_activate_fallback(self):
        self.populate_inputs(opaque=True)
        for kwargs in [{"missing_checksum": ("BTCUSDT",)}, {"gaps": ("BTCUSDT",)}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(gate.GateError):
                    self.lock(**kwargs, missing=("ETHUSDT",), opaque=True)
                self.assertFalse((self.root / gate.CALENDAR_RECORD).exists())

    def test_missing_older_archive_aborts_before_september_probe(self):
        self.populate_inputs(opaque=True)
        _, relative, _ = gate._archive_identity("BTCUSDT", "2024-02")
        (self.root / relative).unlink()
        fetch = mock.Mock(side_effect=AssertionError("must not fetch"))
        with self.assertRaisesRegex(gate.GateError, "required input"):
            gate.lock_calendar(self.root, self.commit, clock=lambda: OCT7, fetch=fetch)
        fetch.assert_not_called()

    def test_delayed_evaluation_requires_existing_october7_decision(self):
        with self.assertRaisesRegex(gate.GateError, "decision is required"):
            gate.evaluate(self.root, self.commit, clock=lambda: OCT8)

    def test_atomic_claim_precedes_price_read_all_outputs_saved_and_repeat_refused(self):
        self.populate_inputs()
        self.lock(missing=gate.ASSETS)
        original = gate._read_close
        calls = []
        def checked_read(root, entries, symbol):
            status = json.loads((self.root / gate.RUN_DIRECTORY / "status.json").read_text())
            self.assertEqual(status["status"], "running")
            self.assertTrue((self.root / gate.RUN_DIRECTORY / "input_archives.json").exists())
            calls.append(symbol)
            return original(root, entries, symbol)
        with mock.patch.object(gate, "_read_close", checked_read):
            result = gate.evaluate(self.root, self.commit, clock=lambda: OCT8)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls, list(gate.ASSETS))
        for symbol in gate.ASSETS:
            for output in gate.OUTPUTS:
                self.assertTrue((self.root / gate.RUN_DIRECTORY / symbol / (output + ".csv")).is_file())
            self.assertTrue((self.root / gate.RUN_DIRECTORY / symbol / "exclusion_counts.csv").is_file())
        report = (self.root / gate.RUN_DIRECTORY / "report.md").read_text()
        self.assertIn("fallback was activated", report)
        self.assertIn("uncertain", report)
        self.assertIn("2026-08-26", report)
        with mock.patch.object(gate, "_read_close", side_effect=AssertionError("repeat price read")):
            with self.assertRaisesRegex(gate.GateError, "already exists"):
                gate.evaluate(self.root, self.commit, clock=lambda: OCT8)

    def test_post_lock_input_change_fails_without_prices_and_retains_run(self):
        self.populate_inputs()
        self.lock(missing=gate.ASSETS)
        _, relative, _ = gate._archive_identity("BTCUSDT", "2024-01")
        (self.root / relative).write_bytes(b"corrupted synthetic archive")
        with mock.patch.object(gate, "_read_close", side_effect=AssertionError("price read")):
            with self.assertRaisesRegex(gate.GateError, "checksum"):
                gate.evaluate(self.root, self.commit, clock=lambda: OCT8)
        status = json.loads((self.root / gate.RUN_DIRECTORY / "status.json").read_text())
        self.assertEqual(status["status"], "failed")
        with self.assertRaisesRegex(gate.GateError, "already exists"):
            gate.evaluate(self.root, self.commit, clock=lambda: OCT8)

    def test_model_failure_retains_run_and_cannot_be_retried(self):
        self.populate_inputs()
        self.lock(missing=gate.ASSETS)
        def fail(*args):
            raise RuntimeError("synthetic exception after price access")
        import pandas as pd
        with mock.patch.object(gate, "load_part_a_functions", return_value={"pd": pd, "evaluate_asset": fail}):
            with self.assertRaises(RuntimeError):
                gate.evaluate(self.root, self.commit, clock=lambda: OCT8)
        status = json.loads((self.root / gate.RUN_DIRECTORY / "status.json").read_text())
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error_type"], "RuntimeError")
        self.assertIn("synthetic exception", (self.root / gate.RUN_DIRECTORY / "traceback.txt").read_text())
        with self.assertRaisesRegex(gate.GateError, "already exists"):
            gate.evaluate(self.root, self.commit, clock=lambda: OCT8)


if __name__ == "__main__":
    unittest.main()
