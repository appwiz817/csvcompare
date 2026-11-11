"""Record matching and issue categorization."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .csvio import CsvData


@dataclass
class Comparison:
    categories: dict[str, int]
    differences: list[dict[str, Any]]
    units_considered: int


def _decimal_places(value: str) -> int | None:
    """Return written decimal places for a plain decimal number, else None."""
    try:
        number = Decimal(value)
        if not number.is_finite():
            return None
        return max(0, -number.as_tuple().exponent)
    except InvalidOperation:
        return None


def compare(source: CsvData, target: CsvData, keyed: bool,
            key_columns: tuple[str, ...], limit: int | None = None) -> Comparison:
    """Compare records; preserve original strings in all emitted records."""
    categories: dict[str, int] = defaultdict(int)
    differences: list[dict[str, Any]] = []
    headers_match = source.headers == target.headers
    if not headers_match:
        categories["header_mismatch"] += 1

    if keyed:
        for label, data in (("source", source), ("target", target)):
            absent = [key for key in key_columns if key not in data.headers]
            if absent:
                raise ValueError(f"{label} is missing key column(s): {', '.join(absent)}")
        source_map: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
        target_map: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
        for row in source.rows:
            source_map[tuple(row[k] for k in key_columns)].append(row)
        for row in target.rows:
            target_map[tuple(row[k] for k in key_columns)].append(row)
        for label, mapping in (("source", source_map), ("target", target_map)):
            for key, rows in mapping.items():
                if len(rows) > 1:
                    categories["duplicate_key"] += len(rows) - 1
                    for row in rows:
                        differences.append(_entry(label, "duplicate_key", key_columns,
                                                  key, "", row, None))
        units = []
        for key in sorted(set(source_map) | set(target_map)):
            left, right = source_map.get(key, []), target_map.get(key, [])
            for i in range(max(len(left), len(right))):
                units.append((key, left[i] if i < len(left) else None,
                              right[i] if i < len(right) else None))
    else:
        # Exact row tuples; duplicates are paired in original file order.
        target_queues: dict[tuple[str, ...], deque[dict[str, str]]] = defaultdict(deque)
        for row in target.rows:
            target_queues[tuple(row.get(h, "") for h in target.headers)].append(row)
        used_target: set[int] = set()
        target_indices = {id(row): i for i, row in enumerate(target.rows)}
        units = []
        for row in source.rows:
            signature = tuple(row.get(h, "") for h in source.headers)
            queue = target_queues.get(signature)
            if queue:
                matched = queue.popleft()
                used_target.add(target_indices[id(matched)])
                units.append(((), row, matched))
            else:
                units.append(((), row, None))
        units.extend(((), None, row) for i, row in enumerate(target.rows) if i not in used_target)

    if limit is not None:
        units = units[:limit]

    compared_columns = list(dict.fromkeys(source.headers + target.headers))
    for key, left, right in units:
        if left is None:
            categories["missing_from_source"] += 1
            differences.append(_entry("target", "missing_from_source", key_columns, key, "", right, None))
            continue
        if right is None:
            categories["missing_from_target"] += 1
            differences.append(_entry("source", "missing_from_target", key_columns, key, "", left, None))
            continue
        if not keyed:
            continue
        for column in compared_columns:
            a, b = left.get(column), right.get(column)
            if a is None or b is None:
                continue
            if a == "" or b == "":
                if a != b:
                    categories["empty_value"] += 1
                    differences.extend([
                        _entry("source", "empty_value", key_columns, key, column, left, right),
                        _entry("target", "empty_value", key_columns, key, column, right, left),
                    ])
            if a != b:
                categories["different_value"] += 1
                differences.extend([
                    _entry("source", "different_value", key_columns, key, column, left, right),
                    _entry("target", "different_value", key_columns, key, column, right, left),
                ])
                if a.strip().casefold() == b.strip().casefold():
                    categories["formatting_difference"] += 1
                    cat = "formatting_difference"
                    differences.extend([
                        _entry("source", cat, key_columns, key, column, left, right),
                        _entry("target", cat, key_columns, key, column, right, left),
                    ])
                da, db = _decimal_places(a), _decimal_places(b)
                if da is not None and db is not None and da != db:
                    categories["decimal_places_difference"] += 1
                    differences.extend([
                        _entry("source", "decimal_places_difference", key_columns, key, column, left, right),
                        _entry("target", "decimal_places_difference", key_columns, key, column, right, left),
                    ])

    if len(source.rows) != len(target.rows):
        categories["row_count_difference"] = 1
    categories["malformed_rows"] = len(source.malformed_rows) + len(target.malformed_rows)
    return Comparison(dict(categories), differences, len(units))


def _entry(source_name: str, category: str, keys: tuple[str, ...],
           key: tuple[str, ...], column: str, record: dict[str, str] | None,
           other: dict[str, str] | None) -> dict[str, Any]:
    return {"data_source": source_name, "category": category,
            "key": dict(zip(keys, key)), "column": column,
            "record": record or {}, "other": other or {}}
