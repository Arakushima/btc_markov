#!/usr/bin/env python3
"""Exact, offline reconciliation of explicitly named 2020-2023 development CSVs.

Never discovers a latest file. Never computes returns or model statistics.
All dates in all inputs are checked before any observed price is converted.
Tolerance flags are descriptive; even within-tolerance exact differences remain
reported and produce a nonzero reconciliation status.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
START, END = date(2020, 1, 1), date(2023, 12, 31)
FIELDS = {"open": "open", "high": "high", "low": "low", "close": "close",
          "volume": "volume", "quote_volume": "dollar_volume",
          "taker_buy_quote": "taker_buy_dollar_volume"}
# Declared before seeing any input. Units are those of each compared column.
# exact equality is the primary criterion; these flags do not excuse a mismatch.
FIXED_TOLERANCES = {
    field: {"absolute": "0.00000001", "relative": "0"}
    for field in ("open", "high", "low", "close", "volume")
}
FIXED_TOLERANCES.update({
    "quote_volume": {"absolute": "0.0001", "relative": "0"},
    "taker_buy_quote": {"absolute": "0.0001", "relative": "0"},
})
DIFFERENCE_COLUMNS = ("asset", "date", "kind", "field", "development_value",
                      "mentor_value", "absolute_difference", "fixed_tolerance", "within_tolerance")


class InputRejected(Exception):
    """Fixed codes intentionally avoid echoing unvalidated source row values."""


@dataclass(frozen=True)
class AuditConfig:
    development_dir: Path
    mentor_csv: Path
    output_dir: Path
    max_differences: int = 100


def checked_path(path: Path, *, require_file: bool = False) -> Path:
    """Reject symlinks and any path component naming a holdout area."""
    path = path.expanduser().absolute()
    if any("holdout" in part.casefold() for part in path.parts):
        raise InputRejected("holdout_path_rejected")
    if ".." in path.parts:
        raise InputRejected("parent_path_traversal_rejected")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise InputRejected("symlink_path_rejected")
    if require_file and not path.is_file():
        raise InputRejected("required_input_file_missing")
    return path


def input_paths(config: AuditConfig) -> dict[str, Path]:
    directory = checked_path(config.development_dir)
    return {symbol: checked_path(directory / f"{symbol}_1d_2020-01_2023-12.csv", require_file=True)
            for symbol in SYMBOLS}


def _date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise InputRejected("invalid_date_format")
    try:
        day = date.fromisoformat(value)
    except ValueError:
        raise InputRejected("invalid_calendar_date") from None
    if day >= date(2024, 1, 1):
        raise InputRejected("future_date_rejected_before_price_conversion")
    if day < START:
        raise InputRejected("date_before_development_range")
    return day


def _load_unconverted(path: Path, *, symbol: str | None = None) -> tuple[dict, dict]:
    """Read strings and date keys only; defer all price/volume conversion."""
    checked_path(path, require_file=True)
    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputRejected("invalid_csv_encoding") from None
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    required = {"date", *FIELDS} if symbol else {"inst", "asof", *FIELDS.values()}
    try:
        header = reader.fieldnames
    except csv.Error:
        raise InputRejected("invalid_csv_header") from None
    if not header or len(header) != len(set(header)) or not required.issubset(header):
        raise InputRejected("invalid_csv_header")
    rows, total, excluded = {}, 0, 0
    try:
        for row in reader:
            total += 1
            if None in row or any(value is None for value in row.values()):
                raise InputRejected("invalid_csv_row_schema")
            # Even an unselected mentor asset cannot hide a future-dated row.
            day = _date(row["date"] if symbol else row["asof"])
            asset = symbol if symbol else row["inst"]
            if asset not in SYMBOLS:
                excluded += 1
                continue
            values = {field: row[field if symbol else mentor_field]
                      for field, mentor_field in FIELDS.items()}
            rows.setdefault((asset, day), []).append({"values": values, "csv_line": reader.line_num})
    except csv.Error:
        raise InputRejected("invalid_csv_syntax") from None
    if not total:
        raise InputRejected("empty_input_csv")
    return rows, {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
                  "bytes": len(payload), "rows": total, "excluded_other_assets": excluded}


def parse_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise InputRejected("invalid_numeric_field") from None
    if not number.is_finite():
        raise InputRejected("nonfinite_numeric_field")
    return number


def exact_subtract(left: Decimal, right: Decimal) -> Decimal:
    """Choose enough working digits for exact decimal subtraction, without floats."""
    with localcontext() as context:
        context.prec = max(left.adjusted(), right.adjusted(), 0) - min(
            left.as_tuple().exponent, right.as_tuple().exponent, 0) + 4
        return left - right


def _decimal_string(number: Decimal) -> str:
    return format(number, "f")


def _coverage(rows: dict, symbol: str) -> dict:
    selected = {day: values for (asset, day), values in rows.items() if asset == symbol}
    dates = sorted(selected)
    duplicates = [{"date": day.isoformat(), "count": len(values),
                   "csv_lines": [v["csv_line"] for v in values]}
                  for day, values in sorted(selected.items()) if len(values) > 1]
    gaps = []
    if dates:
        present = set(dates)
        gaps = [(dates[0] + timedelta(days=i)).isoformat()
                for i in range((dates[-1] - dates[0]).days + 1)
                if dates[0] + timedelta(days=i) not in present]
    return {"rows": sum(len(v) for v in selected.values()), "unique_dates": len(dates),
            "first_date": dates[0].isoformat() if dates else None,
            "last_date": dates[-1].isoformat() if dates else None,
            "duplicates": duplicates, "gaps_within_observed_span": gaps,
            "leading_absent_calendar_days": (dates[0] - START).days if dates else None,
            "trailing_absent_calendar_days": (END - dates[-1]).days if dates else None,
            "boundary_interpretation": "Coverage only; no exchange listing date inferred"}


class DifferenceSample:
    def __init__(self, limit: int):
        self.limit, self.total, self.rows = limit, 0, []

    def add(self, *, asset: str, day: date | str, kind: str, **fields):
        self.total += 1
        if len(self.rows) < self.limit:
            self.rows.append({"asset": asset, "date": str(day), "kind": kind, **fields})


def reconcile(config: AuditConfig) -> tuple[int, dict, list[dict]]:
    """Read development-only inputs; return (0 exact/1 differences, report, sample).

    Invalid paths, dates or schemas raise InputRejected. Duplicate keys are
    reported and excluded from field comparison; no arbitrary first/last row wins.
    The function does not write files. Dates are checked across every input first.
    """
    if not 1 <= config.max_differences <= 1000:
        raise InputRejected("max_differences_must_be_1_to_1000")
    paths = input_paths(config)
    mentor_path = checked_path(config.mentor_csv, require_file=True)
    checked_path(config.output_dir)
    development, provenance = {}, {}
    for symbol, path in paths.items():
        rows, details = _load_unconverted(path, symbol=symbol)
        development.update(rows)
        provenance[symbol] = details
    mentor, provenance["mentor"] = _load_unconverted(mentor_path)
    # Only after all source dates passed are observed numeric values converted.
    converted = {}
    for source, rows in (("development", development), ("mentor", mentor)):
        converted[source] = {
            key: {field: parse_decimal(values[0]["values"][field]) for field in FIELDS}
            for key, values in rows.items() if len(values) == 1
        }
    sample, assets = DifferenceSample(config.max_differences), {}
    for symbol in SYMBOLS:
        dev_dates = {day for asset, day in development if asset == symbol}
        mentor_dates = {day for asset, day in mentor if asset == symbol}
        common = dev_dates & mentor_dates
        comparable = sorted(day for day in common if len(development[(symbol, day)]) == len(mentor[(symbol, day)]) == 1)
        excluded_duplicates = sorted(common - set(comparable))
        field_results = {}
        for field in FIELDS:
            exact, outside, maximum, total_difference = 0, 0, Decimal(0), Decimal(0)
            largest_difference = None
            tolerance = Decimal(FIXED_TOLERANCES[field]["absolute"])
            for day in comparable:
                left, right = converted["development"][(symbol, day)][field], converted["mentor"][(symbol, day)][field]
                difference = exact_subtract(left, right).copy_abs()
                if difference > maximum:
                    # Independent of bounded CSV sampling; ties retain the first
                    # (earliest) date because comparable dates are sorted.
                    largest_difference = {"date": day.isoformat(),
                                          "development_value": _decimal_string(left),
                                          "mentor_value": _decimal_string(right),
                                          "absolute_difference": _decimal_string(difference)}
                maximum = max(maximum, difference)
                total_difference = exact_subtract(total_difference, difference.copy_negate())
                exact += left == right
                outside += difference > tolerance
                if left != right:
                    sample.add(asset=symbol, day=day, kind="field_difference", field=field,
                               development_value=_decimal_string(left), mentor_value=_decimal_string(right),
                               absolute_difference=_decimal_string(difference),
                               fixed_tolerance=_decimal_string(tolerance), within_tolerance=difference <= tolerance)
            field_results[field] = {"mentor_field": FIELDS[field], "compared_dates": len(comparable),
                                    "exact_matches": exact, "exact_mismatches": len(comparable) - exact,
                                    "within_fixed_tolerance_including_exact": len(comparable) - outside,
                                    "outside_fixed_tolerance": outside,
                                    "maximum_absolute_difference": _decimal_string(maximum),
                                    "largest_difference": largest_difference,
                                    "sum_absolute_difference": _decimal_string(total_difference)}
        coverage = {"development": _coverage(development, symbol), "mentor": _coverage(mentor, symbol)}
        only_development, only_mentor = sorted(dev_dates - mentor_dates), sorted(mentor_dates - dev_dates)
        for day in only_development:
            sample.add(asset=symbol, day=day, kind="date_only_in_development")
        for day in only_mentor:
            sample.add(asset=symbol, day=day, kind="date_only_in_mentor")
        for source, description in coverage.items():
            for duplicate in description["duplicates"]:
                sample.add(asset=symbol, day=duplicate["date"], kind=f"duplicate_key_{source}")
            for gap in description["gaps_within_observed_span"]:
                sample.add(asset=symbol, day=gap, kind=f"internal_calendar_gap_{source}")
        close_matches = bool(comparable) and field_results["close"]["exact_mismatches"] == 0
        other_differences = sum(value["exact_mismatches"] for field, value in field_results.items() if field != "close")
        history_identical = dev_dates == mentor_dates
        unambiguous = not coverage["development"]["duplicates"] and not coverage["mentor"]["duplicates"]
        gap_free = not coverage["development"]["gaps_within_observed_span"] and not coverage["mentor"]["gaps_within_observed_span"]
        assets[symbol] = {"coverage": coverage, "common_dates": len(common),
                          "compared_unique_dates": len(comparable),
                          "common_dates_excluded_due_to_duplicates": [day.isoformat() for day in excluded_duplicates],
                          "missing_from_development": [day.isoformat() for day in only_mentor],
                          "missing_from_mentor": [day.isoformat() for day in only_development],
                          "fields": field_results,
                          "summary": {"close_exact_on_compared_common_dates": close_matches,
                                      "other_field_exact_difference_count": other_differences,
                                      "observed_history_identical": history_identical,
                                      "common_comparison_unambiguous": unambiguous,
                                      "exact_reconciliation": close_matches and not other_differences and history_identical and unambiguous and gap_free}}
    exact_all = all(asset["summary"]["exact_reconciliation"] for asset in assets.values())
    report = {"schema_version": 1, "scope": "development_only_2020_2023",
              "expected_range": {"start": START.isoformat(), "end": END.isoformat()},
              "input_selection": "Exact SYMBOL_1d_2020-01_2023-12.csv filenames; no discovery or latest-file selection",
              "fixed_tolerances": FIXED_TOLERANCES,
              "tolerance_policy": "Absolute tolerance only, fixed before input; exact mismatches are never silently accepted",
              "numeric_policy": "Decimal comparison and exact subtraction; no binary floats",
              "history_policy": "Compare unambiguous common dates; report unique histories separately; no listing-date judgment",
              "inputs": provenance, "assets": assets, "exact_reconciliation": exact_all,
              "difference_records_total": sample.total, "difference_records_saved": len(sample.rows),
              "difference_sample_limit": config.max_differences,
              "difference_sample_truncated": sample.total > len(sample.rows)}
    return (0 if exact_all else 1), report, sample.rows


def _write(path: Path, payload: bytes) -> None:
    checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    checked_path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as file:
            temporary = Path(file.name)
            file.write(payload)
        checked_path(path)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_report(config: AuditConfig, report: dict, differences: list[dict]) -> tuple[Path, Path]:
    output = checked_path(config.output_dir)
    report_path = checked_path(output / "development_reconciliation.json")
    differences_path = checked_path(output / "development_differences.csv")
    # Do not allow a chosen output target to overwrite any source input.
    inputs = {Path(value["path"]).resolve() for value in report["inputs"].values()}
    if report_path.resolve() in inputs or differences_path.resolve() in inputs:
        raise InputRejected("output_must_not_replace_input")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=DIFFERENCE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(differences)
    _write(differences_path, buffer.getvalue().encode("utf-8"))
    _write(report_path, (json.dumps(report, indent=2) + "\n").encode("utf-8"))
    return report_path, differences_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-dir", type=Path, required=True)
    parser.add_argument("--mentor-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/data_audit"))
    parser.add_argument("--max-differences", type=int, default=100)
    args = parser.parse_args(argv)
    config = AuditConfig(args.development_dir, args.mentor_csv, args.output_dir, args.max_differences)
    try:
        status, report, differences = reconcile(config)
        report_path, _ = write_report(config, report, differences)
    except InputRejected as failure:
        print(f"Input rejected: {failure}. No price comparison published.")
        return 2
    except OSError:
        print("Input/output error. No successful reconciliation claimed.")
        return 2
    for symbol, asset in report["assets"].items():
        summary = asset["summary"]
        print(f"{symbol}: common dates={asset['compared_unique_dates']}; "
              f"close exactly matches={summary['close_exact_on_compared_common_dates']}; "
              f"other-field differences={summary['other_field_exact_difference_count']}; "
              f"only development={len(asset['missing_from_mentor'])}; "
              f"only mentor={len(asset['missing_from_development'])}")
    print(f"Exact reconciliation: {report['exact_reconciliation']}. Report: {report_path}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
