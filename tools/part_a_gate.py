#!/usr/bin/env python3
"""Part A freeze, calendar decision, and single-run evaluation gate.

No forecasting mathematics lives here. Tagged notebook definitions are the sole
research implementation. freeze/dry-check never read market archives. Calendar
locking and preflight inspect checksums and first-field timestamps only. Prices
are decoded only after a valid freeze/calendar decision and an exclusive run
claim. These records are an audit trail, not tamper-proof access control.
"""
from __future__ import annotations

import __future__
import argparse
import ast
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import traceback
import urllib.error
import urllib.request
import uuid
import zipfile
from zoneinfo import ZoneInfo

NOTEBOOK = "notebooks/01_states_and_first_passage.ipynb"
CONFIG = "research/part_a_config.json"
MANIFEST = "research/part_a_freeze_manifest.json"
TAG = "part-a-functions"
PROTECTED = (
    "research/protocol_part_a.md", CONFIG, "tools/part_a_gate.py",
    "requirements-notebook.txt", "tests/test_prediction.py", "tests/test_part_a_gate.py",
    "tests/test_part_a_shared.py",
    "results/data_audit/development_reconciliation.json",
)
ASSETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
OUTPUTS = ("forecasts", "labels", "daily_losses", "summary", "calibration", "comparisons", "coverage", "bootstrap")
SCHEDULED_DATE = date(2026, 10, 7)
CHICAGO = ZoneInfo("America/Chicago")
CALENDAR_RECORD = "results/part_a_calendar_decision/decision.json"
RUN_DIRECTORY = "results/holdout_evaluation"
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"


class GateError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def _now(clock):
    value = clock()
    if value.tzinfo is None:
        raise GateError("clock must provide an aware datetime")
    return value.astimezone(timezone.utc)


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _path(root, relative):
    root = Path(root).resolve()
    parts = Path(relative)
    if parts.is_absolute() or ".." in parts.parts:
        raise GateError("managed path must be relative to project root")
    path = root
    for part in parts.parts:
        path /= part
        if path.is_symlink():
            raise GateError("managed paths must not contain symbolic links")
    return path


def _write(path, obj, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_bytes(obj)
    if exclusive:
        with path.open("xb") as file:
            file.write(payload)
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _git(root, *args):
    result = subprocess.run(["git", "-C", str(Path(root).resolve()), *args], capture_output=True, check=False)
    if result.returncode:
        raise GateError("required Git operation failed")
    return result.stdout


def _projection(payload):
    notebook = json.loads(payload)
    sources, names, nodes = [], [], []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code" or TAG not in cell.get("metadata", {}).get("tags", []):
            continue
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else source
        tree = ast.parse(source)
        if not tree.body or any(not isinstance(node, ast.FunctionDef) for node in tree.body):
            raise GateError("Part A tagged cells must contain function definitions only")
        for node in tree.body:
            if node.decorator_list:
                raise GateError("Part A function decorators are not permitted")
            for default in [*node.args.defaults, *[d for d in node.args.kw_defaults if d is not None]]:
                try:
                    ast.literal_eval(default)
                except (ValueError, TypeError):
                    raise GateError("Part A defaults must be literals without definition-time execution") from None
            if getattr(node, "type_params", []):
                raise GateError("Part A type parameter execution is not supported")
            names.append(node.name)
            nodes.append(node)
        sources.append(source)
    if not sources or "evaluate_asset" not in names or len(set(names)) != len(names):
        raise GateError("Part A projection requires unique functions including evaluate_asset")
    projection = {"notebook": NOTEBOOK, "tag": TAG, "cell_sources": sources, "function_names": names}
    return {"sha256": _sha(_json_bytes(projection)), "function_names": names, "tagged_cells": len(sources)}, nodes


def load_part_a_functions(root):
    """Define tagged functions in np/pd namespace without running research cells."""
    import numpy as np
    import pandas as pd
    _, nodes = _projection(_path(root, NOTEBOOK).read_bytes())
    namespace = {"np": np, "pd": pd, "__name__": "frozen_part_a_notebook"}
    module = ast.Module(body=nodes, type_ignores=[])
    code = compile(module, NOTEBOOK, "exec", flags=__future__.annotations.compiler_flag, dont_inherit=True)
    exec(code, namespace)
    return namespace


def freeze(root, *, clock=utc_now):
    """Create a manifest once; caller must then commit it together with its inputs."""
    root = Path(root).resolve()
    now = _now(clock)
    if now.astimezone(CHICAGO).date() >= SCHEDULED_DATE:
        raise GateError("Part A must be frozen before the October 7 calendar/evaluation date")
    if Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise GateError("project root must be the Git repository root")
    manifest_path = _path(root, MANIFEST)
    if manifest_path.exists():
        raise GateError("freeze manifest already exists; do not overwrite freeze history")
    config = json.loads(_path(root, CONFIG).read_bytes())
    if not isinstance(config, dict):
        raise GateError("Part A config must be a JSON object")
    if _path(root, "tools/part_a_gate.py").read_bytes() != Path(__file__).read_bytes():
        raise GateError("execute the same gate source that is being frozen")
    projection, _ = _projection(_path(root, NOTEBOOK).read_bytes())
    environment = _environment()
    if any(environment[name] == "unavailable" for name in ("numpy", "pandas")):
        raise GateError("NumPy and pandas must be installed before freezing")
    manifest = {"schema_version": 1, "part": "A_prediction_only", "created_utc": now.isoformat(),
                "created_chicago_date": now.astimezone(CHICAGO).date().isoformat(),
                "environment": environment,
                "earliest_evaluation_chicago_date": SCHEDULED_DATE.isoformat(),
                "protected_sha256": {name: _sha(_path(root, name).read_bytes()) for name in PROTECTED},
                "notebook_projection": projection,
                "commit_instruction": "Commit this manifest and all protected inputs; use that commit with --frozen-commit."}
    _write(manifest_path, manifest, exclusive=True)
    return manifest


def verify_freeze(root, frozen_commit):
    """Verify manifest, current protected inputs, tagged projection, and ancestry."""
    if not isinstance(frozen_commit, str) or not re.fullmatch(r"[a-fA-F0-9]{7,40}", frozen_commit):
        raise GateError("frozen commit must be an explicit commit hash")
    commit = _git(root, "rev-parse", "--verify", frozen_commit + "^{commit}").decode().strip()
    _git(root, "merge-base", "--is-ancestor", commit, "HEAD")
    committed_manifest = _git(root, "show", f"{commit}:{MANIFEST}")
    if _path(root, MANIFEST).read_bytes() != committed_manifest:
        raise GateError("current freeze manifest differs from frozen commit")
    manifest = json.loads(committed_manifest)
    if (manifest.get("schema_version") != 1 or manifest.get("part") != "A_prediction_only"
            or manifest.get("earliest_evaluation_chicago_date") != SCHEDULED_DATE.isoformat()
            or set(manifest.get("protected_sha256", {})) != set(PROTECTED)):
        raise GateError("invalid freeze manifest contract")
    created = datetime.fromisoformat(manifest["created_utc"])
    if (created.tzinfo is None or created.astimezone(CHICAGO).date() >= SCHEDULED_DATE
            or created.astimezone(CHICAGO).date().isoformat() != manifest.get("created_chicago_date")):
        raise GateError("freeze creation date is not before the evaluation schedule")
    environment = _environment()
    if any(environment[name] != manifest.get("environment", {}).get(name) for name in ("python", "numpy", "pandas")):
        raise GateError("Python/NumPy/pandas environment differs from the frozen versions")
    if _sha(Path(__file__).read_bytes()) != manifest["protected_sha256"]["tools/part_a_gate.py"]:
        raise GateError("executing gate source differs from the frozen gate")
    for name, expected in manifest["protected_sha256"].items():
        if _sha(_git(root, "show", f"{commit}:{name}")) != expected:
            raise GateError("protected frozen file disagrees with manifest")
        if _sha(_path(root, name).read_bytes()) != expected:
            raise GateError("protected working file has drifted: " + name)
    frozen_projection, _ = _projection(_git(root, "show", f"{commit}:{NOTEBOOK}"))
    live_projection, _ = _projection(_path(root, NOTEBOOK).read_bytes())
    if frozen_projection != manifest["notebook_projection"] or live_projection != frozen_projection:
        raise GateError("Part A notebook function projection has drifted")
    return {"frozen_commit": commit, "head_commit": _git(root, "rev-parse", "HEAD").decode().strip(),
            "manifest_sha256": _sha(committed_manifest), "manifest": manifest}


def _months(first, last):
    current = first.replace(day=1)
    while current <= last:
        yield current.strftime("%Y-%m")
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


def _days(first, last):
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def _timestamp(raw):
    if not raw.isdigit():
        raise GateError("invalid archive open timestamp")
    value = int(raw)
    unit = "us" if value >= 10 ** 14 else "ms"
    divisor = 86_400_000_000 if unit == "us" else 86_400_000
    if value < 10 ** 11 or value % divisor:
        raise GateError("archive timestamp is not a supported UTC midnight")
    try:
        day = date(1970, 1, 1) + timedelta(days=value // divisor)
    except (ValueError, OverflowError):
        raise GateError("archive timestamp is out of range") from None
    if (day >= date(2025, 1, 1)) != (unit == "us"):
        raise GateError("archive timestamp unit disagrees with 2025 boundary")
    return day, unit


def _archive_identity(symbol, month):
    filename = f"{symbol}-1d-{month}.zip"
    partition = "development" if month <= "2023-12" else "holdout_sealed"
    return filename, f"data/{partition}/archives/{filename}", f"{BASE_URL}/{symbol}/1d/{filename}"


def inspect_archive(payload, checksum, symbol, month):
    """Validate SHA-256 and timestamps only; never decode fields after first comma."""
    filename, relative, url = _archive_identity(symbol, month)
    try:
        match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?(?:\./)?([^\r\n]+)", checksum.decode("ascii").strip())
    except UnicodeDecodeError:
        raise GateError("invalid checksum format") from None
    if not match or match.group(2) != filename or match.group(1).lower() != _sha(payload):
        raise GateError("archive checksum mismatch or invalid checksum identity")
    first = date.fromisoformat(month + "-01")
    next_month = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    expected_start = max(first, date(2020, 8, 11)) if symbol == "SOLUSDT" and month == "2020-08" else first
    expected = _days(expected_start, next_month - timedelta(days=1))
    observed, units = [], set()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [entry for entry in archive.infolist() if not entry.is_dir()]
            if len(members) != 1 or members[0].filename != filename[:-4] + ".csv":
                raise GateError("unexpected ZIP member layout")
            with archive.open(members[0]) as file:
                for line in file:
                    timestamp, separator, _ = line.partition(b",")
                    if not separator:
                        raise GateError("missing timestamp separator")
                    day, unit = _timestamp(timestamp)
                    observed.append(day.isoformat())
                    units.add(unit)
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as error:
        if isinstance(error, GateError):
            raise
        raise GateError("invalid archive container") from None
    if observed != expected or len(set(observed)) != len(observed):
        raise GateError("archive has missing, duplicate, unordered, or out-of-range dates")
    return {"symbol": symbol, "month": month, "relative_path": relative, "url": url,
            "sha256": _sha(payload), "rows": len(observed), "first_date": observed[0],
            "last_date": observed[-1], "timestamp_units": sorted(units), "inspection_scope": "timestamp_only"}


def preflight_inputs(root, label_end):
    """Read only archive bytes/checksums and timestamp fields, across all assets."""
    end = date.fromisoformat(label_end)
    if end not in {date(2026, 8, 31), date(2026, 9, 30)}:
        raise GateError("unsupported locked endpoint")
    entries = []
    for symbol in ASSETS:
        first = date(2020, 8, 1) if symbol == "SOLUSDT" else date(2020, 1, 1)
        for month in _months(first, end):
            _, relative, _ = _archive_identity(symbol, month)
            path = _path(root, relative)
            if not path.is_file() or not _path(root, relative + ".CHECKSUM").is_file():
                raise GateError("required input archive or checksum is unavailable: " + symbol + "/" + month)
            entries.append(inspect_archive(path.read_bytes(), _path(root, relative + ".CHECKSUM").read_bytes(), symbol, month))
    return entries


def fetch_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "btc-markov-part-a-calendar/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _save_archive(root, relative, payload):
    path = _path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise GateError("existing archive/checksum differs from fresh verified availability check")
    else:
        with path.open("xb") as file:
            file.write(payload)


def lock_calendar(root, frozen_commit, *, clock=utc_now, fetch=fetch_url):
    """Lock the shared endpoint on October 7 only, without decoding any prices.

    A delayed run requires this existing decision; a later availability check may
    not be presented as evidence about October 7. Failed preflight attempts are
    retained separately and do not consume the single price-evaluation run.
    """
    now = _now(clock)
    if now.astimezone(CHICAGO).date() != SCHEDULED_DATE:
        raise GateError("calendar locking is permitted only on 2026-10-07 America/Chicago; no retrospective fallback")
    freeze_info = verify_freeze(root, frozen_commit)
    if _path(root, CALENDAR_RECORD).exists():
        raise GateError("calendar decision already exists and cannot be overwritten")
    attempt = _path(root, "results/part_a_calendar_attempts/" + now.strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex + ".json")
    record = {"status": "running", "observed_utc": now.isoformat(), "timezone": "America/Chicago",
              "scheduled_chicago_date": SCHEDULED_DATE.isoformat(),
              "frozen_commit": freeze_info["frozen_commit"], "manifest_sha256": freeze_info["manifest_sha256"],
              "september_availability": []}
    _write(attempt, record, exclusive=True)
    try:
        older = preflight_inputs(root, "2026-08-31")
        for symbol in ASSETS:
            _, relative, url = _archive_identity(symbol, "2026-09")
            evidence = {"symbol": symbol, "month": "2026-09", "url": url, "checked_utc": _now(clock).isoformat()}
            if _now(clock).astimezone(CHICAGO).date() != SCHEDULED_DATE:
                raise GateError("calendar checks crossed the scheduled Chicago date")
            try:
                payload = fetch(url)
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    raise GateError("September availability failed without a definitive archive 404") from None
                if _path(root, relative).exists():
                    raise GateError("fresh archive 404 conflicts with an existing September archive")
                evidence.update(status="missing_archive", http_status=404)
                record["september_availability"].append(evidence)
                continue
            except (OSError, urllib.error.URLError):
                raise GateError("September network failure is not missing-archive evidence") from None
            try:
                checksum = fetch(url + ".CHECKSUM")
            except (OSError, urllib.error.URLError):
                raise GateError("September checksum unavailable; cannot activate missing-month fallback") from None
            if not isinstance(payload, bytes) or not isinstance(checksum, bytes):
                raise GateError("availability downloads must contain bytes")
            info = inspect_archive(payload, checksum, symbol, "2026-09")
            _save_archive(root, relative, payload)
            _save_archive(root, relative + ".CHECKSUM", checksum)
            evidence.update(status="verified", http_status=200, sha256=info["sha256"])
            record["september_availability"].append(evidence)
        fallback = any(row["status"] == "missing_archive" for row in record["september_availability"])
        end = "2026-08-31" if fallback else "2026-09-30"
        inputs = older if fallback else preflight_inputs(root, end)
        record.update(status="locked", label_end=end,
                      origin_start="2024-01-01", origin_end=(date.fromisoformat(end) - timedelta(days=5)).isoformat(),
                      fallback=fallback, input_archives=inputs,
                      fallback_reason="fresh_404_on_scheduled_date" if fallback else None,
                      gate_sha256=freeze_info["manifest"]["protected_sha256"]["tools/part_a_gate.py"])
        if _now(clock).astimezone(CHICAGO).date() != SCHEDULED_DATE:
            raise GateError("calendar locking crossed the scheduled Chicago date")
        _write(_path(root, CALENDAR_RECORD), record, exclusive=True)
        _write(attempt, record)
        return record
    except Exception as error:
        record.update(status="failed", error_type=type(error).__name__,
                      error=str(error) if isinstance(error, GateError) else "calendar preflight failed")
        _write(attempt, record)
        raise


def _load_decision(root, freeze_info):
    path = _path(root, CALENDAR_RECORD)
    if not path.is_file():
        raise GateError("dated October 7 calendar decision is required; no retrospective lock")
    raw = path.read_bytes()
    decision = json.loads(raw)
    if (decision.get("status") != "locked" or decision.get("frozen_commit") != freeze_info["frozen_commit"]
            or decision.get("manifest_sha256") != freeze_info["manifest_sha256"]
            or decision.get("gate_sha256") != freeze_info["manifest"]["protected_sha256"]["tools/part_a_gate.py"]
            or decision.get("scheduled_chicago_date") != SCHEDULED_DATE.isoformat()
            or decision.get("timezone") != "America/Chicago"):
        raise GateError("calendar decision does not match the frozen Part A gate")
    for value in [decision.get("observed_utc"), *[row.get("checked_utc") for row in decision.get("september_availability", [])]]:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.astimezone(CHICAGO).date() != SCHEDULED_DATE:
            raise GateError("calendar evidence is not dated October 7 in Chicago")
        if stamp < datetime.fromisoformat(freeze_info["manifest"]["created_utc"]):
            raise GateError("calendar decision precedes the frozen specification")
    evidence = decision.get("september_availability", [])
    if len(evidence) != len(ASSETS) or {row.get("symbol") for row in evidence} != set(ASSETS):
        raise GateError("calendar evidence must cover every asset exactly once")
    for row in evidence:
        _, _, url = _archive_identity(row["symbol"], "2026-09")
        if row.get("month") != "2026-09" or row.get("url") != url:
            raise GateError("calendar evidence has invalid archive identity")
        if row.get("status") == "missing_archive" and row.get("http_status") == 404:
            continue
        if row.get("status") == "verified" and row.get("http_status") == 200 and re.fullmatch(r"[a-f0-9]{64}", row.get("sha256", "")):
            continue
        raise GateError("fallback requires archive 404, never checksum, gap, or network failure")
    fallback = any(row["status"] == "missing_archive" for row in evidence)
    end = "2026-08-31" if fallback else "2026-09-30"
    if (decision.get("fallback") != fallback or decision.get("label_end") != end
            or decision.get("origin_start") != "2024-01-01"
            or decision.get("origin_end") != (date.fromisoformat(end) - timedelta(days=5)).isoformat()):
        raise GateError("calendar endpoint disagrees with the predeclared shared fallback")
    return decision, _sha(raw)


def _read_close(root, entries, symbol):
    """Price ingestion: called only inside a claimed, gated evaluation record."""
    import numpy as np
    import pandas as pd
    dates, values = [], []
    for entry in entries:
        if entry["symbol"] != symbol:
            continue
        payload = _path(root, entry["relative_path"]).read_bytes()
        if _sha(payload) != entry["sha256"]:
            raise GateError("archive changed between preflight and price ingestion")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            member = next(item for item in archive.infolist() if not item.is_dir())
            with archive.open(member) as file:
                for raw in file:
                    fields = next(csv.reader([raw.decode("ascii").rstrip("\r\n")], strict=True))
                    if len(fields) != 12:
                        raise GateError("price ingestion encountered invalid kline schema")
                    day, _ = _timestamp(fields[0].encode("ascii"))
                    close = float(fields[4])
                    if not np.isfinite(close) or close <= 0:
                        raise GateError("price ingestion encountered invalid close")
                    dates.append(pd.Timestamp(day))
                    values.append(close)
    series = pd.Series(values, index=pd.DatetimeIndex(dates, name="date"), name="close", dtype=float)
    if not series.index.is_unique or not series.index.is_monotonic_increasing:
        raise GateError("price ingestion calendar is invalid")
    return series


def _environment():
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for package in ("numpy", "pandas", "scipy", "nbformat"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = "unavailable"
    return result


def _exclusion_counts(output, pd):
    rows = []
    for table, column in [("forecasts", "exclusion_reason"), ("daily_losses", "score_exclusion_reason")]:
        if column not in output[table]:
            raise GateError("required exclusion-reason column is missing")
        reasons = output[table][column].fillna("").astype(str)
        for reason, count in reasons[reasons.ne("")].value_counts().items():
            rows.append({"stage": table, "reason_combination": reason, "count": int(count)})
    return pd.DataFrame(rows, columns=["stage", "reason_combination", "count"])


def _write_report(run_dir, decision, outputs):
    primary = outputs["BTCUSDT"]["comparisons"].loc["markov_vs_state"]
    lines = ["# Part A prediction evaluation", "", "Primary asset: BTCUSDT. ETHUSDT and SOLUSDT are descriptive secondary checks.", "",
             f"Frozen commit: `{decision['frozen_commit']}`.",
             f"Calendar decision: {decision['observed_utc']} (October 7 in America/Chicago).",
             f"Forecast origins: {decision['origin_start']} through {decision['origin_end']}; complete labels through {decision['label_end']}.", ""]
    if decision["fallback"]:
        lines.append("The predeclared shared August endpoint fallback was activated because a fresh September archive request returned HTTP 404 on the scheduled date. All three assets use the same shortened interval; it was not selected from forecast performance.")
    else:
        lines.append("All three September archives passed fresh availability, checksum and timestamp checks. The full prespecified September endpoint was retained.")
    lines += ["", "## Primary BTC decision", "",
              "Comparison: Markov versus direct current-state historical frequency. Positive Brier loss difference favors Markov.",
              f"Recorded decision: **{primary['decision']}**. Brier difference: {primary['delta_brier']}; 95% interval: [{primary['ci_lower']}, {primary['ci_upper']}].", "",
              "The paired calendar-block interval conditions on the generated forecast paths and does not refit models. It does not correct model selection, establish Markovity, or make the secondary assets independent replications. An interval crossing zero indicates uncertainty, not equivalence."]
    for symbol in ASSETS:
        lines += ["", "## " + symbol, "", "All three prespecified forecasters:", "", "```text",
                  outputs[symbol]["summary"].to_string(), "```", "", "All prespecified paired comparisons:", "", "```text",
                  outputs[symbol]["comparisons"].to_string(), "```", "", "Coverage:", "", "```text",
                  outputs[symbol]["coverage"].to_string(index=False), "```", "",
                  f"Full daily forecasts, labels, losses, calibration, bootstrap draws and exclusion-reason counts are retained in `{symbol}/`."]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate(root, frozen_commit, *, clock=utc_now):
    """Claim once, then load prices and save every prespecified asset/output."""
    now = _now(clock)
    if now.astimezone(CHICAGO).date() < SCHEDULED_DATE:
        raise GateError("price evaluation is forbidden before 2026-10-07 America/Chicago")
    freeze_info = verify_freeze(root, frozen_commit)
    decision, decision_sha = _load_decision(root, freeze_info)
    run_dir = _path(root, RUN_DIRECTORY)
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()  # Exclusive claim occurs before ANY price decode.
    except FileExistsError:
        raise GateError("evaluation record already exists; retries and overwrites are forbidden") from None
    status = {"status": "running", "started_utc": now.isoformat(), "frozen_commit": freeze_info["frozen_commit"],
              "head_commit": freeze_info["head_commit"], "freeze_manifest_sha256": freeze_info["manifest_sha256"],
              "calendar_decision_sha256": decision_sha, "environment": _environment(),
              "origin_start": decision["origin_start"], "origin_end": decision["origin_end"],
              "label_end": decision["label_end"], "assets": list(ASSETS), "outputs": list(OUTPUTS),
              "claim_policy": "Exclusive directory before first price read; failed records are retained."}
    _write(run_dir / "status.json", status)
    try:
        inputs = preflight_inputs(root, decision["label_end"])
        if inputs != decision.get("input_archives"):
            raise GateError("input archive set or hashes changed after the locked calendar decision")
        _write(run_dir / "input_archives.json", inputs)
        _write(run_dir / "calendar_decision.json", decision)
        _write(run_dir / "freeze_manifest.json", freeze_info["manifest"])
        config = json.loads(_path(root, CONFIG).read_bytes())
        _write(run_dir / "config.json", config)
        namespace = load_part_a_functions(root)
        pd = namespace["pd"]
        all_outputs = {}
        for symbol in ASSETS:
            close = _read_close(root, inputs, symbol)
            output = namespace["evaluate_asset"](close, decision["origin_start"], decision["origin_end"], config)
            if not isinstance(output, dict) or set(output) != set(OUTPUTS) or not all(isinstance(output[key], pd.DataFrame) for key in OUTPUTS):
                raise GateError("evaluate_asset must return all eight prespecified DataFrames")
            if set(output["summary"].index) != {"markov", "pooled", "state"} or set(output["comparisons"].index) != {"markov_vs_state", "markov_vs_pooled", "state_vs_pooled"}:
                raise GateError("prespecified forecasters or comparisons are missing")
            destination = run_dir / symbol
            destination.mkdir()
            for key in OUTPUTS:
                output[key].to_csv(destination / (key + ".csv"), index=True)
            _exclusion_counts(output, pd).to_csv(destination / "exclusion_counts.csv", index=False)
            all_outputs[symbol] = output
        _write_report(run_dir, decision, all_outputs)
        status.update(status="completed", completed_utc=_now(clock).isoformat())
        _write(run_dir / "status.json", status)
        return status
    except Exception as error:
        (run_dir / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        status.update(status="failed", failed_utc=_now(clock).isoformat(), error_type=type(error).__name__,
                      error=str(error) if isinstance(error, GateError) else "evaluation failed; preserve this record and document corrections")
        _write(run_dir / "status.json", status)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "dry-check", "lock-calendar", "evaluate"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--frozen-commit")
    args = parser.parse_args(argv)
    if args.command != "freeze" and not args.frozen_commit:
        parser.error("--frozen-commit is required")
    try:
        if args.command == "freeze":
            freeze(args.root)
            print("Part A manifest created. Commit it and its protected inputs before calling this a committed freeze.")
        elif args.command == "dry-check":
            result = verify_freeze(args.root, args.frozen_commit)
            print("Part A freeze verified; no archive or price was read. Frozen commit: " + result["frozen_commit"])
        elif args.command == "lock-calendar":
            result = lock_calendar(args.root, args.frozen_commit)
            print("Calendar decision locked without decoding prices. Label endpoint: " + result["label_end"])
        else:
            result = evaluate(args.root, args.frozen_commit)
            print("Single Part A evaluation completed. Label endpoint: " + result["label_end"])
        return 0
    except GateError as error:
        print("Part A gate refused: " + str(error))
        return 1
    except (OSError, ValueError, TypeError, KeyError, SyntaxError):
        print("Part A gate refused or failed. Preserve any existing calendar/evaluation records; inspect the gate conditions.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
