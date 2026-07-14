"""TEXTS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column
comments by utilities.model.excel_field):

    'BHL or NO BHL' + '_' + 'Unique identifier'  →  text.identifier
    'Title of the work'                          →  text.title
    'Approximate token count'                    →  text.approximate_token_count
    'Prose or verse'                             →  text_form lookup → text.text_form_id
    'Source type'                                →  text_source_type lookup → text.text_source_type_id
    'Subtype'                                    →  text_source_subtype lookup → text.text_source_subtype_id
"""

import logging
from dataclasses import dataclass
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, SQLModel, select

from utilities.model import Text, TextForm, TextSourceSubtype, TextSourceType

from ..excel import data_rows, header_map, is_empty
from ..fields import CellError, FieldSpec, strict_choice, strict_int, strict_str
from ..report import ImportReport, RowError

log = logging.getLogger(__name__)

SHEET = "TEXTS"

SPECS: dict[str, FieldSpec] = {
    "bhl_prefix": FieldSpec("BHL or NO BHL", strict_choice("BHL", "NO BHL"), required=True),
    "unique_id": FieldSpec("Unique identifier", strict_str, required=True),
    "title": FieldSpec("Title of the work", strict_str),
    "token_count": FieldSpec("Approximate token count", strict_int),
    "form": FieldSpec("Prose or verse", strict_str),
    "source_type": FieldSpec("Source type", strict_str),
    "source_subtype": FieldSpec("Subtype", strict_str),
}


@dataclass(frozen=True)
class TextRow:
    """A fully validated TEXTS row, ready for the database."""

    excel_row: int
    identifier: str
    title: str | None
    approximate_token_count: int | None
    form_label: str | None
    source_type_label: str | None
    source_subtype_label: str | None


def parse_sheet(ws: Worksheet, report: ImportReport) -> list[TextRow]:
    """Phase 1 — validate every row; no database involved.

    All cell errors of a row are reported, not just the first; the row is
    then skipped. Fully empty rows are counted but are not failures.
    Duplicate identifiers fail the later row.
    """
    columns = header_map(ws, [spec.column for spec in SPECS.values()])
    rows: list[TextRow] = []
    first_seen: dict[str, int] = {}

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

        identifier = f"{parsed['bhl_prefix'].replace(' ', '_')}_{parsed['unique_id']}"
        if identifier in first_seen:
            report.errors.append(
                RowError(
                    SHEET,
                    excel_row,
                    "'BHL or NO BHL' + 'Unique identifier'",
                    identifier,
                    f"duplicate identifier (first seen at Excel row {first_seen[identifier]})",
                )
            )
            continue
        first_seen[identifier] = excel_row

        rows.append(
            TextRow(
                excel_row=excel_row,
                identifier=identifier,
                title=parsed["title"],
                approximate_token_count=parsed["token_count"],
                form_label=parsed["form"],
                source_type_label=parsed["source_type"],
                source_subtype_label=parsed["source_subtype"],
            )
        )

    report.parsed += len(rows)
    return rows


def _lookup_ids(
    session: Session, model: type[SQLModel], labels: set[str]
) -> dict[str, int]:
    """Get-or-create lookup rows by label; return label → PK."""
    pk = f"{model.__tablename__}_id"
    ids: dict[str, int] = {}
    for label in sorted(labels):
        existing = session.exec(select(model).where(model.label == label)).first()
        if existing is None:
            existing = model(label=label)
            session.add(existing)
            session.flush()
            log.debug("created %s %r", model.__tablename__, label)
        ids[label] = getattr(existing, pk)
    return ids


def import_rows(session: Session, rows: list[TextRow]) -> int:
    """Phase 2 — insert lookups then text rows. Caller commits."""
    forms = _lookup_ids(session, TextForm, {r.form_label for r in rows if r.form_label})
    types = _lookup_ids(
        session, TextSourceType, {r.source_type_label for r in rows if r.source_type_label}
    )
    subtypes = _lookup_ids(
        session,
        TextSourceSubtype,
        {r.source_subtype_label for r in rows if r.source_subtype_label},
    )

    for row in rows:
        session.add(
            Text(
                identifier=row.identifier,
                title=row.title,
                approximate_token_count=row.approximate_token_count,
                text_form_id=forms[row.form_label] if row.form_label else None,
                text_source_type_id=types[row.source_type_label]
                if row.source_type_label
                else None,
                text_source_subtype_id=subtypes[row.source_subtype_label]
                if row.source_subtype_label
                else None,
            )
        )
    log.info("staged %d text rows for insert", len(rows))
    return len(rows)
