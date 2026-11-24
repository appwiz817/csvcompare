"""Write summary, complete differences, and representative example reports."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .compare import Comparison
from .config import Config
from .csvio import CsvData


def _report_columns(
    key_columns: list[str],
    record_headers: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Build unique report headers and map original input headers to them."""
    metadata = (
        ["data_source", "category"]
        + [f"k_{name}" for name in key_columns]
        + ["diff_column", "diff_value"]
    )
    used = set(metadata)
    record_columns: dict[str, str] = {}

    for name in record_headers:
        if name not in used:
            record_columns[name] = name
            used.add(name)

    for name in record_headers:
        if name in record_columns:
            continue
        output_name = f"source_{name}"
        while output_name in used:
            output_name = f"source_{output_name}"
        record_columns[name] = output_name
        used.add(output_name)

    return metadata + [record_columns[name] for name in record_headers], record_columns


def _report_row(
    item: dict,
    key_columns: list[str],
    record_headers: list[str],
    record_columns: dict[str, str],
) -> dict[str, str]:
    """Convert one comparison entry into a flat CSV row."""
    record = item.get("record") or {}
    diff_column = item.get("column") or ""

    row = {
        "data_source": item.get("data_source", ""),
        "category": item.get("category", ""),
        "diff_column": diff_column,
        "diff_value": record.get(diff_column, "") if diff_column else "",
    }
    for name in key_columns:
        row[f"k_{name}"] = (item.get("key") or {}).get(name, "")
    for name in record_headers:
        row[record_columns[name]] = record.get(name, "")
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
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    report_dir = config.reports / timestamp
    suffix = 2
    while True:
        try:
            report_dir.mkdir()
            break
        except FileExistsError:
            report_dir = config.reports / f"{timestamp}-{suffix}"
            suffix += 1
    report_timestamp = report_dir.name
    summary_path = report_dir / f"summary-{report_timestamp}.csv"
    differences_path = report_dir / f"differences-{report_timestamp}.csv"
    examples_path = report_dir / f"examples-{report_timestamp}.csv"

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

    with summary_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["item", "value"])
        writer.writerows(summary_rows)

    key_columns = list(config.key) if keyed else []
    record_headers = list(dict.fromkeys(source.headers + target.headers))
    fieldnames, record_columns = _report_columns(key_columns, record_headers)

    # Complete differences: one row per side of a matched difference.
    with differences_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter=source.delimiter,
        )
        writer.writeheader()
        for item in result.differences:
            writer.writerow(
                _report_row(item, key_columns, record_headers, record_columns)
            )

    # Keep one representative issue per category. Matched examples retain both
    # sides, because each side has its own differences.csv row.
    examples: list[dict] = []
    seen: set[str] = set()
    for item in result.differences:
        category = item.get("category", "")
        if category not in seen:
            seen.add(category)
            examples.append(item)

    with examples_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter=source.delimiter,
        )
        writer.writeheader()
        for example in examples:
            writer.writerow(
                _report_row(example, key_columns, record_headers, record_columns)
            )

            # Include the other side of the same matched example, if present.
            for candidate in result.differences:
                if (
                    candidate is example
                    or candidate.get("category") != example.get("category")
                    or candidate.get("key") != example.get("key")
                    or candidate.get("data_source") == example.get("data_source")
                ):
                    continue
                writer.writerow(
                    _report_row(candidate, key_columns, record_headers, record_columns)
                )
                break

    return report_dir
