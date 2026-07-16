"""Workbook access: sheet lookup, header verification, row iteration.

Sheet and header names are matched on their stripped form because the
workbook contains e.g. a ' MANUSCRIPTS' sheet (leading space) and headers
with trailing spaces. A missing sheet or header is a fatal error — the
workbook layout is a contract, not something to guess around.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


class WorkbookError(RuntimeError):
    """The workbook does not match the expected layout (fatal, exit 2)."""


def load(path: Path) -> Workbook:
    if not path.exists():
        raise WorkbookError(f"workbook not found: {path}")
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def sheet(workbook: Workbook, name: str) -> Worksheet:
    """Find a sheet by stripped name."""
    for candidate in workbook.sheetnames:
        if candidate.strip() == name:
            return workbook[candidate]
    raise WorkbookError(
        f"sheet {name!r} not found; workbook has {workbook.sheetnames}"
    )


def _normalize_header(header: str) -> str:
    """Collapse all whitespace runs (incl. non-breaking spaces) to one space.

    The workbook has headers like 'Likely\\xa0use of a copy of Manuscript 3?'
    where a non-breaking space stands in for a regular one.
    """
    return re.sub(r"\s+", " ", header).strip()


def header_map(ws: Worksheet, expected: list[str]) -> dict[str, int]:
    """Map each expected header to its 0-based column index.

    Headers are matched on their whitespace-normalized form (row 1). Every
    expected header must be present.
    """
    first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    positions: dict[str, int] = {}
    for index, header in enumerate(first_row):
        if header is None:
            continue
        positions.setdefault(_normalize_header(str(header)), index)
    missing = [h for h in expected if _normalize_header(h) not in positions]
    if missing:
        raise WorkbookError(f"sheet {ws.title.strip()!r} is missing headers: {missing}")
    return {h: positions[_normalize_header(h)] for h in expected}


def data_rows(ws: Worksheet) -> Iterator[tuple[int, tuple[Any, ...]]]:
    """Yield (excel_row_number, values) for every row below the header."""
    for number, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        yield number, values


def is_empty(values: tuple[Any, ...]) -> bool:
    """A row with no meaningful content in any cell."""
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in values)
