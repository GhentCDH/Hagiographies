"""TEXTS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column
comments by utilities.model.excel_field):

    'BHL or NO BHL' + '_' + 'Unique identifier'  →  text.identifier
    'Title of the work'                          →  text.title
    'Approximate token count'                    →  text.approximate_token_count
    'Prose or verse'                             →  text_form lookup
    'Source type'                                →  text_source_type lookup
    'Subtype'                                    →  text_source_subtype lookup
    'Réécriture?'                                →  text.reecriture
    'Réécriture of which text(s)?'               →  text.reecriture_note (raw)
                                                    + text.reecriture_text_id (resolved)
    'Dating range (beginning)' / '(end)'         →  text.dating_range_start / _stop
    'Quarter century chronology'                 →  text.dating_range
    'Dating confidence rating'                   →  dating_confidence lookup
    'Dating notes'                               →  text.dating_note
    'Author of the text' (+ training ground, antecedents, milieu columns)
                                                 →  author row → text.author_id
    'Is author based in destinatary institution?'→  text.author_in_destinary_institution
    'Text creation - location by archdiocese'    →  archdiocese lookup
    'Text creation - location by diocese'        →  diocese lookup
    'Text creation - location by institution'    →  institution lookup (+ GPS → location)
    'Primary institutional destinatary'          →  institution lookup (+ GPS → location)
    'Selected reference'                         →  text.reference
    'Notes'                                      →  text.general_note

The 'Precise institutional origin?' / 'Precise destinatary?' flags are not
stored (institution presence implies precision).

GPS: the workbook's GPS headers are SWAPPED — the '… GPS Longitude' column
holds latitude ×10⁶ and '… GPS Latitude' holds longitude ×10⁶. Values are
read swapped and divided by 1e6 (documented workbook defect) and must land
in Western Europe (lat 44–56, lon −2–10); anything else is reported as a
warning and no location is attached.

Anonymous authors ('Anon…') become one author row per text, named
'Anonymous ' + text.identifier, with the raw cell kept as the author note.
'N/A' and 'Unknown' in institution/destinatary/milieu columns mean NULL.
"""

import logging
from dataclasses import dataclass
from typing import Any

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, SQLModel, select

from utilities.model import (
    Archdiocese,
    Author,
    AuthorMilieu,
    DatingConfidence,
    Diocese,
    Institution,
    Location,
    Text,
    TextForm,
    TextSourceSubtype,
    TextSourceType,
)

from ..excel import data_rows, header_map, is_empty
from ..fields import (
    CellError,
    FieldSpec,
    strict_choice,
    strict_int,
    strict_str,
    strict_tristate,
    strict_yesno,
)
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
    "reecriture": FieldSpec("Réécriture?", strict_yesno),
    "reecriture_ref": FieldSpec("Réécriture of which text(s)?", strict_str),
    "dating_start": FieldSpec("Dating range (beginning)", strict_int),
    "dating_stop": FieldSpec("Dating range (end)", strict_int),
    "dating_range": FieldSpec("Quarter century chronology", strict_str),
    "dating_confidence": FieldSpec("Dating confidence rating", strict_str),
    "dating_note": FieldSpec("Dating notes", strict_str),
    "author": FieldSpec("Author of the text", strict_str),
    "author_training": FieldSpec("Institutional training ground of the author", strict_str),
    "author_antecedents": FieldSpec("Regional or local antecedents of the author", strict_str),
    "author_milieu": FieldSpec("Author milieu", strict_str),
    "author_in_dest": FieldSpec("Is author based in destinatary institution?", strict_tristate),
    "creation_archdiocese": FieldSpec("Text creation - location by archdiocese", strict_str),
    "creation_diocese": FieldSpec("Text creation - location by diocese", strict_str),
    "creation_institution": FieldSpec("Text creation - location by institution", strict_str),
    "destinatary": FieldSpec("Primary institutional destinatary", strict_str),
    "reference": FieldSpec("Selected reference", strict_str),
    "general_note": FieldSpec("Notes", strict_str),
}

# GPS pairs, handled outside SPECS: failures are warnings (location skipped),
# not row rejections. First column of each pair holds LATITUDE (headers are
# swapped in the workbook), second holds LONGITUDE.
CREATION_GPS = (
    "Text creation - institution - most precise possible GPS Longitude",
    "Text creation - institution - most precise possible GPS Latitude",
)
DESTINATARY_GPS = (
    "Institutional destinatary - most precise possible GPS Longitude",
    "Institutional destinatary - most precise possible GPS Latitude",
)

LAT_RANGE = (44.0, 56.0)
LON_RANGE = (-2.0, 10.0)

NULL_TOKENS = {"n/a", "unknown"}


def _null_token(value: str | None) -> str | None:
    """'N/A' and 'Unknown' (exact, case-insensitive) mean: no value."""
    if value is not None and value.casefold() in NULL_TOKENS:
        return None
    return value


def _parse_gps(raw_lat: Any, raw_lon: Any, scale: float = 1e6) -> tuple[float, float] | None:
    """Unscale a swapped GPS pair; CellError when junk or outside W-Europe.

    TEXTS stores degrees ×10⁶ (default scale); MANUSCRIPTS stores plain
    degrees (scale=1).
    """
    if raw_lat is None and raw_lon is None:
        return None
    if not isinstance(raw_lat, (int, float)) or not isinstance(raw_lon, (int, float)):
        raise CellError(f"expected a numeric GPS pair, got {raw_lat!r} / {raw_lon!r}")
    lat, lon = float(raw_lat) / scale, float(raw_lon) / scale
    if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
        raise CellError(
            f"GPS ({lat:.4f}, {lon:.4f}) outside Western Europe "
            f"(lat {LAT_RANGE}, lon {LON_RANGE})"
        )
    return round(lat, 6), round(lon, 6)


@dataclass(frozen=True)
class TextRow:
    """A fully validated TEXTS row, ready for the database."""

    excel_row: int
    identifier: str
    unique_id: str  # the part after the BHL/NO-BHL prefix; other sheets link on it
    title: str | None
    approximate_token_count: int | None
    form_label: str | None
    source_type_label: str | None
    source_subtype_label: str | None
    reecriture: bool | None
    reecriture_note: str | None
    reecriture_of_index: int | None  # index into the parsed row list
    dating_range_start: int | None
    dating_range_stop: int | None
    dating_range: str | None
    dating_confidence_label: str | None
    dating_note: str | None
    author_name: str | None  # deduplicated author-row name (or Anonymous …)
    author_note: str | None
    author_training: str | None
    author_antecedents: str | None
    author_milieu_label: str | None
    author_in_destinary_institution: bool | None
    creation_archdiocese_name: str | None
    creation_diocese_name: str | None
    creation_institution_name: str | None
    creation_gps: tuple[float, float] | None
    destinatary_institution_name: str | None
    destinatary_gps: tuple[float, float] | None
    reference: str | None
    general_note: str | None


def parse_sheet(
    ws: Worksheet, report: ImportReport, context: dict[str, list] | None = None
) -> list[TextRow]:
    """Phase 1 — pure validation and réécriture-link resolution; no DB."""
    columns = header_map(
        ws,
        [spec.column for spec in SPECS.values()]
        + list(CREATION_GPS)
        + list(DESTINATARY_GPS),
    )
    report.register_columns(SHEET, columns)

    prelim: list[dict[str, Any]] = []
    first_seen: dict[str, int] = {}
    for excel_row, values in data_rows(ws):
        if is_empty(values):
            report.skipped_empty.append(excel_row)
            continue

        parsed: dict[str, Any] = {"excel_row": excel_row}
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
        parsed["identifier"] = identifier

        # GPS pairs → warnings, never row rejections.
        for key, (lat_col, lon_col) in (
            ("creation_gps", CREATION_GPS),
            ("destinatary_gps", DESTINATARY_GPS),
        ):
            raw_lat, raw_lon = values[columns[lat_col]], values[columns[lon_col]]
            try:
                parsed[key] = _parse_gps(raw_lat, raw_lon)
            except CellError as error:
                parsed[key] = None
                report.errors.append(
                    RowError(SHEET, excel_row, lat_col, f"{raw_lat!r}/{raw_lon!r}",
                             str(error), severity="warning")
                )

        # NULL tokens in geo / milieu columns.
        for key in ("creation_archdiocese", "creation_diocese",
                    "creation_institution", "destinatary", "author_milieu"):
            parsed[key] = _null_token(parsed[key])
        if parsed["reecriture_ref"] is not None and \
                parsed["reecriture_ref"].casefold() == "n/a":
            parsed["reecriture_ref"] = None

        prelim.append(parsed)

    # Réécriture references resolve against the parsed rows themselves.
    index_by_uid = {p["unique_id"]: i for i, p in enumerate(prelim)}

    # Institution → GPS (first occurrence wins; conflicts warned once per
    # distinct (institution, coordinates) resp. (coordinates, name) pair —
    # the same collision repeats across many rows).
    institution_gps: dict[str, tuple[float, float]] = {}
    location_names: dict[tuple[float, float], str] = {}
    warned: set[tuple] = set()
    for parsed in prelim:
        for name_key, gps_key in (
            ("creation_institution", "creation_gps"),
            ("destinatary", "destinatary_gps"),
        ):
            name, gps = parsed[name_key], parsed[gps_key]
            if not name or gps is None:
                continue
            if name in institution_gps and institution_gps[name] != gps:
                if ("inst", name, gps) not in warned:
                    warned.add(("inst", name, gps))
                    report.errors.append(
                        RowError(
                            SHEET, parsed["excel_row"], SPECS[name_key].column, name,
                            f"institution already located at {institution_gps[name]}, "
                            f"also seen at {gps} (first wins)",
                            severity="warning",
                        )
                    )
                continue
            institution_gps.setdefault(name, gps)
            if gps in location_names and location_names[gps] != name:
                if ("loc", gps, name) not in warned:
                    warned.add(("loc", gps, name))
                    report.errors.append(
                        RowError(
                            SHEET, parsed["excel_row"], SPECS[name_key].column, name,
                            f"coordinates {gps} already named "
                            f"{location_names[gps]!r} (first name wins)",
                            severity="warning",
                        )
                    )
            location_names.setdefault(gps, name)

    rows: list[TextRow] = []
    for index, parsed in enumerate(prelim):
        reecriture_of_index = None
        ref = parsed["reecriture_ref"]
        if ref is not None:
            candidate = ref.removeprefix("BHL ").strip()
            reecriture_of_index = index_by_uid.get(candidate)
            if reecriture_of_index == index:
                reecriture_of_index = None
            if (
                reecriture_of_index is None
                and parsed["reecriture"] is True
                and ref.casefold() not in {"no", "n/a"}
            ):
                report.errors.append(
                    RowError(
                        SHEET, parsed["excel_row"], SPECS["reecriture_ref"].column,
                        ref, "réécriture source not resolvable to a text "
                        "(kept as note only)", severity="warning",
                    )
                )

        author_raw = parsed["author"]
        if author_raw is not None and author_raw.casefold().startswith("anon"):
            author_name = f"Anonymous {parsed['identifier']}"
            author_note = author_raw
        else:
            author_name, author_note = author_raw, None

        rows.append(
            TextRow(
                excel_row=parsed["excel_row"],
                identifier=parsed["identifier"],
                unique_id=parsed["unique_id"],
                title=parsed["title"],
                approximate_token_count=parsed["token_count"],
                form_label=parsed["form"],
                source_type_label=parsed["source_type"],
                source_subtype_label=parsed["source_subtype"],
                reecriture=parsed["reecriture"],
                reecriture_note=parsed["reecriture_ref"],
                reecriture_of_index=reecriture_of_index,
                dating_range_start=parsed["dating_start"],
                dating_range_stop=parsed["dating_stop"],
                dating_range=parsed["dating_range"],
                dating_confidence_label=parsed["dating_confidence"],
                dating_note=parsed["dating_note"],
                author_name=author_name,
                author_note=author_note,
                author_training=parsed["author_training"],
                author_antecedents=parsed["author_antecedents"],
                author_milieu_label=parsed["author_milieu"],
                author_in_destinary_institution=parsed["author_in_dest"],
                creation_archdiocese_name=parsed["creation_archdiocese"],
                creation_diocese_name=parsed["creation_diocese"],
                creation_institution_name=parsed["creation_institution"],
                creation_gps=parsed["creation_gps"],
                destinatary_institution_name=parsed["destinatary"],
                destinatary_gps=parsed["destinatary_gps"],
                reference=parsed["reference"],
                general_note=parsed["general_note"],
            )
        )

    report.parsed += len(rows)
    return rows


def _lookup_ids(
    session: Session, model: type[SQLModel], labels: set[str], attr: str = "label"
) -> dict[str, int]:
    """Get-or-create lookup rows by label/name; return value → PK."""
    pk = f"{model.__tablename__}_id"
    ids: dict[str, int] = {}
    for label in sorted(labels):
        existing = session.exec(
            select(model).where(getattr(model, attr) == label)
        ).first()
        if existing is None:
            existing = model(**{attr: label})
            session.add(existing)
            session.flush()
            log.debug("created %s %r", model.__tablename__, label)
        ids[label] = getattr(existing, pk)
    return ids


def import_rows(session: Session, rows: list[TextRow]) -> int:
    """Phase 2 — lookups, geography, authors, then text rows. Caller commits."""
    forms = _lookup_ids(session, TextForm, {r.form_label for r in rows if r.form_label})
    types = _lookup_ids(
        session, TextSourceType, {r.source_type_label for r in rows if r.source_type_label}
    )
    subtypes = _lookup_ids(
        session, TextSourceSubtype,
        {r.source_subtype_label for r in rows if r.source_subtype_label},
    )
    confidences = _lookup_ids(
        session, DatingConfidence,
        {r.dating_confidence_label for r in rows if r.dating_confidence_label},
    )
    milieus = _lookup_ids(
        session, AuthorMilieu,
        {r.author_milieu_label for r in rows if r.author_milieu_label},
    )
    archdioceses = _lookup_ids(
        session, Archdiocese,
        {r.creation_archdiocese_name for r in rows if r.creation_archdiocese_name},
        attr="name",
    )
    dioceses = _lookup_ids(
        session, Diocese,
        {r.creation_diocese_name for r in rows if r.creation_diocese_name},
        attr="name",
    )

    # Locations: dedupe by coordinates; name = first institution at the point
    # (same first-wins order as the parse-phase warnings).
    institution_gps: dict[str, tuple[float, float]] = {}
    location_names: dict[tuple[float, float], str] = {}
    for row in rows:
        for name, gps in (
            (row.creation_institution_name, row.creation_gps),
            (row.destinatary_institution_name, row.destinatary_gps),
        ):
            if name and gps is not None:
                institution_gps.setdefault(name, gps)
                location_names.setdefault(gps, name)
    location_ids: dict[tuple[float, float], int] = {}
    for gps, name in location_names.items():
        location = Location(name=name, latitude=gps[0], longitude=gps[1])
        session.add(location)
        session.flush()
        location_ids[gps] = location.location_id

    institution_names = {
        n
        for row in rows
        for n in (row.creation_institution_name, row.destinatary_institution_name)
        if n
    }
    institutions: dict[str, int] = {}
    for name in sorted(institution_names):
        gps = institution_gps.get(name)
        institution = Institution(
            name=name, location_id=location_ids[gps] if gps else None
        )
        session.add(institution)
        session.flush()
        institutions[name] = institution.institution_id

    # Authors: first occurrence wins (anon names are unique per text anyway).
    authors: dict[str, int] = {}
    for row in rows:
        if not row.author_name or row.author_name in authors:
            continue
        author = Author(
            name=row.author_name,
            institutional_training_ground=row.author_training,
            regional_antecedents=row.author_antecedents,
            author_milieu_id=milieus[row.author_milieu_label]
            if row.author_milieu_label
            else None,
            note=row.author_note,
        )
        session.add(author)
        session.flush()
        authors[row.author_name] = author.author_id

    texts = [
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
            reecriture=row.reecriture,
            reecriture_note=row.reecriture_note,
            dating_range_start=row.dating_range_start,
            dating_range_stop=row.dating_range_stop,
            dating_range=row.dating_range,
            dating_confidence_id=confidences[row.dating_confidence_label]
            if row.dating_confidence_label
            else None,
            dating_note=row.dating_note,
            author_id=authors[row.author_name] if row.author_name else None,
            author_in_destinary_institution=row.author_in_destinary_institution,
            creation_archdiocese_id=archdioceses[row.creation_archdiocese_name]
            if row.creation_archdiocese_name
            else None,
            creation_diocese_id=dioceses[row.creation_diocese_name]
            if row.creation_diocese_name
            else None,
            creation_institution_id=institutions[row.creation_institution_name]
            if row.creation_institution_name
            else None,
            destinary_institution_id=institutions[row.destinatary_institution_name]
            if row.destinatary_institution_name
            else None,
            reference=row.reference,
            general_note=row.general_note,
        )
        for row in rows
    ]
    session.add_all(texts)
    session.flush()  # assign text_ids so réécriture self-links can point at them

    for row, text in zip(rows, texts):
        if row.reecriture_of_index is not None:
            text.reecriture_text_id = texts[row.reecriture_of_index].text_id

    log.info("staged %d text rows for insert", len(rows))
    return len(rows)
