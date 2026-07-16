"""EDITIONS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column comments
by utilities.model.excel_field):

    'Unique identifier'      →  edition.text_id (via text.identifier suffix)
    'Edition unique identifier per individual text'
                             →  edition.identifier_per_text, stored with the
                                text's BHL/NO-BHL prefix (e.g. BHL_29-A)
    'Publication year'       →  edition.publication_year (strict integer)
    'Edition reference'      →  edition.reference
    'Page numbers'           →  edition.page_numbers
    'Reprint ?'              →  edition.reprint (YES/NO → boolean)
    'If reprint, identically typeset?'
                             →  edition.reprint_identical (N/A → NULL)
    'If reprint, of what?'   →  edition.reprint_of (raw, N/A → NULL)
                                + edition.reprint_of_edition_id (resolved)
    'Manuscript used 1'–'16' + 'Likely use of a copy of Manuscript 1'–'16?'
                             →  edition__manuscripts link rows
    'Edition used or consulted 1'–'5'
                             →  edition__edition link rows

Reference resolution (this sheet links by several vocabularies):
  - text link: 'Unique identifier' must equal a TEXTS 'Unique identifier'
    (the part of text.identifier after the BHL/NO-BHL prefix); an edition
    whose text cannot be resolved is rejected.
  - manuscript refs: first tried as a manuscript copy identifier
    (e.g. '29-1'), then as a codex identifier within the edition's text
    (e.g. 'Cologne HA 6'). A codex holding several copies of the text is
    ambiguous → error.
  - edition refs (consulted / reprint-of): first tried as a per-text edition
    identifier (e.g. '618-A') when globally unique, then as an
    '(inc. volume)' identifier within the edition's text
    (e.g. 'Surius 5 (1574)').
  - a ref of 'N/A' means "no link" and is skipped silently; every other
    unresolvable or ambiguous ref is reported (the edition row itself is
    kept — fix the workbook).
"""

import logging
from dataclasses import dataclass
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from utilities.model import Edition, EditionEdition, EditionManuscript, Manuscript, Text

from ..excel import data_rows, header_map, is_empty
from ..fields import (
    CellError,
    FieldSpec,
    strict_int,
    strict_str,
    strict_tristate,
    strict_yesno,
)
from ..report import ImportReport, RowError

log = logging.getLogger(__name__)

SHEET = "EDITIONS"

SPECS: dict[str, FieldSpec] = {
    "text_uid": FieldSpec("Unique identifier", strict_str, required=True),
    "identifier_per_text": FieldSpec(
        "Edition unique identifier per individual text", strict_str, required=True
    ),
    "publication_year": FieldSpec("Publication year", strict_int),
    "reference": FieldSpec("Edition reference", strict_str),
    "page_numbers": FieldSpec("Page numbers", strict_str),
    "reprint": FieldSpec("Reprint ?", strict_yesno),
    "reprint_identical": FieldSpec("If reprint, identically typeset?", strict_yesno),
    "reprint_of": FieldSpec("If reprint, of what?", strict_str),
    # Resolution key only (not stored): identifies this edition's containing
    # volume, the vocabulary other rows use to reference it.
    "volume": FieldSpec("Edition unique identifier (inc. volume)", strict_str),
}

MANUSCRIPT_COLUMNS = [(f"Manuscript used {k}", f"Likely use of a copy of Manuscript {k}?") for k in range(1, 17)]
CONSULTED_COLUMNS = [f"Edition used or consulted {k}" for k in range(1, 6)]

NO_LINK = "N/A"


@dataclass(frozen=True)
class ManuscriptLink:
    """A resolved edition→manuscript link."""

    manuscript_identifier: str
    likely_use_of_a_copy: bool | None


@dataclass(frozen=True)
class EditionRow:
    """A fully validated EDITIONS row with resolved links.

    reprint_of_index / consulted_indices are positions in the parsed
    edition-row list (database ids do not exist yet in phase 1).
    """

    excel_row: int
    text_identifier: str
    identifier_per_text: str  # prefixed, e.g. BHL_29-A
    publication_year: int | None
    reference: str | None
    page_numbers: str | None
    reprint: bool | None
    reprint_identical: bool | None
    reprint_of: str | None
    reprint_of_index: int | None
    manuscript_links: tuple[ManuscriptLink, ...]
    consulted_indices: tuple[int, ...]


def parse_sheet(
    ws: Worksheet, report: ImportReport, context: dict[str, list] | None = None
) -> list[EditionRow]:
    """Phase 1 — validate every row and resolve all links; no database.

    Requires the parsed TEXTS and MANUSCRIPTS rows in context (registry
    order guarantees they were parsed first). Links can only resolve to rows
    that themselves passed validation.
    """
    context = context or {}
    text_by_uid = {t.unique_id: t.identifier for t in context.get("TEXTS", [])}
    # text.identifier = prefix + '_' + unique_id, so the prefix is what's left
    # after removing the suffix; editions inherit it for identifier_per_text.
    prefix_by_uid = {
        t.unique_id: t.identifier[: -(len(t.unique_id) + 1)]
        for t in context.get("TEXTS", [])
    }
    ms_by_copy = {m.copy_id: m.identifier for m in context.get("MANUSCRIPTS", [])}
    ms_by_text_codex: dict[tuple[str, str], list[str]] = {}
    for m in context.get("MANUSCRIPTS", []):
        if m.text_unique_id and m.codex_identifier:
            ms_by_text_codex.setdefault(
                (m.text_unique_id, m.codex_identifier), []
            ).append(m.identifier)

    columns = header_map(
        ws,
        [spec.column for spec in SPECS.values()]
        + [c for pair in MANUSCRIPT_COLUMNS for c in pair]
        + CONSULTED_COLUMNS,
    )

    # First pass: cell-level validation of the row's own fields.
    prelim: list[tuple[int, dict[str, Any], tuple[Any, ...]]] = []
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

        if parsed["text_uid"] not in text_by_uid:
            report.errors.append(
                RowError(
                    SHEET,
                    excel_row,
                    "Unique identifier",
                    parsed["text_uid"],
                    "no text with this unique identifier (or its TEXTS row was rejected)",
                )
            )
            continue
        if parsed["reprint_of"] == NO_LINK:
            parsed["reprint_of"] = None
        prelim.append((excel_row, parsed, values))

    # Reference vocabularies, built from surviving rows only.
    by_per_text_id: dict[str, list[int]] = {}
    by_text_volume: dict[tuple[str, str], list[int]] = {}
    for index, (_, parsed, _) in enumerate(prelim):
        by_per_text_id.setdefault(parsed["identifier_per_text"], []).append(index)
        if parsed["volume"]:
            by_text_volume.setdefault(
                (parsed["text_uid"], parsed["volume"]), []
            ).append(index)

    def resolve_edition_ref(
        index: int, excel_row: int, column: str, ref: str
    ) -> int | None:
        """Per-text identifier first (if globally unique), then (text, volume)."""
        text_uid = prelim[index][1]["text_uid"]
        candidates = by_per_text_id.get(ref, [])
        if len(candidates) != 1:
            candidates = by_text_volume.get((text_uid, ref), [])
        if len(candidates) == 1:
            target = candidates[0]
            if target == index:
                report.errors.append(
                    RowError(SHEET, excel_row, column, ref,
                             "edition references itself", severity="warning")
                )
                return None
            return target
        reason = (
            f"ambiguous edition reference ({len(candidates)} matches)"
            if candidates
            else "unresolvable edition reference (no per-text identifier or "
            "same-text volume identifier matches)"
        )
        report.errors.append(
            RowError(SHEET, excel_row, column, ref, reason, severity="warning")
        )
        return None

    # Second pass: resolve links.
    rows: list[EditionRow] = []
    for index, (excel_row, parsed, values) in enumerate(prelim):
        text_uid = parsed["text_uid"]

        manuscript_links: list[ManuscriptLink] = []
        seen_ms: set[str] = set()
        for ref_column, likely_column in MANUSCRIPT_COLUMNS:
            raw_ref = values[columns[ref_column]]
            raw_likely = values[columns[likely_column]]
            try:
                ref = strict_str(raw_ref)
                likely = strict_tristate(raw_likely)
            except CellError as error:
                report.errors.append(
                    RowError(SHEET, excel_row, ref_column, raw_ref, str(error))
                )
                continue
            if ref is None or ref == NO_LINK:
                continue
            if ref in ms_by_copy:
                identifier = ms_by_copy[ref]
            else:
                candidates = ms_by_text_codex.get((text_uid, ref), [])
                if len(candidates) == 1:
                    identifier = candidates[0]
                else:
                    reason = (
                        f"ambiguous manuscript reference: codex holds "
                        f"{len(candidates)} copies of text {text_uid}"
                        if candidates
                        else "unresolvable manuscript reference (no copy identifier "
                        "or same-text codex identifier matches)"
                    )
                    report.errors.append(
                        RowError(SHEET, excel_row, ref_column, ref, reason,
                                 severity="warning")
                    )
                    continue
            if identifier in seen_ms:
                report.errors.append(
                    RowError(SHEET, excel_row, ref_column, ref,
                             f"duplicate manuscript link ({identifier})",
                             severity="warning")
                )
                continue
            seen_ms.add(identifier)
            manuscript_links.append(
                ManuscriptLink(manuscript_identifier=identifier, likely_use_of_a_copy=likely)
            )

        consulted: list[int] = []
        seen_consulted: set[int] = set()
        for column in CONSULTED_COLUMNS:
            raw_ref = values[columns[column]]
            try:
                ref = strict_str(raw_ref)
            except CellError as error:
                report.errors.append(
                    RowError(SHEET, excel_row, column, raw_ref, str(error))
                )
                continue
            if ref is None or ref == NO_LINK:
                continue
            target = resolve_edition_ref(index, excel_row, column, ref)
            if target is None or target in seen_consulted:
                continue
            seen_consulted.add(target)
            consulted.append(target)

        reprint_of_index = None
        if parsed["reprint_of"] is not None:
            reprint_of_index = resolve_edition_ref(
                index, excel_row, "If reprint, of what?", parsed["reprint_of"]
            )

        rows.append(
            EditionRow(
                excel_row=excel_row,
                text_identifier=text_by_uid[text_uid],
                identifier_per_text=(
                    f"{prefix_by_uid[text_uid]}_{parsed['identifier_per_text']}"
                ),
                publication_year=parsed["publication_year"],
                reference=parsed["reference"],
                page_numbers=parsed["page_numbers"],
                reprint=parsed["reprint"],
                reprint_identical=parsed["reprint_identical"],
                reprint_of=parsed["reprint_of"],
                reprint_of_index=reprint_of_index,
                manuscript_links=tuple(manuscript_links),
                consulted_indices=tuple(consulted),
            )
        )

    report.parsed += len(rows)
    return rows


def import_rows(session: Session, rows: list[EditionRow]) -> int:
    """Phase 2 — insert editions, then their link rows. Caller commits."""
    text_ids = {
        identifier: pk
        for identifier, pk in session.exec(select(Text.identifier, Text.text_id)).all()
    }
    manuscript_ids = {
        identifier: pk
        for identifier, pk in session.exec(
            select(Manuscript.identifier, Manuscript.manuscript_id)
        ).all()
    }

    editions = [
        Edition(
            text_id=text_ids[row.text_identifier],
            identifier_per_text=row.identifier_per_text,
            publication_year=row.publication_year,
            reference=row.reference,
            page_numbers=row.page_numbers,
            reprint=row.reprint,
            reprint_identical=row.reprint_identical,
            reprint_of=row.reprint_of,
        )
        for row in rows
    ]
    session.add_all(editions)
    session.flush()  # assign edition_ids so self-links can point at them

    manuscript_link_count = consulted_count = 0
    for row, edition in zip(rows, editions):
        if row.reprint_of_index is not None:
            edition.reprint_of_edition_id = editions[row.reprint_of_index].edition_id
        for link in row.manuscript_links:
            session.add(
                EditionManuscript(
                    edition_id=edition.edition_id,
                    manuscript_id=manuscript_ids[link.manuscript_identifier],
                    likely_use_of_a_copy=link.likely_use_of_a_copy,
                )
            )
            manuscript_link_count += 1
        for target in row.consulted_indices:
            session.add(
                EditionEdition(
                    edition_id=edition.edition_id,
                    consulted_edition_id=editions[target].edition_id,
                )
            )
            consulted_count += 1

    log.info(
        "staged %d edition rows, %d manuscript links, %d consulted-edition links",
        len(rows), manuscript_link_count, consulted_count,
    )
    return len(rows)
