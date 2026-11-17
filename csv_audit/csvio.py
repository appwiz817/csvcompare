"""CSV input reading without changing input files or field values."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


class InputError(ValueError):
    """Raised when an input CSV cannot be read or has an invalid header."""


@dataclass
class CsvData:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]]
    malformed_rows: list[tuple[int, list[str]]]
    delimiter: str


def read_csv(path: Path, delimiter: str | None = None) -> CsvData:
    """Read a CSV as strings; detect the delimiter from the first row if omitted."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            if delimiter is None:
                first_row = stream.readline()
                if not first_row:
                    raise InputError(
                        f"{path}: file is empty; a header row is required."
                    )

                try:
                    dialect = csv.Sniffer().sniff(first_row, delimiters=",\t;|")
                except csv.Error as exc:
                    raise InputError(
                        f"{path}: could not detect delimiter from the first row."
                    ) from exc

                delimiter = dialect.delimiter
                stream.seek(0)

            reader = csv.reader(stream, delimiter=delimiter)
            try:
                headers = next(reader)
            except StopIteration as exc:
                raise InputError(
                    f"{path}: file is empty; a header row is required."
                ) from exc

            if not headers or any(header == "" for header in headers):
                raise InputError(f"{path}: headers must be nonempty.")
            if len(set(headers)) != len(headers):
                raise InputError(
                    f"{path}: duplicate header names are ambiguous."
                )

            rows: list[dict[str, str]] = []
            malformed: list[tuple[int, list[str]]] = []
            for line_number, values in enumerate(reader, start=2):
                if len(values) != len(headers):
                    malformed.append((line_number, values))
                    continue
                rows.append(dict(zip(headers, values)))

    except OSError as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc
    except csv.Error as exc:
        raise InputError(f"Invalid CSV in {path}: {exc}") from exc

    return CsvData(path, headers, rows, malformed, delimiter)
