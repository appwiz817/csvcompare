"""Write summary, complete differences, and representative example reports."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .compare import Comparison
from .config import Config
from .csvio import CsvData


def _report_row(
    item: dict,
    key_columns: list[str],
    record_headers: list[str],
) -> dict[str, str]:
    """Convert one comparison entry into a flat CSV row."""
    record = item.get("record") or {}
    issue_column = item.get("column") or ""

    row = {
        "data_source": item.get("data_source", ""),
        "category": item.get("category", ""),
        "issue_column": issue_column,
        "issue_column_value": record.get(issue_column, "") if issue_column else "",
    }
    for name in key_columns:
        row[f"key__{name}"] = (item.get("key") or {}).get(name, "")
    for name in record_headers:
        row[f"record__{name}"] = record.get(name, "")
    return row


def write_reports(
    config: Config,
    source: CsvData,
    target: CsvData,
    result: Comparison,
    keyed: bool,
    limit: int | None,
    *,
    case_sensitive: bool = False,
    trim_whitespace: bool = True,
    ignore_blank_nulls: bool = True,
) -> Path:
    """Write exactly three CSV reports and return their directory."""
    config.reports.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    report_dir = config.reports / f"{timestamp}-{uuid4().hex[:8]}"
    report_dir.mkdir()

    source_header_set = set(source.headers)
    target_header_set = set(target.headers)
    headers_only_file1 = [name for name in source.headers if name not in target_header_set]
    headers_only_file2 = [name for name in target.headers if name not in source_header_set]

    summary_rows = [
        ("source_path", str(source.path)),
        ("target_path", str(target.path)),
        ("source_rows", str(len(source.rows))),
        ("target_rows", str(len(target.rows))),
        ("source_headers", repr(source.headers)),
        ("target_headers", repr(target.headers)),
        ("headers_only_in_file1", repr(headers_only_file1)),
        ("headers_only_in_file2", repr(headers_only_file2)),
        ("headers_differ_in_order", str(source.headers != target.headers)),
        ("delimiter", repr(config.delimiter)),
        ("mode", "keyed" if keyed else "no-key"),
        ("key_columns", repr(config.key if keyed else ())),
        ("limit", "all" if limit is None else str(limit)),
        ("units_considered", str(result.units_considered)),
        ("case_sensitive", str(case_sensitive)),
        ("trim_whitespace", str(trim_whitespace)),
        ("ignore_blank_nulls", str(ignore_blank_nulls)),
        # ("blank_null_rule", "empty, whitespace-only, null, none, nil, n/a, na"),
        ("blank_rule", "ignore a field only when both values are empty after trimming whitespace"),

    ]

    summary_rows.append(("header_position_details", repr(result.header_details)))


    summary_rows.extend(
        (f"category:{name}", str(count))
        for name, count in sorted(result.categories.items())
    )

    with (report_dir / "summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["item", "value"])
        writer.writerows(summary_rows)

    key_columns = list(config.key) if keyed else []
    record_headers = list(dict.fromkeys(source.headers + target.headers))
    fieldnames = (
        ["data_source", "category"]
        + [f"key__{name}" for name in key_columns]
        + ["issue_column", "issue_column_value"]
        + [f"record__{name}" for name in record_headers]
    )

    # Complete differences: one row per side of a matched difference.
    with (report_dir / "differences.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in result.differences:
            writer.writerow(_report_row(item, key_columns, record_headers))

    # One example per category and issue column. Matched examples retain both
    # sides, because each side has its own differences.csv row.
    examples: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in result.differences:
        signature = (item.get("category", ""), item.get("column", ""))
        if signature not in seen:
            seen.add(signature)
            examples.append(item)

    with (report_dir / "examples.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for example in examples:
            signature = (example.get("category", ""), example.get("column", ""))
            writer.writerow(_report_row(example, key_columns, record_headers))

            # Include the other side of the same matched example, if present.
            for candidate in result.differences:
                if (
                    candidate is example
                    or candidate.get("category") != signature[0]
                    or candidate.get("column") != signature[1]
                    or candidate.get("key") != example.get("key")
                    or candidate.get("data_source") == example.get("data_source")
                ):
                    continue
                writer.writerow(_report_row(candidate, key_columns, record_headers))
                break

    return report_dir
