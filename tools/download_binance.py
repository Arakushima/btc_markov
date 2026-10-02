#!/usr/bin/env python3
"""Download verified Binance monthly spot archives without opening holdout prices.

Standard-library only. The default partition is development (through 2023).
Holdout ZIPs remain sealed: validation reads only each raw line's first timestamp
field. No holdout OHLC field is decoded, converted, printed, or exported.
"""
from __future__ import annotations

import argparse
import calendar
import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
from typing import Callable
import urllib.error
import urllib.request
import zipfile


BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
FIRST_MONTH, LAST_MONTH = "2020-01", "2026-09"
CSV_COLUMNS = ("date", "open", "high", "low", "close", "volume", "quote_volume",
               "n_trades", "taker_buy_base", "taker_buy_quote")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
UNIT_CHANGE = date(2025, 1, 1)


@dataclass(frozen=True)
class DownloadConfig:
    output_dir: Path
    partition: str = "development"
    start: str = FIRST_MONTH
    end: str = LAST_MONTH
    symbols: tuple[str, ...] = SYMBOLS
    retries: int = 3
    backoff: float = 0.5


class SafeFailure(Exception):
    """Errors contain fixed codes and safe coverage, never source row contents."""
    def __init__(self, code: str, *, http_status: int | None = None, coverage=None):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.coverage = coverage


def month_bounds(month: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("Months must use YYYY-MM")
    year, number = map(int, month.split("-"))
    return date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])


def month_range(start: str, end: str) -> list[str]:
    first, _ = month_bounds(start)
    final, _ = month_bounds(end)
    if first > final:
        raise ValueError("start must not be after end")
    months = []
    while first <= final:
        months.append(first.strftime("%Y-%m"))
        first = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return months


def build_plan(config: DownloadConfig) -> list[dict]:
    months = month_range(config.start, config.end)
    if config.start < FIRST_MONTH or config.end > LAST_MONTH:
        raise ValueError("Supported range is 2020-01 through 2026-09")
    if config.partition not in {"development", "holdout", "all"}:
        raise ValueError("partition must be development, holdout, or all")
    if not config.symbols or len(set(config.symbols)) != len(config.symbols) or any(s not in SYMBOLS for s in config.symbols):
        raise ValueError("symbols must be distinct BTCUSDT, ETHUSDT, or SOLUSDT")
    if config.retries < 1 or config.backoff < 0:
        raise ValueError("retries must be positive and backoff nonnegative")
    plan = []
    for symbol in config.symbols:
        for month in months:
            partition = "development" if month <= "2023-12" else "holdout"
            if config.partition != "all" and partition != config.partition:
                continue
            filename = f"{symbol}-1d-{month}.zip"
            url = f"{BASE_URL}/{symbol}/1d/{filename}"
            directory = "development" if partition == "development" else "holdout_sealed"
            archive = config.output_dir / directory / "archives" / filename
            plan.append({"symbol": symbol, "month": month, "partition": partition,
                         "url": url, "checksum_url": url + ".CHECKSUM",
                         "filename": filename, "archive_path": str(archive),
                         "checksum_path": str(archive) + ".CHECKSUM"})
    if not plan:
        raise ValueError("Requested dates do not intersect the selected partition")
    return plan


def fetch_url(url: str) -> bytes:
    """Production fetch; tests inject a fake and never call this function."""
    request = urllib.request.Request(url, headers={"User-Agent": "btc-markov-research-downloader/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def fetch_with_retry(url: str, fetch: Callable[[str], bytes], *, retries: int,
                     backoff: float, sleep: Callable[[float], None]) -> bytes:
    code, status = "network_error", None
    for attempt in range(retries):
        try:
            result = fetch(url)
            if not isinstance(result, bytes):
                raise SafeFailure("non_bytes_download")
            return result
        except urllib.error.HTTPError as error:
            status = error.code
            code = f"http_{status}"
            if status == 404:
                raise SafeFailure(code, http_status=status) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            code, status = "network_error", None
        if attempt + 1 < retries:
            sleep(backoff * (2 ** attempt))
    raise SafeFailure(code, http_status=status)


def checksum_digest(checksum: bytes, filename: str) -> str:
    try:
        text = checksum.decode("ascii").strip()
    except UnicodeDecodeError:
        raise SafeFailure("invalid_checksum_format") from None
    match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?([^\r\n]+)", text)
    if not match or match.group(2).removeprefix("./") != filename:
        raise SafeFailure("invalid_checksum_format")
    return match.group(1).lower()


def check_managed_path(root: Path, path: Path) -> None:
    """The output root may be a resolved link; nothing below it may be a link.

    Check lexical containment as well as resolved containment, rejecting even a
    symlink that points somewhere else inside the root (partition mixing).
    """
    root = root.resolve()
    try:
        relative = path.absolute().relative_to(root)
    except ValueError:
        raise SafeFailure("unsafe_output_path") from None
    if any(part in {".", ".."} for part in relative.parts):
        raise SafeFailure("unsafe_output_path")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SafeFailure("unsafe_output_path")
    try:
        path.resolve().relative_to(root)
    except (ValueError, RuntimeError):
        raise SafeFailure("unsafe_output_path") from None


def development_csv_path(root: Path, symbol: str, records: list[dict]) -> Path:
    months = [r["month"] for r in records if r["symbol"] == symbol and r["partition"] == "development"]
    return root / "development" / f"{symbol}_1d_{min(months)}_{max(months)}.csv"


def metadata_path(config: DownloadConfig) -> Path:
    return config.output_dir / "metadata" / f"download_{config.partition}_{config.start}_{config.end}.json"


def validate_output_paths(config: DownloadConfig, plan: list[dict]) -> None:
    """Preflight EVERY managed destination before fetching or reading a cache."""
    root = config.output_dir
    paths = [root / "development", root / "holdout_sealed", root / "metadata",
             root / "development" / "archives", root / "holdout_sealed" / "archives",
             metadata_path(config)]
    for item in plan:
        paths.extend((Path(item["archive_path"]), Path(item["checksum_path"])))
    for symbol in config.symbols:
        if any(r["symbol"] == symbol and r["partition"] == "development" for r in plan):
            paths.append(development_csv_path(root, symbol, plan))
    for path in paths:
        check_managed_path(root, path)


def atomic_write(path: Path, payload: bytes, *, root: Path) -> None:
    check_managed_path(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_managed_path(root, path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".part", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
        check_managed_path(root, path)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def get_verified_archive(item: dict, config: DownloadConfig, fetch, sleep) -> tuple[bytes, str, str]:
    archive, checksum_path = Path(item["archive_path"]), Path(item["checksum_path"])
    check_managed_path(config.output_dir, archive)
    check_managed_path(config.output_dir, checksum_path)
    archive_cached, checksum_cached = archive.exists(), checksum_path.exists()
    payload = archive.read_bytes() if archive_cached else fetch_with_retry(
        item["url"], fetch, retries=config.retries, backoff=config.backoff, sleep=sleep)
    try:
        checksum = checksum_path.read_bytes() if checksum_cached else fetch_with_retry(
            item["checksum_url"], fetch, retries=config.retries, backoff=config.backoff, sleep=sleep)
    except SafeFailure as failure:
        # A missing checksum is never classified as a missing/pre-listing archive.
        raise SafeFailure("checksum_unavailable", http_status=failure.http_status) from None
    expected = checksum_digest(checksum, item["filename"])
    if hashlib.sha256(payload).hexdigest() != expected:
        raise SafeFailure("checksum_mismatch")
    if not archive_cached:
        atomic_write(archive, payload, root=config.output_dir)
    if not checksum_cached:
        atomic_write(checksum_path, checksum, root=config.output_dir)
    source = "cache" if archive_cached and checksum_cached else "mixed" if archive_cached or checksum_cached else "network"
    return payload, expected, source


def timestamp_date(timestamp: bytes) -> tuple[date, str]:
    """Interpret only the open-time field; exact integer arithmetic preserves midnight."""
    if not timestamp or not timestamp.isdigit():
        raise SafeFailure("invalid_timestamp")
    value = int(timestamp)
    if value >= 10**14:
        unit, per_day, microseconds = "us", 86_400_000_000, value
    elif value >= 10**11:
        unit, per_day, microseconds = "ms", 86_400_000, value * 1000
    else:
        raise SafeFailure("unsupported_timestamp_magnitude")
    try:
        day = (EPOCH + timedelta(microseconds=microseconds)).date()
    except (OverflowError, ValueError):
        raise SafeFailure("timestamp_out_of_range") from None
    if (day >= UNIT_CHANGE) != (unit == "us"):
        raise SafeFailure("timestamp_unit_2025_boundary_mismatch")
    if value % per_day:
        raise SafeFailure("non_midnight_timestamp")
    return day, unit


def _development_row(raw_line: bytes, day: date) -> list[str]:
    # This function is never called by the sealed-holdout branch.
    try:
        fields = next(csv.reader([raw_line.decode("ascii").rstrip("\r\n")], strict=True))
    except (UnicodeDecodeError, csv.Error, StopIteration):
        raise SafeFailure("invalid_development_schema") from None
    if len(fields) != 12:
        raise SafeFailure("invalid_development_schema")
    from decimal import Decimal, InvalidOperation
    try:
        numbers = [Decimal(fields[i]) for i in (1, 2, 3, 4, 5, 7, 9, 10, 11)]
        if not all(n.is_finite() for n in numbers):
            raise SafeFailure("invalid_development_numeric_field")
        if any(numbers[i] <= 0 for i in range(4)) or any(numbers[i] < 0 for i in (4, 5, 6, 7)):
            raise SafeFailure("invalid_development_numeric_field")
        if not fields[6].isdigit() or not fields[8].isdigit():
            raise SafeFailure("invalid_development_integer_field")
    except (InvalidOperation, ValueError):
        raise SafeFailure("invalid_development_numeric_field") from None
    return [day.isoformat(), *(fields[i] for i in (1, 2, 3, 4, 5, 7, 8, 9, 10))]


def scan_archive(payload: bytes, item: dict) -> tuple[dict, list[list[str]]]:
    """Return safe date coverage and development rows (always [] for holdout).

    The holdout branch partitions bytes once at the first comma and examines only
    that timestamp. It deliberately cannot attest to the uninspected OHLC schema.
    """
    first, last = month_bounds(item["month"])
    coverage = {"rows": 0, "first_date": None, "last_date": None,
                "expected_start": first.isoformat(), "expected_end": last.isoformat(),
                "expected_rows": (last - first).days + 1, "missing_dates": [],
                "duplicate_dates": [], "non_midnight_rows": 0, "out_of_range_dates": [],
                "timestamp_units": [], "schema_scope": "timestamp_only" if item["partition"] == "holdout" else "full_kline"}
    dates, units, development_rows = [], set(), []
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            expected_csv = item["filename"].removesuffix(".zip") + ".csv"
            if len(members) != 1 or members[0].filename != expected_csv:
                raise SafeFailure("invalid_zip_schema")
            with archive.open(members[0]) as source:
                for raw_line in source:
                    coverage["rows"] += 1
                    timestamp, separator, _ = raw_line.partition(b",")
                    if not separator:
                        raise SafeFailure("invalid_timestamp_schema")
                    try:
                        day, unit = timestamp_date(timestamp)
                    except SafeFailure as failure:
                        if failure.code == "non_midnight_timestamp":
                            coverage["non_midnight_rows"] += 1
                        raise
                    units.add(unit)
                    dates.append(day)
                    if not first <= day <= last:
                        coverage["out_of_range_dates"].append(day.isoformat())
                    if item["partition"] == "development":
                        development_rows.append(_development_row(raw_line, day))
    except SafeFailure as failure:
        failure.coverage = coverage
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError):
        raise SafeFailure("invalid_zip", coverage=coverage) from None
    if not dates:
        raise SafeFailure("empty_archive", coverage=coverage)
    unique = set(dates)
    coverage.update(first_date=min(dates).isoformat(), last_date=max(dates).isoformat(),
                    timestamp_units=sorted(units))
    seen = set()
    coverage["duplicate_dates"] = sorted({d.isoformat() for d in dates if d in seen or seen.add(d)})
    coverage["missing_dates"] = [(first + timedelta(days=i)).isoformat()
                                 for i in range((last - first).days + 1) if first + timedelta(days=i) not in unique]
    if coverage["duplicate_dates"]:
        raise SafeFailure("duplicate_dates", coverage=coverage)
    if coverage["out_of_range_dates"]:
        raise SafeFailure("dates_outside_expected_month", coverage=coverage)
    if dates != sorted(dates):
        raise SafeFailure("dates_not_increasing", coverage=coverage)
    # Dates are metadata only; no holdout price survives this function.
    coverage["observed_dates"] = [d.isoformat() for d in dates]
    return coverage, development_rows


def summarize_symbol(records: list[dict]) -> dict:
    ordered = sorted(records, key=lambda record: record["month"])
    verified = [r for r in ordered if r["status"] == "verified"]
    first_record = verified[0] if verified else None
    observed = sorted({d for r in verified for d in r["coverage"]["observed_dates"]})
    first_observed = observed[0] if observed else None
    leading = [r["month"] for r in ordered if r["status"] == "missing_archive"
               and (first_record is None or r["month"] < first_record["month"])]
    candidate_prelisting = bool(first_record and ordered[0]["symbol"] == "SOLUSDT"
                               and ordered[0]["partition"] == "development"
                               and first_record["partition"] == "development")
    leading_days = [] if first_record is None else [d for d in first_record["coverage"]["missing_dates"] if d < first_observed]
    end = month_bounds(ordered[-1]["month"])[1]
    missing_after = []
    if first_observed:
        beginning, present = date.fromisoformat(first_observed), set(observed)
        missing_after = [(beginning + timedelta(days=i)).isoformat()
                         for i in range((end - beginning).days + 1)
                         if (beginning + timedelta(days=i)).isoformat() not in present]
    pending = candidate_prelisting and bool(leading or leading_days)
    # Missing months always keep the overall run incomplete, including possible
    # pre-listing months. Human confirmation is separate from data integrity.
    full = bool(verified) and len(verified) == len(ordered) and not missing_after and not leading_days
    development_eligible = bool(observed) and not missing_after and all(
        r["status"] == "verified" or (pending and r["status"] == "missing_archive" and r["month"] in leading)
        for r in ordered)
    if leading_days and not pending:
        development_eligible = False
    return {"symbol": ordered[0]["symbol"], "requested_archives": len(ordered),
            "verified_archives": len(verified), "first_observed_date": first_observed,
            "last_observed_date": observed[-1] if observed else None,
            "leading_missing_months": leading, "leading_missing_days": leading_days,
            "prelisting_status": "possible_prelisting_requires_manual_confirmation" if pending else "not_assumed",
            "missing_days_after_first_observation": missing_after,
            "complete_requested_range": full,
            "development_csv_eligible": development_eligible}


def run_download(config: DownloadConfig, *, fetch=fetch_url, sleep=time.sleep,
                 log: Callable[[str], None] = print) -> tuple[int, dict]:
    # Resolve only the caller-selected root; links below it are forbidden.
    config = replace(config, output_dir=config.output_dir.expanduser().resolve())
    plan = build_plan(config)
    try:
        validate_output_paths(config, plan)
    except SafeFailure:
        log("Download failed: unsafe_output_path; no archive fetched or cache read.")
        # Do not try to write metadata into the rejected directory tree.
        return 1, {"complete_requested_range": False, "error_code": "unsafe_output_path",
                   "records": [], "development_csv_outputs": []}
    records, dev_rows = [], {}
    for item in plan:
        record = dict(item)
        try:
            payload, digest, source = get_verified_archive(item, config, fetch, sleep)
            record.update(sha256=digest, source=source)
            coverage, rows = scan_archive(payload, item)
            record.update(status="verified", coverage=coverage)
            if item["partition"] == "development":
                dev_rows.setdefault(item["symbol"], []).extend(rows)
        except SafeFailure as failure:
            record.update(status="missing_archive" if failure.code == "http_404" else "failed",
                          error_code=failure.code)
            if failure.http_status is not None:
                record["http_status"] = failure.http_status
            if failure.coverage is not None:
                record["coverage"] = failure.coverage
        except OSError:
            record.update(status="failed", error_code="local_io_error")
        if item["month"] == "2026-09" and record.get("http_status") == 404:
            record["action"] = ("September monthly package unavailable: retry on 2026-10-05 or use a separately "
                                "verified daily fallback. This downloader does not implement daily fallback.")
        records.append(record)
        log(f"{item['symbol']} {item['month']} {item['partition']}: {record['status']}"
            + (f" ({record['error_code']})" if "error_code" in record else ""))
        if "action" in record:
            log(record["action"])
    summaries = [summarize_symbol([r for r in records if r["symbol"] == symbol]) for symbol in config.symbols]
    csv_outputs = []
    for symbol in config.symbols:
        development_records = [r for r in records if r["symbol"] == symbol and r["partition"] == "development"]
        if not development_records:
            continue
        dev_summary = summarize_symbol(development_records)
        if dev_summary["development_csv_eligible"]:
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(CSV_COLUMNS)
            writer.writerows(sorted(dev_rows.get(symbol, []), key=lambda row: row[0]))
            # A range-specific export must not replace a wider earlier export.
            # For --partition all, name only the effective development months.
            path = development_csv_path(config.output_dir, symbol, development_records)
            atomic_write(path, output.getvalue().encode("ascii"), root=config.output_dir)
            csv_outputs.append(str(path))
    complete = all(s["complete_requested_range"] for s in summaries)
    metadata = {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
                "requested_partition": config.partition, "requested_start": config.start,
                "requested_end": config.end, "complete_requested_range": complete,
                "archive_count": len(plan), "records": records, "symbols": summaries,
                "development_csv_outputs": csv_outputs,
                "holdout_policy": "Only first-field timestamp bytes inspected; no holdout OHLC schema or prices decoded/exported"}
    destination = metadata_path(config)
    atomic_write(destination, (json.dumps(metadata, indent=2) + "\n").encode("utf-8"), root=config.output_dir)
    log(f"Coverage complete: {complete}. Metadata: {destination}")
    return (0 if complete else 1), metadata


def main(argv=None, *, fetch=fetch_url, sleep=time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=("development", "holdout", "all"), default="development")
    parser.add_argument("--start", default=FIRST_MONTH, help="First month, YYYY-MM (inclusive)")
    parser.add_argument("--end", default=LAST_MONTH, help="Last month, YYYY-MM (inclusive)")
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS, default=list(SYMBOLS))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Print URLs and counts only; no network or writes")
    args = parser.parse_args(argv)
    config = DownloadConfig(args.output_dir, args.partition, args.start, args.end, tuple(args.symbols), args.retries)
    try:
        plan = build_plan(config)
    except ValueError as error:
        parser.error(str(error))
    if args.dry_run:
        print(json.dumps({"dry_run": True, "counts": {p: sum(i["partition"] == p for i in plan)
                          for p in ("development", "holdout")},
                          "plan": [{k: item[k] for k in ("symbol", "month", "partition", "url", "checksum_url")}
                                   for item in plan]}, indent=2))
        return 0
    try:
        exit_code, _ = run_download(config, fetch=fetch, sleep=sleep)
        return exit_code
    except (OSError, SafeFailure):
        print("Download failed: local_io_error; completeness was not established.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
