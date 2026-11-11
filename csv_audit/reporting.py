"""CSV report generation."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .compare import Comparison
from .config import Config
from .csvio import CsvData


def write_reports(
    config: Config,
    source: CsvData,
    target: CsvData,
    result: Comparison,
    keyed: bool,
    limit: int | None,
) -> Path:
    """Write summary.csv and differences.csv; return their containing directory.

    Report files use comma delimiters. Complete-record fields are named
    ``record__<original header>`` to avoid collisions with report metadata.
    Key fields are named ``key__<key header>``.
    """
    config.reports.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    report_dir = config.reports / f"{timestamp}-{uuid4().hex[:8]}"
    report_dir.mkdir()

    # Summary: one row per item/category.
    summary_rows = [
        ("source_path", str(source.path)),
        ("target_path", str(target.path)),
        ("source_rows", str(len(source.rows))),
        ("target_rows", str(len(target.rows))),
        ("source_headers", repr(source.headers)),
        ("target_headers", repr(target.headers)),
        ("delimiter", repr(config.delimiter)),
        ("mode", "keyed" if keyed else "no-key"),
        ("key_columns", repr(config.key if keyed else ())),
        ("limit", "all" if limit is None else str(limit)),
        ("units_considered", str(result.units_considered)),
    ]
    summary_rows.extend(
        (f"category:{name}", str(count))
        for name, count in sorted(result.categories.items())
    )

    with (report_dir / "summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.writer(file)
        writer.writerow(["item", "value"])
        writer.writerows(summary_rows)

    # Key columns and complete-record columns are separate. Prefixes keep
    # report headers unique even when input headers match metadata names.
    key_columns = list(config.key) if keyed else []
    record_headers = list(dict.fromkeys(source.headers + target.headers))

    fieldnames = (
        ["data_source", "category"]
        + [f"key__{name}" for name in key_columns]
        + ["issue_column", "issue_column_value"]
        + [f"record__{name}" for name in record_headers]
    )

    with (report_dir / "differences.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for item in result.differences:
            record = item.get("record") or {}
            issue_column = item.get("column", "") or ""

            row: dict[str, str] = {
                "data_source": (
                    "file1" if item.get("data_source") == "source" else "file2"
                ),
                "category": item.get("category", ""),
                "issue_column": issue_column,
                "issue_column_value": (
                    record.get(issue_column, "") if issue_column else ""
                ),
            }

            key_values = item.get("key") or {}
            for name in key_columns:
                row[f"key__{name}"] = key_values.get(name, "")

            for name in record_headers:
                row[f"record__{name}"] = record.get(name, "")

            writer.writerow(row)

    return report_dir
