"""MANUSCRIPTS sheet: parse/validate (phase 1, pure) and import (phase 2, DB).

Excel column ↔ database mapping (also recorded as PostgreSQL column comments
by utilities.model.excel_field):

    'BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text'
                                     →  manuscript.identifier (e.g. BHL_29-4)
    'Unique text identifier'         →  manuscript.text_id (prefix + uid
                                        matched against text.identifier; no
                                        match is a WARNING — the manuscript
                                        is imported with text_id NULL and the
                                        raw reference in general_notes)
    'Codex number in database'       →  manuscript.codex_number
    'Codex unique identifier'        →  manuscript.codex_identifier
    'Codex with multiple manuscript copies of texts from corpus'
                                     →  manuscript.codex_multiple_copies (Y/N)
    'Codex features n manuscript copies of texts from corpus'
                                     →  manuscript.codex_copy_amount
    'Preservation status of manuscript copy'
                                     →  manuscript_preservation_status lookup
    'Manuscript location'            →  manuscript.location_id (location row
                                        get-or-created by name, no coordinates)
    'Manuscript holding institution' →  manuscript_holding_institution lookup
    'Manuscript height' / 'Manuscript width'
                                     →  manuscript.height / .width (text; the
                                        workbook mixes numbers and prose)
    'Manuscript dating by (earliest) century'
                                     →  manuscript.dating_century
    'Manuscript dating range start' / 'Manuscript dating range end'
                                     →  manuscript.dating_range_start / _end:
                                        0 when the cell is not an integer
                                        (e.g. 'Unknown'), with the raw values
                                        kept in manuscript.dating_note
    'Preferred secondary reference for manuscript dating'
                                     →  manuscript.dating_reference (the
                                        cell's hyperlink URL when present)
    'Confidence rating for manuscript dating'
                                     →  dating_confidence lookup (shared with
                                        TEXTS)
    'Usable Légendiers entry for codex contents'
                                     →  manuscript.codex_legendiers_usable
    'Composite?'                     →  manuscript.codex_composite
    'Légendiers entry code'          →  manuscript.codex_legendiers_entry_code
    'Notes on codex contents'        →  manuscript.codex_notes
    'Vernacular region (Romance/Germanic)'
                                     →  vernacular_region lookup (G/R/F;
                                        Unknown/N/A → NULL, anything else
                                        warns and stays NULL)
    'Manuscript origin by archdiocese' / '… by diocese' / '… by institution'
                                     →  manuscript.origin_archdiocese_id /
                                        origin_diocese_id /
                                        origin_institution_id (get-or-create
                                        by name in the shared geography
                                        lookups)
    'Manuscript origin by diocese confidence rating' /
    'Manuscript origin confidence rating'
                                     →  origin_confidence lookup (A/B/C/D)
    'Manuscript provenance by early/earliest institutional owner' (+ its
    confidence rating) — both headers appear TWICE in the workbook; the
    FIRST occurrences hold stray GPS coordinates, the SECOND occurrences the
    real owner name and A/B/C rating
                                     →  manuscript.provenance_early_institute_id
                                        + provenance_early_confidence_id
                                        (provenance_confidence lookup)
    'Manuscript provenance by undetermined or later institutional owner'
                                     →  manuscript.provenance_later_institute_id
                                        (no confidence column exists yet;
                                        provenance_later_confidence_id stays
                                        NULL)
    GPS pairs ('… origin by diocese GPS Longitude/latitude', '… early/earliest
    institutional owner GPS Longitude/latitude', '… undetermined or later
    institutional owner GPS Longitude/latitude') — headers are SWAPPED like
    the TEXTS sheet ('… GPS Longitude' holds latitude) but the values are
    plain degrees, not ×10⁶
                                     →  a location row per distinct coordinate
                                        pair (deduplicated, first name wins),
                                        linked from diocese.location_id resp.
                                        institution.location_id. Geography
                                        names without coordinates (always the
                                        archdiocese and origin institution —
                                        no GPS columns exist for them) get a
                                        location get-or-created by name with
                                        NULL coordinates. Unknown/N/A mean no
                                        coordinates; junk or non-W-Europe
                                        values warn; coordinates whose name
                                        column is NULL warn and are skipped.
                                        An entity's existing location_id (e.g.
                                        set by the TEXTS import) is never
                                        overwritten.
    'Manuscript origin and provenance preferred secondary reference'
                                     →  manuscript.origin_or_provenance_secondary_reference
                                        (hyperlink URL when present)
    'Based on exemplar'              →  manuscript_relation rows, type
                                        'Based on exemplar' (comma-split)
    'Exemplar of which manuscript(s)'
                                     →  manuscript_relation rows, type
                                        'Exemplar of' (comma-split)
    'Manuscript type'                →  manuscript_type lookup (whitespace-
                                        normalized label) + the raw cell in
                                        manuscript.manuscript_type_note
    'Notes'                          →  manuscript.general_notes (appended
                                        after the unresolved-text note)
    link columns (see LINK_COLUMNS + the images pair)
                                     →  manuscript_link rows, typed via
                                        manuscript_link_type

Relation references ('Based on exemplar' / 'Exemplar of …') resolve within
this sheet, like the EDITIONS manuscript refs: first as a copy identifier
(e.g. '1494-4'), then as a codex identifier within the row's own text
(e.g. 'Douai 11'); prose, unresolvable, ambiguous or self references warn.

Link cells: the URL is the cell's *hyperlink* target — the display text is
junk ('Link', 'Word document'). A cell with an http(s) hyperlink becomes a
manuscript_link row; a non-http(s) hyperlink (OneDrive/local paths) or a
link-suggesting display without any hyperlink only warns (the manuscript is
kept). Empty, 'N/A', 'NA' and 'NO' cells mean no link. 'Online manuscript
images' is typed by 'Type of online images' (SCAN / IIIF / IIIF MF / IPhone
pictures, whitespace- and case-insensitive); an unrecognized type warns and
skips the link (user decision — laxer than the EDITIONS images column).

Documented exceptions to strict no-normalization (user decisions):
  - preservation status is matched case-insensitively to Lost/Preserved;
  - institution names differing only in case/whitespace merge into one row,
    the most frequent raw spelling wins;
  - 'N/A' and 'Unknown' mean no value (NULL) in the lookup, name and note
    columns; 'to be verified' in a name column warns and stays NULL;
  - non-integer dating range values become 0, raw values in dating_note;
  - manuscript type labels are whitespace-normalized (raw kept per row in
    manuscript_type_note).
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from utilities.model import (
    Archdiocese,
    DatingConfidence,
    Diocese,
    Institution,
    Location,
    Manuscript,
    ManuscriptHoldingInstitution,
    ManuscriptLink,
    ManuscriptLinkType,
    ManuscriptPreservationStatus,
    ManuscriptRelation,
    ManuscriptRelationshipType,
    ManuscriptType,
    OriginConfidence,
    ProvenanceConfidence,
    Text,
    VernacularRegion,
)

from ..excel import (
    WorkbookError,
    cell_hyperlinks,
    data_rows,
    header_map,
    header_positions,
    is_empty,
)
from ..fields import (
    CellError,
    FieldSpec,
    strict_canonical,
    strict_choice,
    strict_int,
    strict_str,
    strict_tristate,
)
from ..report import ImportReport, RowError

log = logging.getLogger(__name__)

SHEET = "MANUSCRIPTS"

NOT_APPLICABLE = "N/A"


def _null_na(parser: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Wrap a parser so an 'N/A' cell means no value (NULL)."""

    def parse(value: Any) -> Any:
        if isinstance(value, str) and value.strip() == NOT_APPLICABLE:
            return None
        result = parser(value)
        return None if result == NOT_APPLICABLE else result

    return parse


def _strict_century(value: Any) -> int | None:
    """The dating century: an integer; 'Unknown'/'N/A' mean NULL."""
    if isinstance(value, str) and value.strip().casefold() in {"n/a", "unknown"}:
        return None
    return strict_int(value)


_CANONICAL_CONFIDENCE = strict_canonical("A", "B", "C", "D")


def _strict_confidence(value: Any) -> str | None:
    """An A/B/C/D confidence rating; 'N/A'/'Unknown' mean NULL."""
    text = strict_str(value)
    if text is None or text.casefold() in {"n/a", "unknown"}:
        return None
    return _CANONICAL_CONFIDENCE(text)


SPECS: dict[str, FieldSpec] = {
    "bhl_prefix": FieldSpec("BHL or NO BHL", strict_choice("BHL", "NO BHL"), required=True),
    "copy_id": FieldSpec(
        "Manuscript copy unique identifier per text", strict_str, required=True
    ),
    "text_uid": FieldSpec("Unique text identifier", strict_str, required=True),
    "codex_number": FieldSpec("Codex number in database", _null_na(strict_int)),
    "codex": FieldSpec("Codex unique identifier", strict_str),
    "codex_multiple_copies": FieldSpec(
        "Codex with multiple manuscript copies of texts from corpus", strict_tristate
    ),
    "codex_copy_amount": FieldSpec(
        "Codex features n manuscript copies of texts from corpus", _null_na(strict_int)
    ),
    "preservation": FieldSpec(
        "Preservation status of manuscript copy", strict_canonical("Lost", "Preserved")
    ),
    "location": FieldSpec("Manuscript location", _null_na(strict_str)),
    "institution": FieldSpec("Manuscript holding institution", strict_str),
    "height": FieldSpec("Manuscript height", _null_na(strict_str)),
    "width": FieldSpec("Manuscript width", _null_na(strict_str)),
    "dating_century": FieldSpec(
        "Manuscript dating by (earliest) century", _strict_century
    ),
    "dating_reference": FieldSpec(
        "Preferred secondary reference for manuscript dating", _null_na(strict_str)
    ),
    "dating_confidence": FieldSpec(
        "Confidence rating for manuscript dating", _null_na(strict_str)
    ),
    "legendiers_usable": FieldSpec(
        "Usable Légendiers entry for codex contents", strict_tristate
    ),
    "composite": FieldSpec("Composite?", strict_tristate),
    "legendiers_code": FieldSpec("Légendiers entry code", _null_na(strict_str)),
    "codex_notes": FieldSpec("Notes on codex contents", _null_na(strict_str)),
    "vernacular": FieldSpec("Vernacular region (Romance/Germanic)", strict_str),
    "origin_archdiocese": FieldSpec("Manuscript origin by archdiocese", strict_str),
    "origin_diocese": FieldSpec("Manuscript origin by diocese", strict_str),
    "origin_diocese_confidence": FieldSpec(
        "Manuscript origin by diocese confidence rating", _strict_confidence
    ),
    "origin_institution": FieldSpec("Manuscript origin by institution", strict_str),
    "origin_institution_confidence": FieldSpec(
        "Manuscript origin confidence rating", _strict_confidence
    ),
    "provenance_later": FieldSpec(
        "Manuscript provenance by undetermined or later institutional owner",
        strict_str,
    ),
    "secondary_reference": FieldSpec(
        "Manuscript origin and provenance preferred secondary reference",
        _null_na(strict_str),
    ),
    "based_on": FieldSpec("Based on exemplar", _null_na(strict_str)),
    "exemplar_of": FieldSpec("Exemplar of which manuscript(s)", _null_na(strict_str)),
    "manuscript_type": FieldSpec("Manuscript type", _null_na(strict_str)),
    "notes": FieldSpec("Notes", _null_na(strict_str)),
}

# Dating range columns, handled outside SPECS: a non-integer value becomes 0
# and the raw start/end pair is preserved in dating_note.
DATING_RANGE_START_COLUMN = "Manuscript dating range start"
DATING_RANGE_END_COLUMN = "Manuscript dating range end"

# The early/earliest provenance owner + confidence headers appear TWICE in
# the sheet; the first occurrences hold stray GPS values, the second the
# real data. Handled outside SPECS via header_positions.
PROVENANCE_EARLY_OWNER_COLUMN = (
    "Manuscript provenance by early/earliest institutional owner"
)
PROVENANCE_EARLY_CONFIDENCE_COLUMN = (
    "Manuscript provenance by early/earliest institutional owner confidence rating"
)

# GPS pairs, handled outside SPECS. Headers are swapped like the TEXTS sheet
# (the '… GPS Longitude' column holds LATITUDE) but the values are plain
# degrees, not ×10⁶. Unknown/N/A mean no coordinates; junk or out-of-range
# values only warn (the coordinates are skipped, the row is kept).
DIOCESE_GPS = (
    "Manuscript origin by diocese GPS Longitude",
    "Manuscript origin by diocese GPS latitude",
)
PROVENANCE_EARLY_GPS = (
    "Manuscript provenance by early/earliest institutional owner GPS Longitude",
    "Manuscript provenance by early/earliest institutional owner GPS latitude",
)
PROVENANCE_LATER_GPS = (
    "Manuscript provenance by undetermined or later institutional owner GPS Longitude",
    "Manuscript provenance by undetermined or later institutional owner GPS latitude",
)

# Plain link columns: one manuscript_link row per http(s) hyperlink.
LINK_COLUMNS: list[tuple[str, str]] = [
    ("Légendiers entry link", "Legendiers entry"),
    (
        "Viable alternative for Légendiers entry on codex contents",
        "Legendiers alternative",
    ),
    ("Online catalogue link", "Catalogue online"),
    ("Bollandist catalogue link", "Catalogue Bollandist"),
    ("Other relevant catalogue link", "Catalogue other"),
]

# The images link is typed by its companion column.
IMAGES_TYPE_COLUMN = "Type of online images"
IMAGES_LINK_COLUMN = "Online manuscript images"
IMAGE_TYPE_LABELS = {
    "scan": "Images Scan",
    "iiif": "Images IIIF",
    "iiif mf": "Images IIIF MF",
    "iphone pictures": "Images Photos",
}

# All manuscript_link_type rows, seeded even when unused.
LINK_TYPE_LABELS: list[str] = [
    "Images Scan",
    "Images IIIF",
    "Images IIIF MF",
    "Images Photos",
    "Catalogue online",
    "Catalogue Bollandist",
    "Catalogue other",
    "Legendiers entry",
    "Legendiers alternative",
]

# Manuscript↔manuscript relation columns: (SPECS key, type label). Both
# columns may list several comma-separated manuscripts.
RELATION_COLUMNS: list[tuple[str, str]] = [
    ("based_on", "Based on exemplar"),
    ("exemplar_of", "Exemplar of"),
]
RELATION_TYPE_LABELS = [label for _, label in RELATION_COLUMNS]

VERNACULAR_LABELS = {"G", "R", "F"}

# Display values that mean "no link here" when the cell has no hyperlink.
NO_LINK_DISPLAY = {"n/a", "na", "no"}


@dataclass(frozen=True)
class ManuscriptRow:
    """A fully validated MANUSCRIPTS row, ready for the database.

    The EDITIONS sheet references manuscripts by copy id or by
    codex-within-text, so the editions linker needs codex_identifier and
    text_unique_id. links holds (link type label, url) pairs; relations
    holds (relation type label, target position in this row list) pairs.
    """

    excel_row: int
    identifier: str
    copy_id: str
    text_identifier: str | None  # None: reference resolves to no text
    text_unique_id: str
    codex_number: int | None
    codex_identifier: str | None
    codex_multiple_copies: bool | None
    codex_copy_amount: int | None
    preservation_label: str | None
    location_name: str | None
    institution_name: str | None
    height: str | None
    width: str | None
    dating_century: int | None
    dating_range_start: int | None
    dating_range_end: int | None
    dating_reference: str | None
    dating_confidence_label: str | None
    dating_note: str | None
    codex_legendiers_usable: bool | None
    codex_composite: bool | None
    codex_legendiers_entry_code: str | None
    codex_notes: str | None
    vernacular_region_label: str | None
    origin_archdiocese_name: str | None
    origin_diocese_name: str | None
    origin_diocese_gps: tuple[float, float] | None
    origin_diocese_confidence_label: str | None
    origin_institution_name: str | None
    origin_institution_confidence_label: str | None
    provenance_early_institute_name: str | None
    provenance_early_gps: tuple[float, float] | None
    provenance_early_confidence_label: str | None
    provenance_later_institute_name: str | None
    provenance_later_gps: tuple[float, float] | None
    origin_or_provenance_secondary_reference: str | None
    manuscript_type_label: str | None
    manuscript_type_note: str | None
    general_notes: str | None
    links: tuple[tuple[str, str], ...]
    relations: tuple[tuple[str, int], ...]


def _dating_range(raw: Any) -> tuple[int | None, bool]:
    """(value, parsed_ok): empty → NULL, non-integer → 0 (raw kept in note)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, True
    try:
        return strict_int(raw), True
    except CellError:
        return 0, False


def parse_sheet(
    ws: Worksheet, report: ImportReport, context: dict[str, list] | None = None
) -> list[ManuscriptRow]:
    """Phase 1 — validate every row; no database involved.

    Requires the parsed TEXTS rows in context to resolve the text link.
    Two passes: rows first, then the manuscript↔manuscript relations (which
    can only point at rows that themselves survived validation).
    """
    from .texts import _parse_gps

    text_identifiers = {t.identifier for t in (context or {}).get("TEXTS", [])}
    columns = header_map(
        ws,
        [spec.column for spec in SPECS.values()]
        + [DATING_RANGE_START_COLUMN, DATING_RANGE_END_COLUMN]
        + list(DIOCESE_GPS)
        + list(PROVENANCE_EARLY_GPS)
        + list(PROVENANCE_LATER_GPS)
        + [column for column, _ in LINK_COLUMNS]
        + [IMAGES_TYPE_COLUMN, IMAGES_LINK_COLUMN],
    )
    owner_positions = header_positions(ws, PROVENANCE_EARLY_OWNER_COLUMN)
    owner_conf_positions = header_positions(ws, PROVENANCE_EARLY_CONFIDENCE_COLUMN)
    if len(owner_positions) < 2 or len(owner_conf_positions) < 2:
        raise WorkbookError(
            f"sheet {SHEET!r}: expected the provenance early-owner and "
            "confidence headers twice (stray GPS pair + real data), found "
            f"{len(owner_positions)}/{len(owner_conf_positions)} occurrences"
        )
    early_owner_index = owner_positions[1]
    early_confidence_index = owner_conf_positions[1]
    report.register_columns(SHEET, columns)
    # The duplicated provenance headers resolve to their SECOND occurrence.
    report.register_columns(
        SHEET,
        {
            PROVENANCE_EARLY_OWNER_COLUMN: early_owner_index,
            PROVENANCE_EARLY_CONFIDENCE_COLUMN: early_confidence_index,
        },
    )

    hyperlinks = cell_hyperlinks(ws)
    letters = {column: get_column_letter(index + 1) for column, index in columns.items()}
    first_seen: dict[str, int] = {}

    def cell_url(excel_row: int, column: str) -> str | None:
        return hyperlinks.get(f"{letters[column]}{excel_row}")

    def collect_link(
        excel_row: int,
        column: str,
        type_label: str,
        raw: Any,
        links: list[tuple[str, str]],
    ) -> None:
        """Apply the link-cell rule to one cell (see module docstring)."""
        url = cell_url(excel_row, column)
        if url is not None:
            if url.startswith(("http://", "https://")):
                links.append((type_label, url))
            else:
                report.errors.append(
                    RowError(SHEET, excel_row, column, url,
                             "hyperlink is not an http(s) URL", severity="warning")
                )
            return
        display = str(raw).strip() if raw is not None else ""
        if display and display.casefold() not in NO_LINK_DISPLAY:
            report.errors.append(
                RowError(SHEET, excel_row, column, raw,
                         "cell suggests a link but has no hyperlink",
                         severity="warning")
            )

    def clean_name(excel_row: int, column: str, value: str | None) -> str | None:
        """A geography/owner name; Unknown/N/A → NULL, 'to be verified' warns."""
        if value is None or value.casefold() in {"unknown", "n/a"}:
            return None
        if value.casefold() == "to be verified":
            report.errors.append(
                RowError(SHEET, excel_row, column, value,
                         "not a name; no lookup row created", severity="warning")
            )
            return None
        return value

    def parse_gps(
        excel_row: int, values: tuple[Any, ...], gps_pair: tuple[str, str],
        name: str | None,
    ) -> tuple[float, float] | None:
        """A swapped, plain-degrees GPS pair; Unknown/N/A → no coordinates.

        Junk, out-of-range or nameless coordinates warn and are skipped
        (the row is kept).
        """
        def null_token(value: Any) -> Any:
            if isinstance(value, str) and value.strip().casefold() in {"", "unknown", "n/a"}:
                return None
            return value

        raw_lat = null_token(values[columns[gps_pair[0]]])
        raw_lon = null_token(values[columns[gps_pair[1]]])
        try:
            gps = _parse_gps(raw_lat, raw_lon, scale=1)
        except CellError as error:
            report.errors.append(
                RowError(SHEET, excel_row, gps_pair[0],
                         f"{raw_lat!r} / {raw_lon!r}", str(error),
                         severity="warning")
            )
            return None
        if gps is not None and name is None:
            report.errors.append(
                RowError(SHEET, excel_row, gps_pair[0], gps,
                         "coordinates without a name in the matching column; "
                         "no location created", severity="warning")
            )
            return None
        return gps

    # First pass: per-row validation (everything except relations).
    prelim: list[dict[str, Any]] = []
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

        # The real early-owner pair (second occurrence of duplicated headers).
        try:
            parsed["provenance_early"] = strict_str(values[early_owner_index])
        except CellError as error:
            report.errors.append(
                RowError(SHEET, excel_row, PROVENANCE_EARLY_OWNER_COLUMN,
                         values[early_owner_index], str(error))
            )
            row_ok = False
        try:
            parsed["provenance_early_confidence"] = _strict_confidence(
                values[early_confidence_index]
            )
        except CellError as error:
            report.errors.append(
                RowError(SHEET, excel_row, PROVENANCE_EARLY_CONFIDENCE_COLUMN,
                         values[early_confidence_index], str(error))
            )
            row_ok = False
        if not row_ok:
            continue

        prefix = parsed["bhl_prefix"].replace(" ", "_")
        text_identifier: str | None = f"{prefix}_{parsed['text_uid']}"
        unresolved_note = None
        if text_identifier not in text_identifiers:
            report.errors.append(
                RowError(
                    SHEET,
                    excel_row,
                    "Unique text identifier",
                    parsed["text_uid"],
                    f"no text with identifier {text_identifier!r} "
                    "(or its TEXTS row was rejected); "
                    "manuscript imported without text link",
                    severity="warning",
                )
            )
            unresolved_note = f"unresolved text reference: {text_identifier!r}"
            text_identifier = None

        identifier = f"{prefix}_{parsed['copy_id']}"
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
        if institution == NOT_APPLICABLE:
            institution = None

        # Dating range: 0 + raw note when a value is not an integer.
        raw_start = values[columns[DATING_RANGE_START_COLUMN]]
        raw_end = values[columns[DATING_RANGE_END_COLUMN]]
        range_start, start_ok = _dating_range(raw_start)
        range_end, end_ok = _dating_range(raw_end)
        dating_note = None
        if not (start_ok and end_ok):
            dating_note = f"dating range in workbook: start={raw_start!r}, end={raw_end!r}"

        # A hyperlinked reference cell means the URL, not the display text.
        dating_reference = (
            cell_url(excel_row, "Preferred secondary reference for manuscript dating")
            or parsed["dating_reference"]
        )
        secondary_reference = (
            cell_url(
                excel_row,
                "Manuscript origin and provenance preferred secondary reference",
            )
            or parsed["secondary_reference"]
        )

        vernacular = parsed["vernacular"]
        if vernacular is not None and vernacular.casefold() in {"unknown", "n/a"}:
            vernacular = None
        elif vernacular is not None and vernacular not in VERNACULAR_LABELS:
            report.errors.append(
                RowError(SHEET, excel_row, "Vernacular region (Romance/Germanic)",
                         vernacular,
                         f"expected one of {sorted(VERNACULAR_LABELS)}, Unknown or "
                         "N/A; no region linked", severity="warning")
            )
            vernacular = None

        type_raw = parsed["manuscript_type"]
        type_label = re.sub(r"\s+", " ", type_raw) if type_raw else None

        # Geography names first, then their GPS pairs (a pair without a name
        # cannot become a location and only warns).
        origin_diocese_name = clean_name(
            excel_row, "Manuscript origin by diocese", parsed["origin_diocese"]
        )
        provenance_early_name = clean_name(
            excel_row, PROVENANCE_EARLY_OWNER_COLUMN, parsed["provenance_early"]
        )
        provenance_later_name = clean_name(
            excel_row,
            "Manuscript provenance by undetermined or later institutional owner",
            parsed["provenance_later"],
        )
        origin_diocese_gps = parse_gps(
            excel_row, values, DIOCESE_GPS, origin_diocese_name
        )
        provenance_early_gps = parse_gps(
            excel_row, values, PROVENANCE_EARLY_GPS, provenance_early_name
        )
        provenance_later_gps = parse_gps(
            excel_row, values, PROVENANCE_LATER_GPS, provenance_later_name
        )

        links: list[tuple[str, str]] = []
        for column, link_type_label in LINK_COLUMNS:
            collect_link(excel_row, column, link_type_label, values[columns[column]], links)

        raw_type = values[columns[IMAGES_TYPE_COLUMN]]
        raw_images = values[columns[IMAGES_LINK_COLUMN]]
        type_text = (
            re.sub(r"\s+", " ", str(raw_type)).strip() if raw_type is not None else ""
        )
        if not type_text or type_text.casefold() in {"no", "n/a"}:
            if cell_url(excel_row, IMAGES_LINK_COLUMN):
                report.errors.append(
                    RowError(SHEET, excel_row, IMAGES_LINK_COLUMN, raw_images,
                             f"image link present but {IMAGES_TYPE_COLUMN!r} "
                             f"is {type_text or 'empty'!r}", severity="warning")
                )
        else:
            image_label = IMAGE_TYPE_LABELS.get(type_text.casefold())
            if image_label is None:
                report.errors.append(
                    RowError(SHEET, excel_row, IMAGES_TYPE_COLUMN, raw_type,
                             "unrecognized image type (expected SCAN, IIIF, "
                             "IIIF MF or IPhone pictures); image link skipped",
                             severity="warning")
                )
            else:
                collect_link(excel_row, IMAGES_LINK_COLUMN, image_label, raw_images, links)

        prelim.append(
            dict(
                excel_row=excel_row,
                identifier=identifier,
                copy_id=parsed["copy_id"],
                text_identifier=text_identifier,
                text_unique_id=parsed["text_uid"],
                codex_number=parsed["codex_number"],
                codex_identifier=parsed["codex"],
                codex_multiple_copies=parsed["codex_multiple_copies"],
                codex_copy_amount=parsed["codex_copy_amount"],
                preservation_label=parsed["preservation"],
                location_name=parsed["location"],
                institution_name=institution,
                height=parsed["height"],
                width=parsed["width"],
                dating_century=parsed["dating_century"],
                dating_range_start=range_start,
                dating_range_end=range_end,
                dating_reference=dating_reference,
                dating_confidence_label=parsed["dating_confidence"],
                dating_note=dating_note,
                codex_legendiers_usable=parsed["legendiers_usable"],
                codex_composite=parsed["composite"],
                codex_legendiers_entry_code=parsed["legendiers_code"],
                codex_notes=parsed["codex_notes"],
                vernacular_region_label=vernacular,
                origin_archdiocese_name=clean_name(
                    excel_row, "Manuscript origin by archdiocese",
                    parsed["origin_archdiocese"],
                ),
                origin_diocese_name=origin_diocese_name,
                origin_diocese_gps=origin_diocese_gps,
                origin_diocese_confidence_label=parsed["origin_diocese_confidence"],
                origin_institution_name=clean_name(
                    excel_row, "Manuscript origin by institution",
                    parsed["origin_institution"],
                ),
                origin_institution_confidence_label=parsed[
                    "origin_institution_confidence"
                ],
                provenance_early_institute_name=provenance_early_name,
                provenance_early_gps=provenance_early_gps,
                provenance_early_confidence_label=parsed[
                    "provenance_early_confidence"
                ],
                provenance_later_institute_name=provenance_later_name,
                provenance_later_gps=provenance_later_gps,
                origin_or_provenance_secondary_reference=secondary_reference,
                manuscript_type_label=type_label,
                manuscript_type_note=type_raw,
                general_notes="; ".join(
                    note for note in (unresolved_note, parsed["notes"]) if note
                )
                or None,
                links=tuple(links),
                based_on_ref=parsed["based_on"],
                exemplar_of_ref=parsed["exemplar_of"],
            )
        )

    # Name ↔ GPS consistency (first wins; conflicts warned once per distinct
    # collision — the same collision repeats across many rows), mirroring the
    # TEXTS sheet. Dioceses and institutions are separate name spaces; the
    # early and later provenance owners share the institution one.
    gps_by_name: dict[tuple[str, str], tuple[float, float]] = {}
    location_names: dict[tuple[float, float], str] = {}
    warned: set[tuple] = set()
    for row in prelim:
        for kind, name_key, gps_key, column in (
            ("diocese", "origin_diocese_name", "origin_diocese_gps",
             "Manuscript origin by diocese"),
            ("institution", "provenance_early_institute_name",
             "provenance_early_gps", PROVENANCE_EARLY_OWNER_COLUMN),
            ("institution", "provenance_later_institute_name",
             "provenance_later_gps",
             "Manuscript provenance by undetermined or later institutional owner"),
        ):
            name, gps = row[name_key], row[gps_key]
            if not name or gps is None:
                continue
            key = (kind, name)
            if key in gps_by_name and gps_by_name[key] != gps:
                if (key, gps) not in warned:
                    warned.add((key, gps))
                    report.errors.append(
                        RowError(
                            SHEET, row["excel_row"], column, name,
                            f"{kind} already located at {gps_by_name[key]}, "
                            f"also seen at {gps} (first wins)",
                            severity="warning",
                        )
                    )
                continue
            gps_by_name.setdefault(key, gps)
            if gps in location_names and location_names[gps] != name:
                if ("loc", gps, name) not in warned:
                    warned.add(("loc", gps, name))
                    report.errors.append(
                        RowError(
                            SHEET, row["excel_row"], column, name,
                            f"coordinates {gps} already named "
                            f"{location_names[gps]!r} (first name wins)",
                            severity="warning",
                        )
                    )
            location_names.setdefault(gps, name)

    # Relation vocabularies, built from surviving rows only (the same refs
    # the EDITIONS sheet uses: copy id, or codex id within the row's text).
    by_copy: dict[str, int] = {}
    by_text_codex: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(prelim):
        by_copy.setdefault(row["copy_id"], index)
        if row["codex_identifier"]:
            by_text_codex.setdefault(
                (row["text_unique_id"], row["codex_identifier"]), []
            ).append(index)

    def resolve_relation(index: int, column: str, ref: str) -> int | None:
        """Copy identifier first, then codex identifier within the same text."""
        row = prelim[index]
        if ref in by_copy:
            target = by_copy[ref]
        else:
            candidates = by_text_codex.get((row["text_unique_id"], ref), [])
            if len(candidates) != 1:
                reason = (
                    f"ambiguous manuscript reference ({len(candidates)} matches)"
                    if candidates
                    else "unresolvable manuscript reference (no copy identifier "
                    "or same-text codex identifier matches)"
                )
                report.errors.append(
                    RowError(SHEET, row["excel_row"], column, ref, reason,
                             severity="warning")
                )
                return None
            target = candidates[0]
        if target == index:
            report.errors.append(
                RowError(SHEET, row["excel_row"], column, ref,
                         "manuscript references itself", severity="warning")
            )
            return None
        return target

    # Second pass: resolve relations and freeze the rows.
    rows: list[ManuscriptRow] = []
    for index, row in enumerate(prelim):
        relations: list[tuple[str, int]] = []
        for key, type_label in RELATION_COLUMNS:
            raw_ref = row.pop(f"{key}_ref")
            if raw_ref is None:
                continue
            for ref in (r.strip() for r in raw_ref.split(",")):
                if not ref or ref.casefold() in {"n/a", "unknown", "no"}:
                    continue
                target = resolve_relation(index, SPECS[key].column, ref)
                if target is not None:
                    relations.append((type_label, target))
        rows.append(ManuscriptRow(relations=tuple(relations), **row))

    report.parsed += len(rows)
    return rows


def _canonical_institutions(rows: list[ManuscriptRow]) -> dict[str, str]:
    """Map each raw holding-institution name to its canonical form.

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
    """Phase 2 — insert lookups, manuscript rows, then link/relation rows.

    Caller commits.
    """
    from .texts import _lookup_ids

    text_ids = {
        identifier: pk
        for identifier, pk in session.exec(select(Text.identifier, Text.text_id)).all()
    }
    canonical = _canonical_institutions(rows)

    statuses = _lookup_ids(
        session,
        ManuscriptPreservationStatus,
        {r.preservation_label for r in rows if r.preservation_label},
    )
    holding_institutions = _lookup_ids(
        session, ManuscriptHoldingInstitution, set(canonical.values()), attr="name"
    )
    confidences = _lookup_ids(
        session,
        DatingConfidence,
        {r.dating_confidence_label for r in rows if r.dating_confidence_label},
    )
    # Manuscript locations are bare place names; new ones get no coordinates.
    locations = _lookup_ids(
        session, Location, {r.location_name for r in rows if r.location_name}, attr="name"
    )
    link_types = _lookup_ids(session, ManuscriptLinkType, set(LINK_TYPE_LABELS))
    vernacular_regions = _lookup_ids(
        session,
        VernacularRegion,
        {r.vernacular_region_label for r in rows if r.vernacular_region_label},
    )
    archdioceses = _lookup_ids(
        session,
        Archdiocese,
        {r.origin_archdiocese_name for r in rows if r.origin_archdiocese_name},
        attr="name",
    )
    dioceses = _lookup_ids(
        session,
        Diocese,
        {r.origin_diocese_name for r in rows if r.origin_diocese_name},
        attr="name",
    )
    institutions = _lookup_ids(
        session,
        Institution,
        {
            name
            for r in rows
            for name in (
                r.origin_institution_name,
                r.provenance_early_institute_name,
                r.provenance_later_institute_name,
            )
            if name
        },
        attr="name",
    )
    origin_confidences = _lookup_ids(
        session,
        OriginConfidence,
        {
            label
            for r in rows
            for label in (
                r.origin_diocese_confidence_label,
                r.origin_institution_confidence_label,
            )
            if label
        },
    )
    provenance_confidences = _lookup_ids(
        session,
        ProvenanceConfidence,
        {
            r.provenance_early_confidence_label
            for r in rows
            if r.provenance_early_confidence_label
        },
    )
    manuscript_types = _lookup_ids(
        session,
        ManuscriptType,
        {r.manuscript_type_label for r in rows if r.manuscript_type_label},
    )
    relation_types = _lookup_ids(
        session, ManuscriptRelationshipType, set(RELATION_TYPE_LABELS)
    )

    # Geography locations: every archdiocese/diocese/institution named on
    # this sheet gets a location_id — a coordinate-deduplicated location when
    # GPS is known (first name wins, parse phase warned about conflicts), a
    # name-keyed location with NULL coordinates otherwise. Locations already
    # in the database (TEXTS import, manuscript places) are reused; an
    # entity's existing location_id (e.g. set by the TEXTS import) wins.
    diocese_gps: dict[str, tuple[float, float]] = {}
    institution_gps: dict[str, tuple[float, float]] = {}
    for r in rows:
        if r.origin_diocese_name and r.origin_diocese_gps:
            diocese_gps.setdefault(r.origin_diocese_name, r.origin_diocese_gps)
        if r.provenance_early_institute_name and r.provenance_early_gps:
            institution_gps.setdefault(
                r.provenance_early_institute_name, r.provenance_early_gps
            )
        if r.provenance_later_institute_name and r.provenance_later_gps:
            institution_gps.setdefault(
                r.provenance_later_institute_name, r.provenance_later_gps
            )

    location_by_coords: dict[tuple[float, float], int] = {
        (location.latitude, location.longitude): location.location_id
        for location in session.exec(
            select(Location).where(Location.latitude.is_not(None))  # type: ignore[union-attr]
        ).all()
    }

    def coords_location_id(name: str, gps: tuple[float, float]) -> int:
        if gps not in location_by_coords:
            location = Location(name=name, latitude=gps[0], longitude=gps[1])
            session.add(location)
            session.flush()
            location_by_coords[gps] = location.location_id
        return location_by_coords[gps]

    # Coordinate locations first, so the name-only fallback below reuses them
    # by name instead of creating NULL-coordinate duplicates.
    unlocated_named: list[tuple[Any, str]] = []
    for model, ids_by_name, gps_map in (
        (Archdiocese, archdioceses, {}),
        (Diocese, dioceses, diocese_gps),
        (Institution, institutions, institution_gps),
    ):
        for name, entity_id in ids_by_name.items():
            entity = session.get(model, entity_id)
            if entity.location_id is not None:
                continue
            gps = gps_map.get(name)
            if gps is not None:
                entity.location_id = coords_location_id(name, gps)
            else:
                unlocated_named.append((entity, name))
    name_location_ids = _lookup_ids(
        session, Location, {name for _, name in unlocated_named}, attr="name"
    )
    for entity, name in unlocated_named:
        entity.location_id = name_location_ids[name]

    def lookup(ids: dict[str, int], label: str | None) -> int | None:
        return ids[label] if label else None

    manuscripts = [
        Manuscript(
            identifier=row.identifier,
            text_id=text_ids.get(row.text_identifier) if row.text_identifier else None,
            codex_number=row.codex_number,
            codex_identifier=row.codex_identifier,
            codex_multiple_copies=row.codex_multiple_copies,
            codex_copy_amount=row.codex_copy_amount,
            manuscript_preservation_status_id=lookup(statuses, row.preservation_label),
            location_id=lookup(locations, row.location_name),
            manuscript_holding_institution_id=lookup(
                holding_institutions,
                canonical[row.institution_name] if row.institution_name else None,
            ),
            height=row.height,
            width=row.width,
            dating_century=row.dating_century,
            dating_range_start=row.dating_range_start,
            dating_range_end=row.dating_range_end,
            dating_reference=row.dating_reference,
            dating_confidence_id=lookup(confidences, row.dating_confidence_label),
            dating_note=row.dating_note,
            codex_legendiers_usable=row.codex_legendiers_usable,
            codex_composite=row.codex_composite,
            codex_legendiers_entry_code=row.codex_legendiers_entry_code,
            codex_notes=row.codex_notes,
            vernacular_region_id=lookup(
                vernacular_regions, row.vernacular_region_label
            ),
            origin_archdiocese_id=lookup(archdioceses, row.origin_archdiocese_name),
            origin_diocese_id=lookup(dioceses, row.origin_diocese_name),
            origin_diocese_confidence_rating_id=lookup(
                origin_confidences, row.origin_diocese_confidence_label
            ),
            origin_institution_id=lookup(institutions, row.origin_institution_name),
            origin_institution_confidence_rating_id=lookup(
                origin_confidences, row.origin_institution_confidence_label
            ),
            provenance_early_institute_id=lookup(
                institutions, row.provenance_early_institute_name
            ),
            provenance_early_confidence_id=lookup(
                provenance_confidences, row.provenance_early_confidence_label
            ),
            provenance_later_institute_id=lookup(
                institutions, row.provenance_later_institute_name
            ),
            provenance_later_confidence_id=None,  # no source column yet
            origin_or_provenance_secondary_reference=(
                row.origin_or_provenance_secondary_reference
            ),
            manuscript_type_id=lookup(manuscript_types, row.manuscript_type_label),
            manuscript_type_note=row.manuscript_type_note,
            general_notes=row.general_notes,
        )
        for row in rows
    ]
    session.add_all(manuscripts)
    session.flush()  # assign manuscript_ids for the link/relation rows

    link_count = relation_count = 0
    for row, manuscript in zip(rows, manuscripts):
        for type_label, url in row.links:
            session.add(
                ManuscriptLink(
                    manuscript_id=manuscript.manuscript_id,
                    manuscript_link_type_id=link_types[type_label],
                    url=url,
                )
            )
            link_count += 1
        for type_label, target in row.relations:
            session.add(
                ManuscriptRelation(
                    manuscript_id=manuscript.manuscript_id,
                    related_manuscript_id=manuscripts[target].manuscript_id,
                    manuscript_relationship_type_id=relation_types[type_label],
                )
            )
            relation_count += 1
    log.info(
        "staged %d manuscript rows, %d links, %d relations for insert",
        len(rows), link_count, relation_count,
    )
    return len(rows)
