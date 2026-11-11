"""CSV input reading without rewriting or normalizing field contents."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


class InputError(ValueError):
    """Raised when an input CSV cannot be read or has an invalid shape."""


@dataclass
class CsvData:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]]
    malformed_rows: list[tuple[int, list[str]]]


def read_csv(path: Path, delimiter: str) -> CsvData:
    """Read records as strings and record rows with the wrong field count."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter)
            try:
                headers = next(reader)
            except StopIteration:
                raise InputError(f"{path}: file is empty; a header row is required.")
            if not headers or any(name == "" for name in headers):
                raise InputError(f"{path}: headers must be nonempty.")
            if len(set(headers)) != len(headers):
                raise InputError(f"{path}: duplicate header names are ambiguous.")
            rows, malformed = [], []
            for line_number, fields in enumerate(reader, start=2):
                if len(fields) != len(headers):
                    malformed.append((line_number, fields))
                    continue
                rows.append(dict(zip(headers, fields)))
    except OSError as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc
    except csv.Error as exc:
        raise InputError(f"Invalid CSV in {path}: {exc}") from exc
    return CsvData(path, headers, rows, malformed)
