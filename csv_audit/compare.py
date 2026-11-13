"""Record matching and difference categorization."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .csvio import CsvData


_NULL_VALUES = {"null", "none", "nil", "n/a", "na"}


@dataclass
class Comparison:
    categories: dict[str, int]
    differences: list[dict[str, Any]]
    units_considered: int
    header_details: list[dict[str, Any]]


# def _is_blank_or_null(value: str) -> bool:
#     """Recognize empty, whitespace-only, and common null-marker values."""
#     stripped = value.strip()
#     return not stripped or stripped.casefold() in _NULL_VALUES

def _is_blank_after_trim(value: str) -> bool:
    """Return True only when trimming whitespace leaves an empty value."""
    return value.strip() == ""


def _comparison_value(value: str, case_sensitive: bool, trim_whitespace: bool) -> str:
    """Normalize a copy of a value for comparison, never the reported value."""
    if trim_whitespace:
        value = value.strip()
    if not case_sensitive:
        value = value.casefold()
    return value


def _decimal_places(value: str) -> int | None:
    """Return the written decimal-place count for a finite decimal value."""
    try:
        number = Decimal(value)
        if not number.is_finite():
            return None
        return max(0, -number.as_tuple().exponent)
    except InvalidOperation:
        return None


def _entry(
    source_name: str,
    category: str,
    key_columns: tuple[str, ...],
    key: tuple[str, ...],
    column: str,
    record: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "data_source": source_name,
        "category": category,
        "key": dict(zip(key_columns, key)),
        "column": column,
        "record": record or {},
    }


def compare(
    source: CsvData,
    target: CsvData,
    keyed: bool,
    key_columns: tuple[str, ...],
    limit: int | None = None,
    *,
    case_sensitive: bool = False,
    trim_whitespace: bool = True,
    ignore_blank_nulls: bool = True,
) -> Comparison:
    """Compare CSV data while retaining original field strings in report rows.

    Keyed records are paired by key; duplicate keys are paired in input order
    and reported. No-key records are matched as an exact-row multiset in file
    order. The limit applies to comparison units after matching.
    """
    categories: dict[str, int] = defaultdict(int)
    differences: list[dict[str, Any]] = []

        # Compare header positions. If a header exists in the other file at a
    # different position, mark it as moved and don't compare that column.
    header_details: list[dict[str, Any]] = []
    source_positions = {name: i for i, name in enumerate(source.headers)}
    target_positions = {name: i for i, name in enumerate(target.headers)}
    max_columns = max(len(source.headers), len(target.headers))
    comparable_columns: list[tuple[int, str, str]] = []

    for index in range(max_columns):
        source_header = source.headers[index] if index < len(source.headers) else None
        target_header = target.headers[index] if index < len(target.headers) else None

        if source_header == target_header and source_header is not None:
            comparable_columns.append((index, source_header, target_header))
            continue

        moved = (
            (source_header is not None
             and source_header in target_positions
             and target_positions[source_header] != index)
            or
            (target_header is not None
             and target_header in source_positions
             and source_positions[target_header] != index)
        )

        detail = {
            "position": index + 1,
            "file1_header": source_header or "",
            "file2_header": target_header or "",
            "status": "ignored_moved_column" if moved else "compared_by_position",
        }
        header_details.append(detail)

        if moved:
            categories["ignored_moved_column"] += 1
        elif source_header is not None and target_header is not None:
            comparable_columns.append((index, source_header, target_header))


    if keyed:
        if not key_columns:
            raise ValueError("Keyed mode requires at least one key column.")
        for label, data in (("file1", source), ("file2", target)):
            missing = [name for name in key_columns if name not in data.headers]
            if missing:
                raise ValueError(f"{label} is missing key column(s): {', '.join(missing)}")

        source_map: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
        target_map: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)

        for row in source.rows:
            source_map[tuple(row[name] for name in key_columns)].append(row)
        for row in target.rows:
            target_map[tuple(row[name] for name in key_columns)].append(row)

        for file_name, mapping in (
            ("file1", source_map),
            ("file2", target_map),
        ):
            for key, rows in mapping.items():
                if len(rows) > 1:
                    categories["duplicate_key"] += len(rows) - 1
                    for row in rows:
                        differences.append(
                            _entry(file_name, "duplicate_key", key_columns, key, "", row)
                        )

        units: list[
            tuple[tuple[str, ...], dict[str, str] | None, dict[str, str] | None]
        ] = []
        for key in sorted(set(source_map) | set(target_map)):
            left = source_map.get(key, [])
            right = target_map.get(key, [])
            for index in range(max(len(left), len(right))):
                units.append((
                    key,
                    left[index] if index < len(left) else None,
                    right[index] if index < len(right) else None,
                ))
    else:
        # Deterministic exact-row multiset matching; duplicate rows pair in file order.
        target_queues: dict[tuple[str, ...], deque[dict[str, str]]] = defaultdict(deque)
        for row in target.rows:
            signature = tuple(row.get(header, "") for header in target.headers)
            target_queues[signature].append(row)

        target_indices = {id(row): index for index, row in enumerate(target.rows)}
        used_target_indices: set[int] = set()
        units = []

        for row in source.rows:
            signature = tuple(row.get(header, "") for header in source.headers)
            queue = target_queues.get(signature)
            if queue:
                matched = queue.popleft()
                used_target_indices.add(target_indices[id(matched)])
                units.append(((), row, matched))
            else:
                units.append(((), row, None))

        for index, row in enumerate(target.rows):
            if index not in used_target_indices:
                units.append(((), None, row))

    if limit is not None:
        units = units[:limit]

    columns = list(dict.fromkeys(source.headers + target.headers))


    for key, left, right in units:
        if left is None:
            categories["missing_from_source"] += 1
            differences.append(_entry("file2", "missing_from_source", key_columns, key, "", right))
            continue
        if right is None:
            categories["missing_from_target"] += 1
            differences.append(_entry("file1", "missing_from_target", key_columns, key, "", left))
            continue

        # No-key mode only matches identical rows, so it has no cell differences.
        if not keyed:
            continue

        # for column in columns:
            a = left.get(column)
            b = right.get(column)
            if a is None or b is None:
                continue

            # if ignore_blank_nulls and _is_blank_or_null(a) and _is_blank_or_null(b):
            #     continue

            # Ignore only when both values are blank after trimming.
            # Ignore this field if either side is blank after trimming.
            # Literal values such as "NULL" and "N/A" are not blank.
            if ignore_blank_nulls and (
                _is_blank_after_trim(a) or _is_blank_after_trim(b)
            ):
                continue



            value_a = _comparison_value(a, case_sensitive, trim_whitespace)
            value_b = _comparison_value(b, case_sensitive, trim_whitespace)

            if value_a == value_b:
                continue

            categories["different_value"] += 1
            differences.extend([
                _entry("file1", "different_value", key_columns, key, column, left),
                _entry("file2", "different_value", key_columns, key, column, right),
            ])

            # Formatting is an additional category only when values differ
            # literally but compare equal after trim/case normalization.
            format_a = _comparison_value(a, False, True)
            format_b = _comparison_value(b, False, True)
            if format_a == format_b and a != b:
                categories["formatting_difference"] += 1
                differences.extend([
                    _entry("file1", "formatting_difference", key_columns, key, column, left),
                    _entry("file2", "formatting_difference", key_columns, key, column, right),
                ])

            places_a = _decimal_places(a)
            places_b = _decimal_places(b)
            if places_a is not None and places_b is not None and places_a != places_b:
                categories["decimal_places_difference"] += 1
                differences.extend([
                    _entry("file1", "decimal_places_difference", key_columns, key, column, left),
                    _entry("file2", "decimal_places_difference", key_columns, key, column, right),
                ])

        for _, source_column, target_column in comparable_columns:
            a = left.get(source_column)
            b = right.get(target_column)
            if a is None or b is None:
                continue

            if (
                ignore_blank_nulls
                and _is_blank_after_trim(a)
                and _is_blank_after_trim(b)
            ):
                continue

            value_a = _comparison_value(a, case_sensitive, trim_whitespace)
            value_b = _comparison_value(b, case_sensitive, trim_whitespace)

            if value_a == value_b:
                continue

            # Keep the per-file column names in the difference entries.
            display_column = (
                source_column
                if source_column == target_column
                else f"{source_column} <-> {target_column}"
            )
            categories["different_value"] += 1
            differences.extend([
                _entry("file1", "different_value", key_columns, key, source_column, left),
                _entry("file2", "different_value", key_columns, key, target_column, right),
            ])

            places_a = _decimal_places(a)
            places_b = _decimal_places(b)
            if places_a is not None and places_b is not None and places_a != places_b:
                categories["decimal_places_difference"] += 1
                differences.extend([
                    _entry(
                        "file1", "decimal_places_difference",
                        key_columns, key, source_column, left
                    ),
                    _entry(
                        "file2", "decimal_places_difference",
                        key_columns, key, target_column, right
                    ),
                ])


    if len(source.rows) != len(target.rows):
        categories["row_count_difference"] = 1

    malformed_count = len(source.malformed_rows) + len(target.malformed_rows)
    if malformed_count:
        categories["malformed_rows"] = malformed_count

    return Comparison(
        dict(categories),
        differences,
        len(units),
        header_details,
    )

