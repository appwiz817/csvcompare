"""Collision-resistant CSV report generation."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .compare import Comparison
from .config import Config
from .csvio import CsvData


def write_reports(config: Config, source: CsvData, target: CsvData,
                  result: Comparison, keyed: bool, limit: int | None) -> Path:
    """Write exactly summary.csv and differences.csv in a unique directory."""
    config.reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = config.reports / f"{stamp}-{uuid4().hex[:8]}"
    directory.mkdir()

    summary_rows = [
        ("source_path", str(source.path)), ("target_path", str(target.path)),
        ("source_rows", str(len(source.rows))), ("target_rows", str(len(target.rows))),
        ("source_headers", repr(source.headers)), ("target_headers", repr(target.headers)),
        ("delimiter", repr(config.delimiter)), ("mode", "keyed" if keyed else "no-key"),
        ("key_columns", repr(config.key if keyed else ())),
        ("limit", "all" if limit is None else str(limit)),
        ("units_considered", str(result.units_considered)),
    ]
    summary_rows.extend((f"category:{name}", str(count))
                        for name, count in sorted(result.categories.items()))
    with (directory / "summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["item", "value"])
        writer.writerows(summary_rows)

    # Output uses comma delimiters. Record JSON-like repr safely preserves the
    # exact field strings while avoiding ambiguous collisions with metadata.
    with (directory / "differences.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["data_source", "category", "key_fields", "column",
                         "record_headers", "record_values",
                         "other_record_headers", "other_record_values"])
        for item in result.differences:
            record, other = item["record"], item["other"]
            writer.writerow([
                item["data_source"], item["category"], repr(item["key"]),
                item["column"], repr(list(record.keys())), repr(list(record.values())),
                repr(list(other.keys())), repr(list(other.values())),
            ])
    return directory