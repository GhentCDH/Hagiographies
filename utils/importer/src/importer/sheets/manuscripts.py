"""MANUSCRIPTS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column comments
by utilities.model.excel_field):

    'BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text'
                                     →  manuscript.identifier (e.g. BHL_29-4)
    'Title'                          →  manuscript.title
    'Preservation status of manuscript copy'
                                     →  manuscript_preservation_status lookup
    'Manuscript holding institution' →  manuscript_holding_institution lookup

Documented exceptions to strict no-normalization (user decisions):
  - preservation status is matched case-insensitively to Lost/Preserved;
  - institution names differing only in case/whitespace merge into one row,
    the most frequent raw spelling wins;
  - an institution of exactly 'N/A' means no institution (NULL FK).
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from utilities.model import (
    Manuscript,
    ManuscriptHoldingInstitution,
    ManuscriptPreservationStatus,
)

from ..excel import data_rows, header_map, is_empty
from ..fields import CellError, FieldSpec, strict_canonical, strict_choice, strict_str
from ..report import ImportReport, RowError

log = logging.getLogger(__name__)

SHEET = "MANUSCRIPTS"

SPECS: dict[str, FieldSpec] = {
    "bhl_prefix": FieldSpec("BHL or NO BHL", strict_choice("BHL", "NO BHL"), required=True),
    "copy_id": FieldSpec(
        "Manuscript copy unique identifier per text", strict_str, required=True
    ),
    "title": FieldSpec("Title", strict_str),
    "preservation": FieldSpec(
        "Preservation status of manuscript copy", strict_canonical("Lost", "Preserved")
    ),
    "institution": FieldSpec("Manuscript holding institution", strict_str),
}


@dataclass(frozen=True)
class ManuscriptRow:
    """A fully validated MANUSCRIPTS row, ready for the database."""

    excel_row: int
    identifier: str
    title: str | None
    preservation_label: str | None
    institution_name: str | None


def parse_sheet(ws: Worksheet, report: ImportReport) -> list[ManuscriptRow]:
    """Phase 1 — validate every row; no database involved."""
    columns = header_map(ws, [spec.column for spec in SPECS.values()])
    rows: list[ManuscriptRow] = []
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

        identifier = f"{parsed['bhl_prefix'].replace(' ', '_')}_{parsed['copy_id']}"
        if identifier in first_seen:
            report.errors.append(
                RowError(
                    SHEET,
                    excel_row,
                    "'BHL or NO BHL' + 'Manuscript copy unique identifier per text'",
                    identifier,
                    f"duplicate identifier (first seen at Excel row {first_seen[identifier]})",
                )
            )
            continue
        first_seen[identifier] = excel_row

        institution = parsed["institution"]
        if institution == "N/A":
            institution = None

        rows.append(
            ManuscriptRow(
                excel_row=excel_row,
                identifier=identifier,
                title=parsed["title"],
                preservation_label=parsed["preservation"],
                institution_name=institution,
            )
        )

    report.parsed += len(rows)
    return rows


def _canonical_institutions(rows: list[ManuscriptRow]) -> dict[str, str]:
    """Map each raw institution name to its canonical (deduplicated) form.

    Names equal after whitespace-collapse + casefold are one institution;
    the most frequent raw spelling wins (ties: first seen wins, since
    Counter.most_common preserves insertion order).
    """
    spellings: dict[str, Counter] = {}
    for row in rows:
        if row.institution_name:
            key = re.sub(r"\s+", " ", row.institution_name).casefold()
            spellings.setdefault(key, Counter())[row.institution_name] += 1
    canonical_by_key = {
        key: counts.most_common(1)[0][0] for key, counts in spellings.items()
    }
    mapping = {}
    for counts in spellings.values():
        for raw in counts:
            mapping[raw] = canonical_by_key[re.sub(r"\s+", " ", raw).casefold()]
    for key, counts in spellings.items():
        if len(counts) > 1:
            log.info(
                "merged institution spellings %s → %r",
                sorted(counts), canonical_by_key[key],
            )
    return mapping


def import_rows(session: Session, rows: list[ManuscriptRow]) -> int:
    """Phase 2 — insert lookups then manuscript rows. Caller commits."""
    canonical = _canonical_institutions(rows)

    statuses: dict[str, int] = {}
    for label in sorted({r.preservation_label for r in rows if r.preservation_label}):
        existing = session.exec(
            select(ManuscriptPreservationStatus).where(
                ManuscriptPreservationStatus.label == label
            )
        ).first()
        if existing is None:
            existing = ManuscriptPreservationStatus(label=label)
            session.add(existing)
            session.flush()
        statuses[label] = existing.manuscript_preservation_status_id

    institutions: dict[str, int] = {}
    for name in sorted(set(canonical.values())):
        existing = session.exec(
            select(ManuscriptHoldingInstitution).where(
                ManuscriptHoldingInstitution.name == name
            )
        ).first()
        if existing is None:
            existing = ManuscriptHoldingInstitution(name=name)
            session.add(existing)
            session.flush()
        institutions[name] = existing.manuscript_holding_institution_id

    for row in rows:
        session.add(
            Manuscript(
                identifier=row.identifier,
                title=row.title,
                manuscript_preservation_status_id=statuses[row.preservation_label]
                if row.preservation_label
                else None,
                manuscript_holding_institution_id=institutions[
                    canonical[row.institution_name]
                ]
                if row.institution_name
                else None,
            )
        )
    log.info("staged %d manuscript rows for insert", len(rows))
    return len(rows)
