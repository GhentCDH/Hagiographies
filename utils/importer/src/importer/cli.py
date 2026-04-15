# cli.py
# ---------------------------------------------------------------------------
# Import hagiographies.xlsx into the SQLite database.
#
# Changelog (validated against hagiographies.xlsx):
#
#   - parse_yesno / cyesno return True/False/None (not 1/0/None).
#
#   - Author location and milieu are resolved in import_texts and passed to
#     _get_or_create_author, which writes them on the Author record.  If the
#     same author appears in a later row with additional location data the
#     function back-fills only NULL fields, preserving earlier values.
#
#   - 'Locally based in Origin': not a clean boolean in the source
#     ("Unknown/Metz?", "Yes (Sankt Pantaleon?)").  The raw value is stored
#     on Text.author_locally_based.  A starts-with-"yes" check (case-
#     insensitive) is still used to decide whether to assign origin_place_id
#     as the author's place_id — this matches the original intent while
#     tolerating the qualified values.
#
#   - 'Full OCR/XML available?': contains BHL reference strings, not yes/no.
#     Stored as Text.full_ocr_bhl_refs (free text) via cval(), not cyesno().
#
#   - 'Cleaned?' has a third value 'Unpublished'; parse_yesno returns None
#     for it, stored as NULL in is_ocr_cleaned.
#
#   - ImageAvailability lookup removed.  When the 'IIIF, scan, or no images'
#     column indicates images should exist but no URL is extractable, a
#     WARNING is logged and an 'image_warning' entry is added to the report.
#
#   - Edition.has_scan removed; scan URL stored via EditionExternalResource.
#   - Edition.checked_leg removed (field gone from model).
#   - Edition.reprint_type derived from the two former boolean columns.
#
#   - Text.reecriture_of renamed rewrite_notes (free text, not a FK).
#   - 'Check  Philippart' header has a double space; both variants tried.
#
#   - All renamed model fields, relationship names, and import list updated.
# ---------------------------------------------------------------------------

import logging
import re
import unicodedata
from itertools import islice
from typing import Any, Dict, Generator, List, Optional, Tuple

from openpyxl import load_workbook
from openpyxl.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet
from rich.logging import RichHandler
from sqlmodel import SQLModel, Session, select

from utilities.config import EXCEL, DATA_ROOT, DB_PATH
from utilities.db import create_updated_at_trigger, engine
from utilities.model import (
    Author,
    ChurchEntity,
    DatingCentury,
    Edition,
    EditionExternalResource,
    EditionManuscript,
    ExternalResource,
    ExternalResourceType,
    Image,
    ImageType,
    Institution,
    Manuscript,
    ManuscriptIdentifier,
    ManuscriptRelation,
    ManuscriptText,
    ManuscriptType,
    Milieu,
    Place,
    ProvenanceGeneral,
    RelationType,
    ReprintType,
    Certainty,
    Text,
    TextType,
    Typology,
    VernacularRegion,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

handler = RichHandler(
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    markup=True,
    show_time=True,
    show_path=True,
)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMPTY_ROW_LIMIT = 10
_EDITION_MS_COL_INDICES = list(range(22, 38))
_EDITION_EDITION_COL_INDICES = list(range(38, 43))

_COL_MS_NASO = "NASO"
_COL_MS_FOLIO = "Folio or page per BHL"
_COL_MS_DATING_CENTURY = "Dating by (earliest) century"
_COL_MS_VERNACULAR = "Vernacular region (Romance/Germanic)"
_COL_MS_COLLECTION_ID = "Unique  identifier per collection"
_COL_MS_CATALOGUE = "Online catalogue link"
_COL_MS_BOLLANDIST = "Bollandist catalogue link"
_COL_MS_OTHER_CATALOGUE = "Other relevant catalogue link"
_COL_MS_IMAGE_AVAIL = "IIIF, scan, or no images"
_COL_MS_IMAGES = "Link to images"
_COL_MS_RELATIONS = "Relation to other manuscript witnesses?"
_COL_MS_EXEMPLAR_CERTAIN = " Certain?"

_MANUSCRIPT_RESOURCE_COLS: List[Tuple[str, str]] = [
    (_COL_MS_CATALOGUE, "catalog_link"),
    (_COL_MS_BOLLANDIST, "bollandist_catalog"),
    (_COL_MS_OTHER_CATALOGUE, "catalog_link"),
]

_COPY_OF_COLS = [
    "Copy of which first exemplar?",
    "Copy of which second exemplar?",
    "Copy of which third exemplar?",
]

_EXEMPLAR_OF_COLS = [
    "Exemplar of which manuscript (1)?",
    "Exemplar of which manuscript (2)?",
    "Exemplar of which manuscript (3)?",
    "Exemplar of which manuscript (4)?",
]

_COL_ED_BHL = "BHL"
_COL_ED_ID = "Ed. reference per individual text"
_COL_ED_UID_NUM = "Unique ED ID"
_COL_ED_UID_DESC = "Unique  identifier per edition + volume"
_COL_ED_YEAR = "Date"
_COL_ED_BIBREF = "Edition reference"
_COL_ED_PAGES = "Pages"
_COL_ED_REPRINT_OF = "If reprint, of what?"
_COL_ED_SCAN_LINK = "Online scan link"
_COL_ED_TRANSCRIBED = "Transcribed?"
_COL_ED_COLLATED = "Collation done?"

# 'Check  Philippart' has a double space in the actual worksheet header.
_COL_CHECK_PHILIPPART_VARIANTS = ("Check  Philippart", "Check Philippart")

# Image availability values that indicate *no* images are expected.
_NO_IMAGE_VALUES = {"NO", "NO IMAGES", ""}


# ---------------------------------------------------------------------------
# Pure value helpers
# ---------------------------------------------------------------------------

def normalize_id(val: Any) -> str:
    """Normalise a collection identifier for cache-key comparison."""
    if not val:
        return ""
    s = str(val).strip().lower()
    if "(" in s:
        s = s.split("(")[0].strip()
    return re.sub(r"\s+", " ", s)


def clean_value(val: Any) -> Optional[str]:
    """Return a stripped string or None for empty / NaN-like values."""
    if val is None or val == "" or str(val).lower() == "nan":
        return None
    s = str(val).strip()
    return s if s else None


def parse_int(val: Any) -> Tuple[Optional[int], bool]:
    """Parse an integer, returning (value, success)."""
    if val is None:
        return None, True
    try:
        return int(val), True
    except (ValueError, TypeError):
        return None, False


def parse_float(val: Any) -> Optional[float]:
    """Parse a float, returning None on failure."""
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def parse_yesno(val: Any) -> Optional[bool]:
    """Convert a yes/no Excel value to a Python bool.

    Recognises common variants in English, French and Dutch.
    Returns None for blank, unrecognised, or qualified values
    (e.g. 'Unpublished', 'to be verified', 'Unknown').
    """
    if val is None:
        return None
    s = str(val).strip().upper()
    if s in ("Y", "YES", "1", "TRUE", "OUI", "JA"):
        return True
    if s in ("N", "NO", "0", "FALSE", "NON", "NEE"):
        return False
    return None


def _locally_based_implies_place(raw_val: Optional[str]) -> bool:
    """Return True when the 'Locally based' column value starts with 'yes'.

    Used only to decide whether to assign origin_place_id as author.place_id.
    The raw string is still stored verbatim on Text.author_locally_based.
    """
    if not raw_val:
        return False
    return raw_val.strip().lower().startswith("yes")


def _is_empty_row(row_cells_list: List[Cell]) -> bool:
    return all(c.value is None or str(c.value).strip() == "" for c in row_cells_list)


def _iter_data_rows(
    rows_iter, sheet_title: str = "", empty_limit: int = EMPTY_ROW_LIMIT
) -> Generator[Tuple[int, List[Cell]], None, None]:
    """Yield (1-based row number, cell list) pairs, stopping after *empty_limit* consecutive empty rows."""
    consecutive_empty = 0
    for row_num, row_cells in enumerate(rows_iter, start=2):
        row_cells_list = list(row_cells)
        if _is_empty_row(row_cells_list):
            consecutive_empty += 1
            if consecutive_empty >= empty_limit:
                logger.info(
                    f"[{sheet_title}] {empty_limit} consecutive empty rows "
                    f"at row {row_num} — stopping early."
                )
                return
            continue
        consecutive_empty = 0
        yield row_num, row_cells_list


URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def _extract_hyperlink_url(cell: Cell) -> Optional[str]:
    """Extract the target URL from an Excel cell, ignoring display text."""
    if cell is None:
        return None
    if cell.hyperlink:
        target = (
            getattr(cell.hyperlink, "target", None)
            or getattr(cell.hyperlink, "location", None)
        )
        if target:
            target_str = str(target).strip()
            if URL_RE.match(target_str):
                return target_str
    value = cell.value
    if isinstance(value, str):
        val_str = value.strip()
        if URL_RE.match(val_str):
            return val_str
    return None


def _normalize_name(value: Optional[str]) -> Optional[str]:
    """Normalise a place, institution or author name: lowercase, collapse whitespace, fold accents."""
    if not value:
        return None
    value = " ".join(value.strip().split()).lower()
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    return value or None


def _normalize_col(col: str) -> str:
    """Normalise a column lookup key: strip outer whitespace and collapse inner whitespace.

    Applied in cval/cint/cfloat/cyesno so that lookup keys are always
    consistent with the stripped headers produced by _read_headers.
    Fixes historic trailing-space bugs (e.g. 'MGH ' and 'Dating ').
    """
    return re.sub(r'\s+', ' ', col.strip())


def _validate_url(
    url: str, excel_row: int, col_name: str, report: "ImportReport"
) -> Optional[str]:
    """Validate a URL string; log and return None if malformed."""
    if not URL_RE.match(url):
        report.add(
            "url_skipped",
            {"Row": excel_row, "Column": col_name, "URL": url, "Reason": "Malformed URL"},
        )
        return None
    return url


_IMAGE_TYPE_MAP = [
    ("IIIF MF", "iiif_mf"),
    ("IIIF", "iiif"),
    ("SCAN", "scan"),
    ("IPHONE", "iphone_photo"),
]


def _infer_image_type(image_availability: Optional[str]) -> str:
    """Infer an ImageType name from the free-text image-availability column."""
    aa = (image_availability or "").upper()
    for marker, itype in _IMAGE_TYPE_MAP:
        if marker in aa:
            return itype
    return "scan"


# ---------------------------------------------------------------------------
# Cached get_or_create helpers
# ---------------------------------------------------------------------------

def _get_or_create_resource(
    url: str,
    resource_type: str,
    comment: Optional[str],
    cache: Dict[str, ExternalResource],
    session: Session,
    manuscript_id: Optional[int] = None,
) -> ExternalResource:
    """Return an ExternalResource for *url*, creating it if absent."""
    if url in cache:
        return cache[url]
    query = select(ExternalResource).where(ExternalResource.url == url)
    if manuscript_id:
        query = query.where(ExternalResource.manuscript_id == manuscript_id)
    else:
        query = query.where(ExternalResource.manuscript_id == None)  # noqa: E711
    existing = session.exec(query).first()
    if existing:
        cache[url] = existing
        return existing
    try:
        rtype_enum = ExternalResourceType(resource_type)
    except ValueError:
        rtype_enum = ExternalResourceType.other
    resource = ExternalResource(
        url=url,
        resource_type=rtype_enum,
        comment=comment,
        manuscript_id=manuscript_id,
    )
    session.add(resource)
    session.flush()
    cache[url] = resource
    return resource


def _get_or_create_place(
    session: Session,
    name: Optional[str],
    cache: Dict[str, Place],
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Optional[int]:
    """Return the id of a Place, creating it if absent. Updates coordinates if missing."""
    if not name:
        return None
    raw_name = name.strip()
    norm_name = _normalize_name(raw_name)
    if norm_name in cache:
        return cache[norm_name].id
    existing_all = session.exec(select(Place)).all()
    matched = next(
        (p for p in existing_all if _normalize_name(p.name) == norm_name), None
    )
    if matched:
        if lat and not matched.lat:
            matched.lat = lat
        if lon and not matched.lon:
            matched.lon = lon
        cache[norm_name] = matched
        return matched.id
    place = Place(name=raw_name, lat=lat, lon=lon)
    session.add(place)
    session.flush()
    cache[norm_name] = place
    return place.id


def _get_or_create_institution(
    session: Session,
    name: Optional[str],
    place_id: Optional[int],
    cache: Dict[str, Institution],
) -> Optional[int]:
    """Return the id of an Institution, creating it if absent."""
    if not name:
        return None
    raw_name = name.strip()
    norm_name = _normalize_name(raw_name)
    if norm_name in cache:
        return cache[norm_name].id
    existing_all = session.exec(select(Institution)).all()
    matched = next(
        (i for i in existing_all if _normalize_name(i.name) == norm_name), None
    )
    if matched:
        if place_id and not matched.place_id:
            matched.place_id = place_id
        cache[norm_name] = matched
        return matched.id
    inst = Institution(name=raw_name, place_id=place_id)
    session.add(inst)
    session.flush()
    cache[norm_name] = inst
    return inst.id


def _get_or_create_author(
    session: Session,
    name: Optional[str],
    cache: Dict[str, Author],
    place_id: Optional[int] = None,
    education_place_id: Optional[int] = None,
    earlier_place_id: Optional[int] = None,
    milieu_id: Optional[int] = None,
) -> Optional[int]:
    """Return the id of an Author, creating it if absent.

    Location and milieu fields are written on creation.  For an existing
    Author, each field is back-filled only when it is currently NULL, so that
    the first non-null value encountered wins without overwriting richer data
    from a previous row.

    Author names are normalised with NFKD + ASCII-fold + lowercase (same logic
    as _get_or_create_place) so that accent variants and extra whitespace do
    not produce duplicate Author records.  The *stored* name preserves the
    original casing from the first occurrence that created the record.
    """
    if not name:
        return None
    raw_name = name.strip()
    norm_name = _normalize_name(raw_name)
    if not norm_name:
        return None

    def _backfill(auth: Author) -> None:
        if place_id and not auth.place_id:
            auth.place_id = place_id
        if education_place_id and not auth.education_place_id:
            auth.education_place_id = education_place_id
        if earlier_place_id and not auth.earlier_place_id:
            auth.earlier_place_id = earlier_place_id
        if milieu_id and not auth.milieu_id:
            auth.milieu_id = milieu_id

    if norm_name in cache:
        _backfill(cache[norm_name])
        return cache[norm_name].id

    existing_all = session.exec(select(Author)).all()
    matched = next(
        (a for a in existing_all if _normalize_name(a.name) == norm_name), None
    )
    if matched:
        _backfill(matched)
        cache[norm_name] = matched
        return matched.id

    auth = Author(
        name=raw_name,
        place_id=place_id,
        education_place_id=education_place_id,
        earlier_place_id=earlier_place_id,
        milieu_id=milieu_id,
    )
    session.add(auth)
    session.flush()
    cache[norm_name] = auth
    return auth.id


def _get_or_create_typology(
    session: Session,
    name: Optional[str],
    parent_id: Optional[int],
    cache: Dict[str, Typology],
) -> Optional[int]:
    """Return the id of a Typology entry, creating it if absent."""
    if not name:
        return None
    name = name.strip()
    if name in cache:
        return cache[name].id
    existing = session.exec(select(Typology).where(Typology.name == name)).first()
    if existing:
        if parent_id and not existing.parent_id:
            existing.parent_id = parent_id
        cache[name] = existing
        return existing.id
    typo = Typology(name=name, parent_id=parent_id)
    session.add(typo)
    session.flush()
    cache[name] = typo
    return typo.id


def _get_or_create_manuscript_type(
    session: Session, name: Optional[str], cache: Dict[str, ManuscriptType]
) -> Optional[int]:
    """Return the id of a ManuscriptType entry, creating it if absent."""
    if not name:
        return None
    name = name.strip()
    if name in cache:
        return cache[name].id
    existing = session.exec(
        select(ManuscriptType).where(ManuscriptType.name == name)
    ).first()
    if existing:
        cache[name] = existing
        return existing.id
    mt = ManuscriptType(name=name)
    session.add(mt)
    session.flush()
    cache[name] = mt
    return mt.id


def _get_or_create_text_type(
    session: Session, name: Optional[str], cache: Dict[str, TextType]
) -> Optional[int]:
    """Return the id of a TextType entry, creating it if absent."""
    if not name:
        return None
    name = name.strip()
    if name in cache:
        return cache[name].id
    existing = session.exec(select(TextType).where(TextType.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    obj = TextType(name=name)
    session.add(obj)
    session.flush()
    cache[name] = obj
    return obj.id


def _get_or_create_image_type(
    session: Session, name: Optional[str], cache: Dict[str, ImageType]
) -> Optional[int]:
    """Return the id of an ImageType entry, creating it if absent."""
    if not name:
        return None
    name = name.strip()
    if name in cache:
        return cache[name].id
    existing = session.exec(select(ImageType).where(ImageType.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    obj = ImageType(name=name)
    session.add(obj)
    session.flush()
    cache[name] = obj
    return obj.id


def _get_or_create_milieu(
    session: Session, name: Optional[str], cache: Dict[str, Milieu]
) -> Optional[int]:
    """Return the id of a Milieu entry, creating it if absent."""
    if not name:
        return None
    name = name.strip()
    if name in cache:
        return cache[name].id
    existing = session.exec(select(Milieu).where(Milieu.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    m = Milieu(name=name)
    session.add(m)
    session.flush()
    cache[name] = m
    return m.id


def _get_or_create_church_entity(
    session: Session,
    name: Optional[str],
    entity_type: str,
    cache: Dict[str, ChurchEntity],
) -> Optional[int]:
    """Return the id of a ChurchEntity, creating it if absent.

    entity_type must be 'archdiocese' or 'diocese'.  The unique constraint
    in the database covers (name, entity_type), so 'Trier' can legitimately
    exist as two separate rows — one per ecclesiastical level — and the
    Kottster UI no longer shows spurious 'Trier Trier' duplicates.
    """
    if not name:
        return None
    name = name.strip()
    cache_key = f"{name}|{entity_type}"
    if cache_key in cache:
        return cache[cache_key].id
    existing = session.exec(
        select(ChurchEntity).where(
            ChurchEntity.name == name,
            ChurchEntity.entity_type == entity_type,
        )
    ).first()
    if existing:
        cache[cache_key] = existing
        return existing.id
    ce = ChurchEntity(name=name, entity_type=entity_type)
    session.add(ce)
    session.flush()
    cache[cache_key] = ce
    return ce.id


def _get_or_create_ms_identifier(
    session: Session,
    title: Optional[str],
    bhl: Optional[str],
    cache: Dict[str, ManuscriptIdentifier],
) -> Optional[int]:
    """Return the id of a ManuscriptIdentifier, creating it if absent."""
    if not title:
        return None
    title = title.strip()
    bhl = bhl.strip() if bhl else None
    key = f"{title}|{bhl or ''}"
    if key in cache:
        return cache[key].id
    existing = session.exec(
        select(ManuscriptIdentifier).where(
            ManuscriptIdentifier.title == title,
            ManuscriptIdentifier.bhl_number == bhl,
        )
    ).first()
    if existing:
        cache[key] = existing
        return existing.id
    obj = ManuscriptIdentifier(
        title=title,
        bhl_number=bhl,
        identifier=f"{title} ({bhl})" if bhl else title,
    )
    session.add(obj)
    session.flush()
    cache[key] = obj
    return obj.id


def _get_or_create_dating_century(
    session: Session,
    century_val: Optional[Any],
    cache: Dict[int, DatingCentury],
) -> Optional[int]:
    """Return the id of a DatingCentury row, creating it if absent."""
    if century_val is None or str(century_val).strip() == "":
        return None
    try:
        century = int(float(century_val))
    except (ValueError, TypeError):
        return None
    if century in cache:
        return cache[century].id
    existing = session.exec(
        select(DatingCentury).where(DatingCentury.century == century)
    ).first()
    if existing:
        cache[century] = existing
        return existing.id
    obj = DatingCentury(century=century)
    session.add(obj)
    session.flush()
    cache[century] = obj
    return obj.id


def _get_or_create_vernacular_region(
    session: Session,
    region: Optional[str],
    cache: Dict[str, VernacularRegion],
) -> Optional[int]:
    """Return the id of a VernacularRegion entry, creating it if absent."""
    if not region:
        return None
    region = region.strip()
    if region in cache:
        return cache[region].id
    existing = session.exec(
        select(VernacularRegion).where(VernacularRegion.region == region)
    ).first()
    if existing:
        cache[region] = existing
        return existing.id
    obj = VernacularRegion(region=region)
    session.add(obj)
    session.flush()
    cache[region] = obj
    return obj.id


def _get_or_create_provenance_general(
    session: Session,
    description: Optional[str],
    cache: Dict[str, ProvenanceGeneral],
) -> Optional[int]:
    """Return the id of a ProvenanceGeneral entry, creating it if absent."""
    if not description:
        return None
    description = description.strip()
    if description in cache:
        return cache[description].id
    existing = session.exec(
        select(ProvenanceGeneral).where(
            ProvenanceGeneral.description == description
        )
    ).first()
    if existing:
        cache[description] = existing
        return existing.id
    obj = ProvenanceGeneral(description=description)
    session.add(obj)
    session.flush()
    cache[description] = obj
    return obj.id


def _add_manuscript_resource(
    ms: Manuscript,
    url: str,
    resource_type: str,
    comment: Optional[str],
    col_name: str,
    excel_row: int,
    session: Session,
    report: "ImportReport",
    stats: Dict[str, int],
) -> None:
    """Validate and attach a single ExternalResource to a Manuscript."""
    url = _validate_url(url, excel_row, col_name, report)
    if not url:
        stats["urls_skipped"] += 1
        return
    exists = session.exec(
        select(ExternalResource).where(
            ExternalResource.manuscript_id == ms.id,
            ExternalResource.url == url,
        )
    ).first()
    if not exists:
        try:
            rtype = ExternalResourceType(resource_type)
        except ValueError:
            rtype = ExternalResourceType.other
        session.add(
            ExternalResource(
                manuscript_id=ms.id,
                url=url,
                resource_type=rtype,
                comment=comment,
            )
        )
        stats["urls_imported"] += 1


def _cell_inspection_status(cell: Cell) -> str:
    """Derive an inspection status string from the cell fill colour."""
    try:
        fill = cell.fill
        if fill is None or fill.fgColor is None:
            return "unknown"
        color = fill.fgColor
        if color.type != "rgb":
            return "unknown"
        argb = color.rgb
        if argb in ("00000000", "FF000000", "FFFFFFFF"):
            return "unknown"
        r, g, b = int(argb[2:4], 16), int(argb[4:6], 16), int(argb[6:8], 16)
        if r < 100 and g > 150 and b < 100:
            return "direct"
        if r > 200 and 100 <= g <= 200 and b < 100:
            return "uncertain"
        if r > 200 and g < 100 and b < 100:
            return "indirect"
        return "unknown"
    except Exception:
        return "unknown"


def _chunked(iterable, n: int):
    """Yield successive n-sized chunks from *iterable*."""
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk


def row_to_cell_dict(
    row_cells_list: List[Cell], headers: List[Optional[str]]
) -> Dict[str, Cell]:
    """Map header names to their corresponding Cell objects for a data row."""
    return {h: c for h, c in zip(headers, row_cells_list) if h is not None}


def cval(row: Dict[str, Cell], col: str) -> Optional[str]:
    """Extract a cleaned string value from a named column.

    The column name is normalised (outer strip + inner whitespace collapse)
    before lookup so that trailing/leading spaces in literal strings never
    cause silent misses against the stripped headers in _read_headers.
    """
    cell = row.get(_normalize_col(col))
    return clean_value(cell.value) if cell else None


def cval_first(row: Dict[str, Cell], *cols: str) -> Optional[str]:
    """Return the first non-None cleaned value from a list of column name candidates."""
    for col in cols:
        v = cval(row, col)
        if v is not None:
            return v
    return None


def cint(row: Dict[str, Cell], col: str) -> Optional[int]:
    """Extract an integer value from a named column."""
    cell = row.get(_normalize_col(col))
    v, _ = parse_int(cell.value if cell else None)
    return v


def cfloat(row: Dict[str, Cell], col: str) -> Optional[float]:
    """Extract a float value from a named column."""
    cell = row.get(_normalize_col(col))
    return parse_float(cell.value if cell else None)


def cyesno(row: Dict[str, Cell], col: str) -> Optional[bool]:
    """Extract a boolean yes/no value from a named column."""
    cell = row.get(_normalize_col(col))
    return parse_yesno(cell.value if cell else None)


def _read_headers(ws: Worksheet) -> Tuple[List[Optional[str]], Any]:
    """Read the first row of a worksheet as column headers."""
    rows_iter = ws.rows
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], iter([])
    
    headers = []
    seen = {}
    for c in header_row:
        if c.value is not None:
            val = re.sub(r'\s+', ' ', str(c.value).strip())
            if val in seen:
                seen[val] += 1
                headers.append(f"{val}_{seen[val]}")
            else:
                seen[val] = 1
                headers.append(val)
        else:
            headers.append(None)
            
    logger.info(f"[Headers] {headers}")
    return headers, rows_iter


# ---------------------------------------------------------------------------
# ImportReport
# ---------------------------------------------------------------------------

class ImportReport:
    """Collects import anomalies and writes them to an Excel workbook."""

    CATEGORIES = [
        "url_skipped",
        "relation_inconsistency",
        "invalid_format",
        "critical_error",
        "image_warning",
    ]

    def __init__(self) -> None:
        self.categories: Dict[str, List[Dict[str, Any]]] = {
            c: [] for c in self.CATEGORIES
        }

    def add(self, category: str, data: Dict[str, Any]) -> None:
        self.categories.setdefault(category, []).append(data)

    def save(self, path: str) -> None:
        from openpyxl import Workbook as WB

        wb = WB()
        if wb.active:
            wb.remove(wb.active)
        for category in self.CATEGORIES:
            entries = self.categories.get(category, [])
            ws = wb.create_sheet(title=category.upper()[:31])
            if not entries:
                ws.append(["(no entries)"])
                continue
            headers = list(entries[0].keys())
            ws.append(headers)
            for entry in sorted(entries, key=lambda x: x.get("Row", 0)):
                ws.append([entry.get(h, "") for h in headers])
        wb.save(path)


# ---------------------------------------------------------------------------
# Step 1 — import_texts
# ---------------------------------------------------------------------------

def import_texts(session: Session, wb, report: ImportReport) -> Dict[str, "Text"]:
    """Import all rows from the 'Corpus hagio' worksheet.

    Author location and milieu data are resolved here and passed to
    _get_or_create_author, writing them on the Author row rather than Text.
    'Locally based in Origin' is stored verbatim on Text.author_locally_based;
    a starts-with-"yes" check is used only for the place_id inference.

    Returns a dict mapping BHL number → Text instance.
    """
    ws = wb["Corpus hagio"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        logger.error("Tab 'Corpus hagio' is empty.")
        return {}

    text_cache: Dict[str, Text] = {}
    place_cache: Dict[str, Place] = {}
    church_cache: Dict[str, ChurchEntity] = {}
    author_cache: Dict[str, Author] = {}
    milieu_cache: Dict[str, Milieu] = {}
    typology_cache: Dict[str, Typology] = {}
    text_type_cache: Dict[str, TextType] = {}

    inserted = skipped = 0

    for excel_row, row_cells_list in _iter_data_rows(rows_iter, "Corpus hagio"):
        row = row_to_cell_dict(row_cells_list, headers)

        # BHL number may sit in either column depending on the row format.
        bhl = cval_first(
            row,
            "BHL reference",
            "BHL reference (orange = versions with multiple Unique Identifiers "
            "or IDd redactions in one box)",
        )
        if not bhl:
            skipped += 1
            continue
        if bhl in text_cache:
            skipped += 1
            continue

        existing = session.exec(select(Text).where(Text.bhl_number == bhl)).first()
        if existing:
            text_cache[bhl] = existing
            skipped += 1
            continue

        orig_arch_id = _get_or_create_church_entity(
            session, cval(row, "Archbishopric"), "archdiocese", church_cache
        )
        orig_dio_id = _get_or_create_church_entity(
            session, cval(row, "Bishopric"), "diocese", church_cache
        )

        orig_lat = parse_float(
            row["GPS Latitude OR"].value if "GPS Latitude OR" in row else None
        )
        orig_lon = parse_float(
            row["GPS Longitude OR"].value if "GPS Longitude OR" in row else None
        )
        orig_place_id = _get_or_create_place(
            session, cval(row, "Origin"), place_cache, lat=orig_lat, lon=orig_lon
        )

        dest_lat = parse_float(
            row["GPS Latitude DES"].value if "GPS Latitude DES" in row else None
        )
        dest_lon = parse_float(
            row["GPS Longitude DES"].value if "GPS Longitude DES" in row else None
        )
        dest_place_id = _get_or_create_place(
            session,
            cval(row, "Primary destinatary"),
            place_cache,
            lat=dest_lat,
            lon=dest_lon,
        )

        # 'Locally based in Origin' is stored verbatim; a starts-with-"yes" check
        # is the only logic applied for place_id assignment on Author.
        locally_based_raw = cval(row, "Locally based in Origin (see col. O)?")
        auth_place_id = (
            orig_place_id if _locally_based_implies_place(locally_based_raw) else None
        )
        auth_edu_id = _get_or_create_place(
            session, cval(row, "Education"), place_cache
        )
        auth_ant_id = _get_or_create_place(
            session, cval(row, "Antecedents"), place_cache
        )
        milieu_id = _get_or_create_milieu(
            session, cval(row, "Milieu"), milieu_cache
        )

        auth_id = _get_or_create_author(
            session,
            cval(row, "Author"),
            author_cache,
            place_id=auth_place_id,
            education_place_id=auth_edu_id,
            earlier_place_id=auth_ant_id,
            milieu_id=milieu_id,
        )

        src_typo_id = _get_or_create_typology(
            session, cval(row, "Source type"), None, typology_cache
        )
        sub_typo_id = _get_or_create_typology(
            session, cval(row, "Subtype"), src_typo_id, typology_cache
        )
        text_type_id = _get_or_create_text_type(
            session, cval(row, "Mainly prose or verse"), text_type_cache
        )

        # 'Check  Philippart' has a double space in the actual worksheet header.
        checked_philippart = cyesno(row, _COL_CHECK_PHILIPPART_VARIANTS[0]) or cyesno(
            row, _COL_CHECK_PHILIPPART_VARIANTS[1]
        )

        text = Text(
            bhl_number=bhl,
            title=cval(row, "Title"),
            word_count=cint(row, "Approx. length in words"),
            code=cval(row, "Code"),
            checked_bhl=cyesno(row, "Check BHL"),
            checked_isb=cyesno(row, "Check Index scriptorum Belgii"),
            checked_naso=cyesno(row, "Check Narrative Sources"),
            checked_dg=cyesno(row, "Check Deutschlands Geschichtsquellen"),
            checked_philippart=checked_philippart,
            checked_secondary=cyesno(row, "Check secondaryliterature"),
            # checked_leg removed: no 'Check LEG' column exists on the Corpus hagio tab.
            is_origin_precise=cyesno(row, "Precise origin?"),
            is_destinatary_precise=cyesno(row, "Precise destinatary?"),
            author_locally_based=locally_based_raw,
            dating_rough=cval(row, "Rough chronology"),
            dating_precise=cval(row, "Dating"),
            origin_archdiocese_id=orig_arch_id,
            origin_diocese_id=orig_dio_id,
            origin_place_id=orig_place_id,
            primary_destinatary_place_id=dest_place_id,
            author_id=auth_id,
            source_type_id=src_typo_id,
            subtype_id=sub_typo_id,
            text_type_id=text_type_id,
            is_rewrite=cyesno(row, "Réécriture?"),
            rewrite_notes=cval(row, "Of which text(s)?"),   # free text, not FK
            is_based_on_pre880=cyesno(row, "Based on pre-880 text?"),
            preferred_edition=cval(row, "Edition reference"),
            edition_link_aass=cval(row, "Direct AASS link"),
            edition_link_other=cval(row, "Direct other links"),
            edition_link_mgh=cval(row, "MGH"),   # trailing space stripped by _normalize_col
            is_ocr_pre_1800=cyesno(
                row, "Definitely OCR pre-1800 + look for alternatives"
            ),
            is_ocr_post_1800=cyesno(row, "Definitely OCR post-1800"),
            full_ocr_bhl_refs=cval(row, "Full OCR/XML available?"),   # BHL refs, not bool
            is_ocr_cleaned=cyesno(row, "Cleaned?"),   # 'Unpublished' → None via parse_yesno
            ocr_comments=cval(row, "Comments on OCR/Cleaning/edition"),
            edition_link_1=cval(row, "Edition link 1 (some broken)"),
            edition_link_2=cval(row, "Edition link 2"),
            key_bibliography=cval(row, "Repertory entries and key bibliography"),
            notes=cval(row, "Notes"),
        )
        session.add(text)
        session.flush()
        text_cache[bhl] = text
        inserted += 1

    session.commit()
    logger.info(f"[Tab 3] Text: {inserted} inserted, {skipped} skipped.")
    return text_cache


# ---------------------------------------------------------------------------
# Step 2 — import_manuscripts
# ---------------------------------------------------------------------------

def import_manuscripts(
    session: Session,
    wb,
    text_cache: Dict[str, "Text"],
    report: ImportReport,
) -> Tuple[Dict[int, Manuscript], Dict[str, Manuscript]]:
    """Import all rows from the 'Manuscripts' worksheet.

    ImageAvailability is no longer stored as a lookup table.  When the
    image-availability column indicates images should exist but no URL is
    extractable, a WARNING is logged and an 'image_warning' entry is added
    to the import report.

    Returns two caches:
        ms_cache      — unique_id (int) → Manuscript
        ms_coll_cache — normalised collection_identifier (str) → Manuscript
    """
    ws = wb["Manuscripts"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        logger.error("Tab 'Manuscripts' is empty.")
        return {}, {}

    resource_cache: Dict[str, ExternalResource] = {}
    place_cache: Dict[str, Place] = {}
    inst_cache: Dict[str, Institution] = {}
    church_cache: Dict[str, ChurchEntity] = {}
    mt_cache: Dict[str, ManuscriptType] = {}
    ms_ident_cache: Dict[str, ManuscriptIdentifier] = {}
    century_cache: Dict[int, DatingCentury] = {}
    vernacular_cache: Dict[str, VernacularRegion] = {}
    prov_gen_cache: Dict[str, ProvenanceGeneral] = {}
    image_type_cache: Dict[str, ImageType] = {}

    stats: Dict[str, int] = {
        "manuscripts_inserted": 0,
        "manuscripts_skipped": 0,
        "ms_text_links_created": 0,
        "ms_text_links_skipped": 0,
        "urls_imported": 0,
        "urls_skipped": 0,
        "images_created": 0,
    }

    ms_cache: Dict[int, Manuscript] = {}
    ms_coll_cache: Dict[str, Manuscript] = {}
    for existing_ms in session.exec(select(Manuscript)).all():
        if existing_ms.unique_id is not None:
            ms_cache[existing_ms.unique_id] = existing_ms
        if existing_ms.collection_identifier:
            ms_coll_cache[normalize_id(existing_ms.collection_identifier)] = existing_ms

    relation_tasks: List[Tuple[int, int, str, str, Optional[str], str, int]] = []

    for batch in _chunked(_iter_data_rows(rows_iter, "Manuscripts"), 500):
        try:
            for excel_row, row_cells_list in batch:
                row = row_to_cell_dict(row_cells_list, headers)

                ms_number = cval(row, "MS N° per BHL number")
                col_a_cell = row_cells_list[0] if row_cells_list else None
                col_a_value = clean_value(col_a_cell.value) if col_a_cell else None

                if not col_a_value and not ms_number:
                    continue

                uid_raw, uid_ok = parse_int(
                    row["Unique ID"].value if "Unique ID" in row else None
                )
                if not uid_ok:
                    report.add(
                        "invalid_format",
                        {
                            "Row": excel_row,
                            "Column": "Unique ID",
                            "Value": row["Unique ID"].value if "Unique ID" in row else None,
                            "Reason": "Could not parse as integer",
                        },
                    )

                text_obj = text_cache.get(col_a_value) if col_a_value else None

                coll_loc_id = _get_or_create_place(
                    session, cval(row, "Location"), place_cache
                )
                heri_inst_id = _get_or_create_institution(
                    session,
                    cval(row, "Heritage institution"),
                    coll_loc_id,
                    inst_cache,
                )
                shelfmark = cval(row, "Shelfmark")
                comp_key = f"ms_{heri_inst_id}_{shelfmark}"

                ms = None
                if uid_raw is not None:
                    ms = ms_cache.get(uid_raw)
                    if not ms:
                        ms = session.exec(
                            select(Manuscript).where(Manuscript.unique_id == uid_raw)
                        ).first()
                if not ms and heri_inst_id and shelfmark:
                    ms = ms_cache.get(comp_key)
                    if not ms:
                        ms = session.exec(
                            select(Manuscript).where(
                                Manuscript.heritage_institution_id == heri_inst_id,
                                Manuscript.shelfmark == shelfmark,
                            )
                        ).first()

                if ms:
                    stats["manuscripts_skipped"] += 1
                    if ms.unique_id is not None:
                        ms_cache[ms.unique_id] = ms
                    if ms.heritage_institution_id and ms.shelfmark:
                        ms_cache[
                            f"ms_{ms.heritage_institution_id}_{ms.shelfmark}"
                        ] = ms
                else:
                    prov_arch_id = _get_or_create_church_entity(
                        session, cval(row, "Provenance archdiocese"), "archdiocese", church_cache,
                    )
                    prov_dio_id = _get_or_create_church_entity(
                        session, cval(row, "Provenance diocese"), "diocese", church_cache,
                    )
                    prov_inst_id = _get_or_create_institution(
                        session,
                        cval(row, "Provenance institution"),
                        coll_loc_id,
                        inst_cache,
                    )
                    ms_title_str = cval(row, "Title")
                    ms_ident_id = _get_or_create_ms_identifier(
                        session, ms_title_str, col_a_value, ms_ident_cache
                    )
                    century_id = _get_or_create_dating_century(
                        session,
                        row[_COL_MS_DATING_CENTURY].value
                        if _COL_MS_DATING_CENTURY in row
                        else None,
                        century_cache,
                    )
                    vernacular_id = _get_or_create_vernacular_region(
                        session, cval(row, _COL_MS_VERNACULAR), vernacular_cache
                    )
                    prov_gen_id = _get_or_create_provenance_general(
                        session, cval(row, "Provenance general"), prov_gen_cache,
                    )
                    ms_typo_id = _get_or_create_manuscript_type(
                        session, cval(row, "Manuscript type"), mt_cache
                    )

                    ms = Manuscript(
                        unique_id=uid_raw,
                        ms_identifier_id=ms_ident_id,
                        collection_identifier=cval(row, _COL_MS_COLLECTION_ID),
                        checked_leg=cyesno(row, "LEG"),
                        checked_dg=cyesno(row, "DG"),
                        checked_naso=cyesno(row, _COL_MS_NASO),
                        checked_ed_sec=cyesno(row, "ED/SEC"),
                        collection_place_id=coll_loc_id,
                        heritage_institution_id=heri_inst_id,
                        shelfmark=shelfmark,
                        dating_century_id=century_id,
                        dating_precise=cval(row, "Dating"),   # trailing space fixed by _normalize_col
                        provenance_general_id=prov_gen_id,
                        provenance_archdiocese_id=prov_arch_id,
                        provenance_diocese_id=prov_dio_id,
                        provenance_institution_id=prov_inst_id,
                        vernacular_region_id=vernacular_id,
                        notes=cval(row, "Notes"),
                        witness_relation_notes=cval(row, _COL_MS_RELATIONS),
                        manuscript_type_id=ms_typo_id,
                        dimension_width_cm=cfloat(row, "Width"),
                        dimension_height_cm=cfloat(row, "Height"),
                    )
                    session.add(ms)
                    session.flush()

                    if ms.unique_id is not None:
                        ms_cache[ms.unique_id] = ms
                    if ms.heritage_institution_id and ms.shelfmark:
                        ms_cache[comp_key] = ms
                    coll_id = cval(row, _COL_MS_COLLECTION_ID)
                    if coll_id:
                        ms_coll_cache[normalize_id(coll_id)] = ms
                    stats["manuscripts_inserted"] += 1

                # --- ManuscriptText link ---
                if text_obj is not None:
                    txt_arch_id = _get_or_create_church_entity(
                        session, cval(row, "Archbishopric"), "archdiocese", church_cache,
                    )
                    txt_bish_id = _get_or_create_church_entity(
                        session, cval(row, "Bishopric"), "diocese", church_cache,
                    )
                    txt_orig_id = _get_or_create_place(
                        session, cval(row, "Origin"), place_cache
                    )
                    existing_link = session.exec(
                        select(ManuscriptText).where(
                            ManuscriptText.ms_id == ms.id,
                            ManuscriptText.text_id == text_obj.id,
                        )
                    ).first()
                    if existing_link:
                        stats["ms_text_links_skipped"] += 1
                    else:
                        link = ManuscriptText(
                            ms_id=ms.id,
                            text_id=text_obj.id,
                            ms_number_per_bhl=ms_number,
                            folio_pages=cval(row, _COL_MS_FOLIO),
                            text_archdiocese_id=txt_arch_id,
                            text_bishopric_id=txt_bish_id,
                            text_origin_place_id=txt_orig_id,
                        )
                        session.add(link)
                        stats["ms_text_links_created"] += 1

                # --- Manuscript-to-manuscript relation tasks ---
                if uid_raw is not None:
                    certainty_val = cyesno(row, _COL_MS_EXEMPLAR_CERTAIN)
                    cert_enum = (
                        Certainty.certain if certainty_val else Certainty.uncertain
                    )
                    notes_copy = cval(row, "Notes on exemplar")
                    notes_exemplar = cval(row, "Notes on copies")

                    for col in _COPY_OF_COLS:
                        cell = row.get(col)
                        if cell and cell.value:
                            target_uid, _ = parse_int(cell.value)
                            if target_uid is not None:
                                relation_tasks.append((
                                    uid_raw, target_uid, RelationType.copy_of,
                                    cert_enum, notes_copy, col, excel_row,
                                ))
                    for col in _EXEMPLAR_OF_COLS:
                        cell = row.get(col)
                        if cell and cell.value:
                            copy_uid, _ = parse_int(cell.value)
                            if copy_uid is not None:
                                relation_tasks.append((
                                    copy_uid, uid_raw, RelationType.copy_of,
                                    Certainty.uncertain, notes_exemplar, col, excel_row,
                                ))

                # --- External resources (catalogue links) ---
                for col_name, resource_type in _MANUSCRIPT_RESOURCE_COLS:
                    cell = row.get(col_name)
                    if cell is None:
                        continue
                    url_str = _extract_hyperlink_url(cell)
                    if not url_str:
                        if cell.value:
                            stats["urls_skipped"] += 1
                        continue
                    _add_manuscript_resource(
                        ms, url_str, resource_type,
                        comment=None, col_name=col_name, excel_row=excel_row,
                        session=session, report=report, stats=stats,
                    )

                # --- Images ---
                image_avail_str = cval(row, _COL_MS_IMAGE_AVAIL)
                img_cell = row.get(_COL_MS_IMAGES)

                if img_cell is not None:
                    url_str = _extract_hyperlink_url(img_cell)
                    if url_str:
                        url_str = _validate_url(
                            url_str, excel_row, _COL_MS_IMAGES, report
                        )
                        if url_str:
                            itype_str = _infer_image_type(image_avail_str)
                            itype_id = _get_or_create_image_type(
                                session, itype_str, image_type_cache
                            )
                            exists = session.exec(
                                select(Image).where(
                                    Image.ms_id == ms.id,
                                    Image.url == url_str,
                                )
                            ).first()
                            if not exists:
                                session.add(
                                    Image(
                                        url=url_str,
                                        image_type_id=itype_id,
                                        comment=None,
                                        ms_id=ms.id,
                                    )
                                )
                                stats["images_created"] += 1
                    elif img_cell.value:
                        stats["urls_skipped"] += 1

                # Warn when availability column promises images but no URL was found.
                avail_upper = (image_avail_str or "").strip().upper()
                has_promised_image = avail_upper not in _NO_IMAGE_VALUES
                img_was_imported = (
                    img_cell is not None and _extract_hyperlink_url(img_cell) is not None
                )
                if has_promised_image and not img_was_imported:
                    logger.warning(
                        f"[Tab 1] Row {excel_row}: image availability "
                        f"'{image_avail_str}' indicated but no image URL extracted."
                    )
                    report.add(
                        "image_warning",
                        {
                            "Row": excel_row,
                            "ImageAvailability": image_avail_str,
                            "Reason": (
                                "Availability column set but no image URL found"
                            ),
                        },
                    )

            session.commit()

        except Exception as e:
            logger.error(f"[Tab 1] Batch error: {e}")
            report.add("critical_error", {"Error": str(e)})
            session.rollback()
            continue

    # --- Post-pass: resolve ManuscriptRelation tasks ---
    logger.info(
        f"[Relations] Processing {len(relation_tasks)} relation tasks..."
    )
    rel_created = rel_skipped = 0
    for src_uid, tgt_uid, rel_type, cert, notes, col, row_num in relation_tasks:
        src_ms = ms_cache.get(src_uid) or session.exec(
            select(Manuscript).where(Manuscript.unique_id == src_uid)
        ).first()
        tgt_ms = ms_cache.get(tgt_uid) or session.exec(
            select(Manuscript).where(Manuscript.unique_id == tgt_uid)
        ).first()

        if src_ms:
            ms_cache[src_uid] = src_ms
        if tgt_ms:
            ms_cache[tgt_uid] = tgt_ms

        if not src_ms or not tgt_ms:
            continue

        exists = session.exec(
            select(ManuscriptRelation).where(
                ManuscriptRelation.source_manuscript_id == src_ms.id,
                ManuscriptRelation.target_manuscript_id == tgt_ms.id,
                ManuscriptRelation.relation_type == rel_type,
            )
        ).first()
        if exists:
            rel_skipped += 1
            continue

        session.add(
            ManuscriptRelation(
                source_manuscript_id=src_ms.id,
                target_manuscript_id=tgt_ms.id,
                relation_type=rel_type,
                certainty=cert,
                notes=notes,
                source_reference=(
                    f"Excel import — Manuscripts tab "
                    f"(row {row_num}, column '{col}')"
                ),
            )
        )
        rel_created += 1

    session.commit()
    logger.info(
        f"[Tab 1] Done — {stats['manuscripts_inserted']} inserted, "
        f"{stats['ms_text_links_created']} text-links created, "
        f"{rel_created} relations created."
    )
    return ms_cache, ms_coll_cache


# ---------------------------------------------------------------------------
# Step 3 — import_editions
# ---------------------------------------------------------------------------

def import_editions(
    session: Session,
    wb,
    text_cache: Dict[str, "Text"],
    ms_cache: Dict[int, Manuscript],
    ms_coll_cache: Dict[str, Manuscript],
    report: ImportReport,
) -> None:
    """Import all rows from the 'Editions' worksheet.

    Edition.has_scan is removed — the scan URL is stored as an ExternalResource
    linked via EditionExternalResource.

    Edition.reprint_type is derived from the two former boolean columns:
      - identically=YES → ReprintType.identically_typeset
      - newly=YES       → ReprintType.newly_typeset
      - both markers = 'to be verified' → ReprintType.to_be_verified
      - both NO / missing → None (not a reprint or unclassified)
    """
    ws = wb["Editions"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        return

    resource_cache: Dict[str, ExternalResource] = {}
    edition_cache: Dict[Any, Edition] = {}
    stats: Dict[str, int] = {
        "editions_inserted": 0,
        "ms_links_created": 0,
        "urls_imported": 0,
        "urls_skipped": 0,
    }

    for batch in _chunked(_iter_data_rows(rows_iter, "Editions"), 500):
        try:
            edition_ms_pairs: set = set()

            for excel_row, row_cells_list in batch:
                row = row_to_cell_dict(row_cells_list, headers)

                bhl = cval(row, _COL_ED_BHL)
                ed_id = cval(row, _COL_ED_ID)
                if not bhl and not ed_id:
                    continue

                text_obj = text_cache.get(bhl) if bhl else None

                edition_ref_parts = [
                    clean_value(row_cells_list[idx].value)
                    for idx in _EDITION_EDITION_COL_INDICES
                    if idx < len(row_cells_list)
                    and clean_value(row_cells_list[idx].value)
                ]

                scan_cell = row.get(_COL_ED_SCAN_LINK)
                scan_url = _extract_hyperlink_url(scan_cell) if scan_cell else None

                uid_num = cint(row, _COL_ED_UID_NUM)
                uid_desc = cval(row, _COL_ED_UID_DESC)
                title = cval(row, "Title")

                cache_key = uid_num if uid_num is not None else (
                    uid_desc if uid_desc else f"{title}|{bhl}"
                )

                # Derive reprint_type from the two former boolean columns.
                raw_ident = (
                    str(row[col].value).strip().upper()
                    if (col := "If reprint, identically typeset?") in row
                    and row[col].value is not None
                    else ""
                )
                raw_newly = (
                    str(row[col2].value).strip().upper()
                    if (col2 := "If reprint, newly typeset?") in row
                    and row[col2].value is not None
                    else ""
                )
                _tbc = "TO BE VERIFIED"
                if raw_ident in (_tbc, "TO BE VERIFIED") and raw_newly in (_tbc, "TO BE VERIFIED"):
                    reprint_type_val: Optional[ReprintType] = ReprintType.to_be_verified
                elif raw_ident in ("YES", "Y"):
                    reprint_type_val = ReprintType.identically_typeset
                elif raw_newly in ("YES", "Y"):
                    reprint_type_val = ReprintType.newly_typeset
                else:
                    reprint_type_val = None

                if cache_key in edition_cache:
                    edition = edition_cache[cache_key]
                else:
                    existing = None
                    if uid_num is not None:
                        existing = session.exec(
                            select(Edition).where(
                                Edition.unique_id_numeric == uid_num
                            )
                        ).first()
                    elif uid_desc:
                        existing = session.exec(
                            select(Edition).where(
                                Edition.unique_id_descriptive == uid_desc
                            )
                        ).first()

                    if existing:
                        edition = existing
                        edition_cache[cache_key] = edition
                    else:
                        edition = Edition(
                            bhl_number=bhl,
                            title=title,
                            edition_identifier=ed_id,
                            edition_reference_per_text=cval(
                                row, "Ed. reference per individual text"
                            ),
                            checked_dg=cyesno(row, "DG"),
                            checked_naso=cyesno(row, "NASO"),
                            checked_ed_sec=cyesno(row, "ED/SEC"),
                            unique_id_numeric=uid_num,
                            unique_id_descriptive=uid_desc,
                            year_of_publication=cint(row, _COL_ED_YEAR),
                            bibliographic_reference=cval(row, _COL_ED_BIBREF),
                            page_range=cval(row, _COL_ED_PAGES),
                            is_reprint=cyesno(row, "Reprint?"),
                            reprint_type=reprint_type_val,
                            reprint_of=cval(row, _COL_ED_REPRINT_OF),
                            has_transcription=cyesno(row, _COL_ED_TRANSCRIBED),
                            is_our_transcription=cyesno(row, "Our transcribed ed.?"),
                            is_collated=cyesno(row, _COL_ED_COLLATED),
                            edition_refs=", ".join(edition_ref_parts) or None,
                            notes=cval(row, "Notes"),
                            text_id=text_obj.id if text_obj else None,
                        )
                        session.add(edition)
                        session.flush()
                        edition_cache[cache_key] = edition
                        stats["editions_inserted"] += 1

                if scan_url:
                    scan_url = _validate_url(
                        scan_url, excel_row, _COL_ED_SCAN_LINK, report
                    )
                    if scan_url:
                        resource = _get_or_create_resource(
                            scan_url, "scan",
                            comment=None,
                            cache=resource_cache,
                            session=session,
                        )
                        exists = session.exec(
                            select(EditionExternalResource).where(
                                EditionExternalResource.edition_id == edition.id,
                                EditionExternalResource.resource_id == resource.id,
                            )
                        ).first()
                        if not exists:
                            session.add(
                                EditionExternalResource(
                                    edition_id=edition.id,
                                    resource_id=resource.id,
                                )
                            )
                            stats["urls_imported"] += 1
                elif scan_cell and scan_cell.value:
                    stats["urls_skipped"] += 1

                for idx in _EDITION_MS_COL_INDICES:
                    if idx >= len(row_cells_list):
                        continue
                    ms_cell = row_cells_list[idx]
                    ms_val = str(ms_cell.value).strip() if ms_cell.value else ""
                    if not ms_val or ms_val.upper() == "N/A":
                        continue

                    match_val = normalize_id(ms_val)
                    target_ms = ms_coll_cache.get(match_val)

                    if target_ms is None:
                        report.add(
                            "invalid_format",
                            {
                                "Row": excel_row,
                                "Column": f"col index {idx} (W-AL)",
                                "Value": ms_val,
                                "Reason": (
                                    f"Collection identifier '{match_val}' not found"
                                ),
                            },
                        )
                        continue

                    pair_key = (edition.id, target_ms.id)
                    if pair_key not in edition_ms_pairs:
                        inspection = (
                            "uncertain"
                            if "(?)" in ms_val
                            else _cell_inspection_status(ms_cell)
                        )
                        exists = session.exec(
                            select(EditionManuscript).where(
                                EditionManuscript.edition_id == edition.id,
                                EditionManuscript.ms_id == target_ms.id,
                            )
                        ).first()
                        if not exists:
                            session.add(
                                EditionManuscript(
                                    edition_id=edition.id,
                                    ms_id=target_ms.id,
                                    inspection_status=inspection,
                                )
                            )
                            edition_ms_pairs.add(pair_key)
                            stats["ms_links_created"] += 1

            session.commit()

        except Exception as e:
            logger.error(f"[Tab 2] Batch error: {e}")
            report.add("critical_error", {"Error": str(e)})
            session.rollback()
            continue

    logger.info(
        f"[Tab 2] Done — {stats['editions_inserted']} editions inserted, "
        f"{stats['ms_links_created']} manuscript links created."
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Excel → SQLite import pipeline."""
    logger.info(f"Using database at {DB_PATH}")
    if not EXCEL.exists():
        logger.error(
            f"Excel file not found at {EXCEL}, cannot proceed with import."
        )
        return

    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    wb = load_workbook(EXCEL, data_only=True)
    report = ImportReport()

    with Session(engine) as session:
        logger.info("=== Step 1: Importing Text ===")
        text_cache = import_texts(session, wb, report)

        logger.info("=== Step 2: Importing Manuscripts ===")
        ms_cache, ms_coll_cache = import_manuscripts(
            session, wb, text_cache, report
        )

        logger.info("=== Step 3: Importing Editions ===")
        import_editions(
            session, wb, text_cache, ms_cache, ms_coll_cache, report
        )

    report.save(str(DATA_ROOT / "import_report.xlsx"))


if __name__ == "__main__":
    main()