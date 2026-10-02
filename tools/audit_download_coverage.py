#!/usr/bin/env python3
"""Audit the fixed download plan using ONLY its two metadata JSON files.

Never opens an archive, CSV, checksum file, or price field. SHA-256 values for
archives are assertions copied from downloader metadata, not reverified here.
Exit codes: 0 = eligible requested ranges complete; 1 = incomplete (reports still
written); 2 = invalid metadata/plan or local I/O failure.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import tempfile

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
METADATA_NAMES = {p: f"download_{p}_2020-01_2026-09.json" for p in ("development", "holdout")}
PERIODS = {"development": (date(2020, 1, 1), date(2023, 12, 31)),
           "holdout": (date(2024, 1, 1), date(2026, 9, 30))}
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SOL_LISTING = {"symbol": "SOLUSDT", "official_scheduled_listing_utc": "2020-08-11T06:00:00Z",
               "first_eligible_date": "2020-08-11",
               "source_url": "https://www.binance.com/en/support/announcement/detail/cf77f566c9b64cc791fc152679175de8",
               "treatment": "First observed date is a partial trading day; do not zero-fill pre-listing dates."}
SOL_START = date.fromisoformat(SOL_LISTING["first_eligible_date"])


class AuditError(ValueError):
    """Invalid or inconsistent fixed-plan metadata; never include raw row data."""


def days_between(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=n)).isoformat() for n in range(max(0, (end - start).days + 1))]


def months_between(start: date, end: date) -> list[str]:
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return months


def month_dates(month: str) -> list[str]:
    first = date.fromisoformat(month + "-01")
    after = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return days_between(first, after - timedelta(days=1))


def _dates(values, field: str) -> list[str]:
    if not isinstance(values, list):
        raise AuditError(f"invalid date list: {field}")
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise AuditError(f"invalid date value: {field}")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise AuditError(f"invalid date value: {field}") from None
    return values


def _date_or_none(value, field: str):
    if value is not None:
        _dates([value], field)
    return value


def _count(value, field: str):
    if type(value) is not int or value < 0:
        raise AuditError(f"invalid nonnegative count: {field}")
    return value


def _coverage(record: dict) -> tuple[dict | None, list[str], list[str]]:
    source = record.get("coverage")
    verified = record["status"] == "verified"
    if source is None:
        if verified:
            raise AuditError("verified archive lacks coverage")
        return None, [], []
    if not isinstance(source, dict):
        raise AuditError("invalid coverage object")
    expected = month_dates(record["month"])
    observed = _dates(source.get("observed_dates", []), "observed_dates")
    reported_missing = _dates(source.get("missing_dates", []), "missing_dates")
    reported_duplicates = _dates(source.get("duplicate_dates", []), "duplicate_dates")
    outside = _dates(source.get("out_of_range_dates", []), "out_of_range_dates")
    units = source.get("timestamp_units", [])
    if not isinstance(units, list) or any(unit not in {"ms", "us"} for unit in units):
        raise AuditError("invalid timestamp units")
    scope = source.get("schema_scope")
    if scope not in {"timestamp_only", "full_kline"}:
        raise AuditError("invalid coverage schema scope")
    safe = {"rows": _count(source.get("rows"), "rows"),
            "first_date": _date_or_none(source.get("first_date"), "first_date"),
            "last_date": _date_or_none(source.get("last_date"), "last_date"),
            "expected_start": expected[0], "expected_end": expected[-1], "expected_rows": len(expected),
            "missing_dates": reported_missing, "duplicate_dates": reported_duplicates,
            "out_of_range_dates": outside,
            "non_midnight_rows": _count(source.get("non_midnight_rows", 0), "non_midnight_rows"),
            "timestamp_units": sorted(set(units)), "schema_scope": scope}
    issues = []
    if verified:
        counts = Counter(observed)
        duplicates = sorted(d for d, count in counts.items() if count > 1)
        missing = sorted(set(expected) - set(observed))
        unexpected = sorted(set(observed) - set(expected))
        if not observed:
            issues.append("verified_archive_has_no_observed_dates")
        if safe["rows"] != len(observed):
            issues.append("row_count_disagrees_with_observed_dates")
        if safe["first_date"] != (min(observed) if observed else None) or safe["last_date"] != (max(observed) if observed else None):
            issues.append("date_bounds_disagree_with_observed_dates")
        if reported_missing != missing or reported_duplicates != duplicates or outside != unexpected:
            issues.append("reported_gaps_or_duplicates_disagree_with_observed_dates")
        if source.get("expected_start") != expected[0] or source.get("expected_end") != expected[-1] or source.get("expected_rows") != len(expected):
            issues.append("reported_expected_calendar_disagrees_with_plan")
        if duplicates:
            issues.append("duplicate_observed_dates")
        if unexpected:
            issues.append("observed_dates_outside_archive_month")
        if observed != sorted(observed):
            issues.append("observed_dates_not_sorted")
        expected_unit = "us" if record["month"] >= "2025-01" else "ms"
        if safe["timestamp_units"] != [expected_unit] or safe["non_midnight_rows"]:
            issues.append("timestamp_unit_or_midnight_check_failed")
        expected_scope = "timestamp_only" if record["partition"] == "holdout" else "full_kline"
        if scope != expected_scope:
            issues.append("coverage_scope_disagrees_with_partition")
        safe.update(missing_dates=missing, duplicate_dates=duplicates, out_of_range_dates=unexpected)
    # Failed records can contain partial metadata, but never supply usable dates.
    return safe, observed if verified else [], issues


def _validate_document(document: dict, partition: str) -> list[dict]:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise AuditError("unsupported metadata schema")
    if document.get("requested_partition") != partition or document.get("requested_start") != "2020-01" or document.get("requested_end") != "2026-09":
        raise AuditError("metadata request does not match the fixed plan")
    if type(document.get("complete_requested_range")) is not bool:
        raise AuditError("missing raw completeness flag")
    records = document.get("records")
    if not isinstance(records, list):
        raise AuditError("records must be a list")
    start, end = PERIODS[partition]
    expected = {(symbol, month) for symbol in SYMBOLS for month in months_between(start, end)}
    keys = []
    for record in records:
        if not isinstance(record, dict):
            raise AuditError("invalid archive record")
        key = (record.get("symbol"), record.get("month"))
        if key not in expected or record.get("partition") != partition:
            raise AuditError("unexpected asset/month/partition in archive records")
        keys.append(key)
        filename = f"{key[0]}-1d-{key[1]}.zip"
        url = f"{BASE_URL}/{key[0]}/1d/{filename}"
        if record.get("url") != url or record.get("filename") != filename or record.get("checksum_url") != url + ".CHECKSUM":
            raise AuditError("archive identity or URL disagrees with the fixed plan")
        if record.get("status") not in {"verified", "missing_archive", "failed"}:
            raise AuditError("unknown archive status")
        checksum = record.get("sha256")
        if record["status"] == "verified" or checksum is not None:
            if not isinstance(checksum, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
                raise AuditError("invalid or absent archive SHA-256")
        if "error_code" in record and not re.fullmatch(r"[a-z0-9_]+", str(record["error_code"])):
            raise AuditError("invalid safe error code")
        if "http_status" in record and (type(record["http_status"]) is not int or not 100 <= record["http_status"] <= 599):
            raise AuditError("invalid HTTP status")
    if len(set(keys)) != len(keys):
        raise AuditError("duplicate archive identity")
    if set(keys) != expected or document.get("archive_count") != len(expected):
        raise AuditError("missing archive records or incorrect planned count")
    return sorted(records, key=lambda r: (r["symbol"], r["month"]))


def _summarize(partition: str, symbol: str, entries: list[dict], dates: list[str]) -> dict:
    start, end = PERIODS[partition]
    eligible_start = SOL_START if partition == "development" and symbol == "SOLUSDT" else start
    excluded = days_between(start, eligible_start - timedelta(days=1))
    counts = Counter(dates)
    present = set(dates)
    duplicates = sorted(d for d, count in counts.items() if count > 1)
    eligible = set(days_between(eligible_start, end))
    missing = sorted(eligible - present)
    unexpected = sorted(present - eligible)
    first, last = (min(present), max(present)) if present else (None, None)
    interior = sorted(set(days_between(date.fromisoformat(first), date.fromisoformat(last))) - present) if present else []
    excluded_months, bad_archives = [], []
    for entry in entries:
        confirmed_missing = (partition == "development" and symbol == "SOLUSDT"
                             and entry["month"] < "2020-08" and entry["status"] == "missing_archive"
                             and entry.get("error_code") == "http_404" and entry.get("http_status") == 404)
        if confirmed_missing:
            excluded_months.append(entry["month"])
        elif entry["status"] != "verified":
            bad_archives.append(entry["month"])
    issues = [{"month": e["month"], "issues": e["audit_issues"]} for e in entries if e["audit_issues"]]
    clean = not (duplicates or unexpected or issues)
    complete = bool(present) and not missing and not bad_archives and clean
    raw_complete = all(e["status"] == "verified" for e in entries) and not (set(days_between(start, end)) - present) and clean
    return {"symbol": symbol, "requested_start": start.isoformat(), "requested_end": end.isoformat(),
            "eligible_start": eligible_start.isoformat(), "eligible_end": end.isoformat(),
            "requested_archives": len(entries), "status_counts": dict(sorted(Counter(e["status"] for e in entries).items())),
            "verified_archives": sum(e["status"] == "verified" for e in entries),
            "observed_rows": len(dates), "unique_observed_dates": len(present),
            "first_observed_date": first, "last_observed_date": last,
            "duplicate_dates": duplicates, "unexpected_dates": unexpected,
            "missing_eligible_dates": missing, "interior_missing_dates": interior,
            "missing_eligible_tail_dates": [d for d in missing if last is not None and d > last],
            "available_interval_contiguous": bool(present) and not interior and clean,
            "available_from_eligible_start_contiguous": bool(present) and first == eligible_start.isoformat() and not interior and clean,
            "recomputed_raw_requested_range_complete": raw_complete,
            "eligible_requested_range_complete": complete,
            "confirmed_prelisting_excluded_archive_months": excluded_months,
            "confirmed_prelisting_excluded_dates_count": len(excluded),
            "confirmed_prelisting_excluded_date_range": {"start": excluded[0], "end": excluded[-1]} if excluded else None,
            "unexcused_nonverified_archive_months": bad_archives,
            "archive_audit_issues": issues}


def audit_metadata(metadata_dir: Path) -> tuple[dict, dict]:
    """Read exactly the two named metadata files; discard all local-path fields."""
    manifest = {"schema_version": 1, "audit_scope": "metadata_only_no_archive_or_price_reads",
                "checksum_scope": "Archive digests copied from downloader metadata; not reverified by this tool.",
                "source_metadata": {}, "archives": []}
    coverage = {"schema_version": 1, "audit_scope": manifest["audit_scope"],
                "official_prelisting_rule": SOL_LISTING, "partitions": {}}
    for partition, name in METADATA_NAMES.items():
        raw = (Path(metadata_dir) / name).read_bytes()
        document = json.loads(raw)
        records = _validate_document(document, partition)
        manifest["source_metadata"][partition] = {"filename": name, "sha256": hashlib.sha256(raw).hexdigest(),
                                                 "raw_complete_requested_range": document["complete_requested_range"]}
        observations = {symbol: [] for symbol in SYMBOLS}
        compact = []
        for record in records:
            safe_coverage, observed, issues = _coverage(record)
            entry = {key: record[key] for key in ("symbol", "month", "partition", "url", "status")}
            entry["sha256"] = record.get("sha256", None)
            for key in ("error_code", "http_status"):
                if key in record:
                    entry[key] = record[key]
            entry.update(coverage=safe_coverage, audit_issues=issues)
            observations[record["symbol"]].extend(observed)
            compact.append(entry)
        summaries = {symbol: _summarize(partition, symbol, [e for e in compact if e["symbol"] == symbol], observations[symbol])
                     for symbol in SYMBOLS}
        recomputed_raw = all(s["recomputed_raw_requested_range_complete"] for s in summaries.values())
        coverage["partitions"][partition] = {
            "raw_complete_requested_range": document["complete_requested_range"],
            "recomputed_raw_requested_range_complete": recomputed_raw,
            "raw_completeness_flag_consistent": document["complete_requested_range"] == recomputed_raw,
            "eligible_requested_range_complete": all(s["eligible_requested_range_complete"] for s in summaries.values()),
            "requested_archive_count": len(compact),
            "status_counts": dict(sorted(Counter(e["status"] for e in compact).items())), "symbols": summaries}
        manifest["archives"].extend(compact)
    coverage["all_eligible_requested_ranges_complete"] = all(
        p["eligible_requested_range_complete"] and p["raw_completeness_flag_consistent"]
        for p in coverage["partitions"].values())
    coverage["interpretation"] = ("Official pre-listing exclusions do not rewrite raw downloader status. "
                                  "A continuous available prefix is not completion of the requested holdout through 2026-09-30. "
                                  "No price validation, protocol freeze, or evaluation authorization is implied.")
    return manifest, coverage


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".part", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest, coverage = audit_metadata(args.metadata_dir)
        _write_json(args.output_dir / "archive_manifest.json", manifest)
        _write_json(args.output_dir / "download_coverage_audit.json", coverage)
    except (OSError, ValueError, TypeError, KeyError):
        print("Metadata audit failed: invalid metadata/plan or local I/O; no completeness established.")
        return 2
    development = coverage["partitions"]["development"]["eligible_requested_range_complete"]
    holdout = coverage["partitions"]["holdout"]["eligible_requested_range_complete"]
    print(f"Metadata-only audit written. Development after confirmed pre-listing exclusions: {development}. "
          f"Holdout through 2026-09-30: {holdout}.")
    return 0 if coverage["all_eligible_requested_ranges_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
