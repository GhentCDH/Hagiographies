"""EDITIONS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column comments
by utilities.model.excel_field):

    'Title'             →  edition.title
    'Publication year'  →  edition.publication_year (strict integer)
    'Reprint ?'         →  edition.reprint (YES/NO → boolean)
"""

import logging
from dataclasses import dataclass
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session

from utilities.model import Edition

from ..excel import data_rows, header_map, is_empty
from ..fields import CellError, FieldSpec, strict_int, strict_str, strict_yesno
from ..report import ImportReport, RowError

log = logging.getLogger(__name__)

SHEET = "EDITIONS"

SPECS: dict[str, FieldSpec] = {
    "title": FieldSpec("Title", strict_str, required=True),
    "publication_year": FieldSpec("Publication year", strict_int),
    "reprint": FieldSpec("Reprint ?", strict_yesno),
}


@dataclass(frozen=True)
class EditionRow:
    """A fully validated EDITIONS row, ready for the database."""

    excel_row: int
    title: str
    publication_year: int | None
    reprint: bool | None


def parse_sheet(ws: Worksheet, report: ImportReport) -> list[EditionRow]:
    """Phase 1 — validate every row; no database involved."""
    columns = header_map(ws, [spec.column for spec in SPECS.values()])
    rows: list[EditionRow] = []

    for excel_row, values in data_rows(ws):
        if is_empty(values):
            report.skipped_empty.append(excel_row)
            continue

        parsed: dict[str, Any] = {}
        row_ok = True
        for name, spec in SPECS.items():
            raw = values[columns[spec.column]]
            try:
                parsed[name] = spec.parser(raw)
            except CellError as error:
                report.errors.append(
                    RowError(SHEET, excel_row, spec.column, raw, str(error))
                )
                row_ok = False
                continue
            if spec.required and parsed[name] is None:
                report.errors.append(
                    RowError(SHEET, excel_row, spec.column, raw, "required value is missing")
                )
                row_ok = False
        if not row_ok:
            continue

        rows.append(
            EditionRow(
                excel_row=excel_row,
                title=parsed["title"],
                publication_year=parsed["publication_year"],
                reprint=parsed["reprint"],
            )
        )

    report.parsed += len(rows)
    return rows


def import_rows(session: Session, rows: list[EditionRow]) -> int:
    """Phase 2 — insert edition rows (no lookups). Caller commits."""
    for row in rows:
        session.add(
            Edition(
                title=row.title,
                publication_year=row.publication_year,
                reprint=row.reprint,
            )
        )
    log.info("staged %d edition rows for insert", len(rows))
    return len(rows)
