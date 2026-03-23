# cli_hagio.py
# ---------------------------------------------------------------------------
# Import hagiographies.xlsx into the SQLite database.
#
# Worksheet layout:
#   Tab 1  "Manuscripts"  -> Manuscript + Image + ExternalResource
#   Tab 2  "Editions"     -> Edition + EditionManuscript + ExternalResource
#   Tab 3  "Corpus hagio" -> Text
#
# Key differences:
#   - load_workbook() without read_only=True  -> cell.hyperlink.target accessible
#   - row_to_cell_dict() stores Cell objects  -> .value AND .hyperlink available
#   - _extract_hyperlink() returns (url, display_text); URL always wins over
#     display text ("Link", "CHECK", etc. are silently discarded)
#   - _iter_data_rows() skips empty rows and stops after EMPTY_ROW_LIMIT
#     consecutive empty rows — avoids crawling thousands of blank Excel rows
#
# Column names below are the ACTUAL headers found in hagiographies.xlsx.
# ---------------------------------------------------------------------------

import logging
import re
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
    Text,
    Manuscript,
    Image,
    ExternalResource,
    ManuscriptExternalResource,
    EditionExternalResource,
    ManuscriptRelation,
    Edition,
    EditionManuscript,
    Place,
    Institution,
    Author,
    Typology,
    ManuscriptType,
    Milieu,
    ChurchEntity,
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


def normalize_id(val: Any) -> str:
    """Lowercase + strip + normalize internal spaces."""
    if not val:
        return ""
    s = str(val).strip().lower()
    if "(" in s:
        s = s.split("(")[0].strip()
    return re.sub(r"\s+", " ", s)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMPTY_ROW_LIMIT = 10

# Cols W-AL (0-based indices 22-37): manuscript Unique ID cross-references
_EDITION_MS_COL_INDICES = list(range(22, 38))

# Cols AM-AQ (0-based indices 38-42): edition cross-references (raw text)
_EDITION_EDITION_COL_INDICES = list(range(38, 43))

# ---------------------------------------------------------------------------
# ACTUAL column names from hagiographies.xlsx (verified from import log)
# ---------------------------------------------------------------------------

# Tab 1 — Manuscripts
_COL_MS_NASO              = "NASO"
_COL_MS_FOLIO             = "Folio or page per BHL"
_COL_MS_DATING_CENTURY    = "Dating by (earliest) century"
_COL_MS_VERNACULAR        = "Vernacular region (Romance/Germanic)"
_COL_MS_COLLECTION_ID     = "Unique  identifier per collection"   # double space!
_COL_MS_CATALOGUE         = "Online catalogue link"
_COL_MS_BOLLANDIST        = "Bollandist catalogue link"
_COL_MS_OTHER_CATALOGUE   = "Other relevant catalogue link"
_COL_MS_IMAGE_AVAIL       = "IIIF, scan, or no images"
_COL_MS_IMAGES            = "Link to images"
_COL_MS_RELATIONS         = "Relation to other manuscript witnesses?"
_COL_MS_EXEMPLAR_CERTAIN  = " Certain?" # Leading space as per user note

# Tab 1 — resource columns: (header_name, resource_type)
_MANUSCRIPT_RESOURCE_COLS: List[Tuple[str, str]] = [
    (_COL_MS_CATALOGUE,       "catalog_link"),
    (_COL_MS_BOLLANDIST,      "bollandist_catalog"),
    (_COL_MS_OTHER_CATALOGUE, "catalog_link"),
]

# Tab 1 — relation columns (verify exact names against Excel)
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

# Tab 2 — Editions
_COL_ED_BHL               = "BHL"
_COL_ED_ID                = "Ed. reference per individual text"
_COL_ED_UID_NUM           = "Unique ED ID"
_COL_ED_UID_DESC          = "Unique identifier per edition + volume"
_COL_ED_YEAR              = "Date"
_COL_ED_BIBREF            = "Edition reference"
_COL_ED_PAGES             = "Pages"
_COL_ED_REPRINT_OF        = "If reprint, of what?"
_COL_ED_SCAN_LINK         = "Online scan link"
_COL_ED_TRANSCRIBED       = "Transcribed?"
_COL_ED_COLLATED          = "Collation done?"

# Tab 3 — Corpus hagio
_COL_TEXT_BHL             = "BHL reference"      # col I — the clean BHL number
_COL_TEXT_WORDS           = "Approx. length in words"
_COL_TEXT_DATING_QC       = "Rough chronology"
_COL_TEXT_DATING_ROUGH    = "Rough chronology"
_COL_TEXT_LAT_OR          = "GPS Latitude OR"
_COL_TEXT_LON_OR          = "GPS Longitude OR"
_COL_TEXT_ORIGIN_KNOWN    = "Precise origin?"
_COL_TEXT_LAT_DES         = "GPS Latitude DES"
_COL_TEXT_LON_DES         = "GPS Longitude DES"
_COL_TEXT_DES_KNOWN       = "Precise destinatary?"
_COL_TEXT_AUTHOR_LOC      = "Locally based in Origin (see col. O)?"
_COL_TEXT_EDUCATION       = "Education"
_COL_TEXT_ANTECEDENTS     = "Antecedents"
_COL_TEXT_PROSE_VERSE     = "Mainly prose or verse"
_COL_TEXT_REECR_OF        = "Of which text(s)?"
_COL_TEXT_PREF_ED         = "Edition reference"
_COL_TEXT_OCR             = "Full OCR/XML available?"
_COL_TEXT_OCR_CLEANED     = "Cleaned?"
_COL_TEXT_OCR_COMMENTS    = "Comments on OCR/Cleaning/edition"
_COL_TEXT_BIBLIOGRAPHY    = "Repertory entries and key bibliography"

# ---------------------------------------------------------------------------
# Pure value helpers
# ---------------------------------------------------------------------------

def clean_value(val: Any) -> Optional[str]:
    if val is None or val == "" or str(val).lower() == "nan":
        return None
    s = str(val).strip()
    return s if s else None


def parse_int(val: Any) -> Tuple[Optional[int], bool]:
    if val is None:
        return None, True
    try:
        return int(val), True
    except (ValueError, TypeError):
        return None, False


def parse_float(val: Any) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def parse_yesno(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip().upper()
    if s in ("Y", "YES", "1", "TRUE", "OUI", "JA"):
        return 1
    if s in ("N", "NO", "0", "FALSE", "NON", "NEE"):
        return 0
    return None


# ---------------------------------------------------------------------------
# Empty-row detection & smart iteration
# ---------------------------------------------------------------------------

def _is_empty_row(row_cells_list: List[Cell]) -> bool:
    return all(
        c.value is None or str(c.value).strip() == ""
        for c in row_cells_list
    )


def _iter_data_rows(
    rows_iter,
    sheet_title: str = "",
    empty_limit: int = EMPTY_ROW_LIMIT,
) -> Generator[Tuple[int, List[Cell]], None, None]:
    """
    Yields (excel_row_number, row_cells_list) for every non-empty data row.
    Stops after `empty_limit` consecutive empty rows.
    Caller must have already consumed the header row from rows_iter.
    """
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
        # logger.info(f"[{sheet_title}] Row {row_num}: {[c.value for c in row_cells_list if c.value]}")
        yield row_num, row_cells_list


# ---------------------------------------------------------------------------
# Hyperlink extraction
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def _extract_hyperlink(cell: Cell) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (url_or_None, display_text_or_None).
    Priority: cell.hyperlink.target > cell.value if URL-shaped > None.
    Requires workbook opened WITHOUT read_only=True.
    """
    display = clean_value(cell.value)
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target.strip(), display
    if display and _URL_RE.match(display):
        return display, None
    return None, display


def _validate_url(
    url: str,
    excel_row: int,
    col_name: str,
    report: "ImportReport",
) -> Optional[str]:
    if not _URL_RE.match(url):
        report.add("url_skipped", {
            "Row": excel_row,
            "Column": col_name,
            "URL": url,
            "Reason": "Malformed URL",
        })
        return None
    return url


# ---------------------------------------------------------------------------
# Image type inference
# ---------------------------------------------------------------------------

_IMAGE_TYPE_MAP = [
    ("IIIF MF", "iiif_mf"),
    ("IIIF",    "iiif"),
    ("SCAN",    "scan"),
    ("IPHONE",  "iphone_photo"),
]


def _infer_image_type(image_availability: Optional[str]) -> str:
    aa = (image_availability or "").upper()
    for marker, itype in _IMAGE_TYPE_MAP:
        if marker in aa:
            return itype
    return "scan"


# ---------------------------------------------------------------------------
# ExternalResource upsert
# ---------------------------------------------------------------------------

def _get_or_create_resource(
    url: str,
    resource_type: str,
    comment: Optional[str],
    cache: Dict[str, ExternalResource],
    session: Session,
) -> ExternalResource:
    if url in cache:
        return cache[url]
    existing = session.exec(
        select(ExternalResource).where(ExternalResource.url == url)
    ).first()
    if existing:
        cache[url] = existing
        return existing
    resource = ExternalResource(url=url, resource_type=resource_type, comment=comment)
    session.add(resource)
    session.flush()
    cache[url] = resource
    return resource


# ---------------------------------------------------------------------------
# Cached get_or_create helpers for normalized tables
# ---------------------------------------------------------------------------

def _get_or_create_place(session: Session, name: Optional[str], cache: Dict[str, Place], lat=None, lon=None) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(Place).where(Place.name == name)).first()
    if existing:
        if lat and not existing.lat: existing.lat = lat
        if lon and not existing.lon: existing.lon = lon
        cache[name] = existing
        return existing.id
    place = Place(name=name, lat=lat, lon=lon)
    session.add(place)
    session.flush()
    cache[name] = place
    return place.id


def _get_or_create_institution(session: Session, name: Optional[str], place_id: Optional[int], cache: Dict[str, Institution]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(Institution).where(Institution.name == name)).first()
    if existing:
        if place_id and not existing.place_id: existing.place_id = place_id
        cache[name] = existing
        return existing.id
    inst = Institution(name=name, place_id=place_id)
    session.add(inst)
    session.flush()
    cache[name] = inst
    return inst.id


def _get_or_create_author(session: Session, name: Optional[str], cache: Dict[str, Author]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(Author).where(Author.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    auth = Author(name=name)
    session.add(auth)
    session.flush()
    cache[name] = auth
    return auth.id


def _get_or_create_typology(session: Session, name: Optional[str], parent_id: Optional[int], cache: Dict[str, Typology]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(Typology).where(Typology.name == name)).first()
    if existing:
        if parent_id and not existing.parent_id: existing.parent_id = parent_id
        cache[name] = existing
        return existing.id
    typo = Typology(name=name, parent_id=parent_id)
    session.add(typo)
    session.flush()
    cache[name] = typo
    return typo.id


def _get_or_create_manuscript_type(session: Session, name: Optional[str], cache: Dict[str, ManuscriptType]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(ManuscriptType).where(ManuscriptType.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    mt = ManuscriptType(name=name)
    session.add(mt)
    session.flush()
    cache[name] = mt
    return mt.id


def _get_or_create_milieu(session: Session, name: Optional[str], cache: Dict[str, Milieu]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(Milieu).where(Milieu.name == name)).first()
    if existing:
        cache[name] = existing
        return existing.id
    m = Milieu(name=name)
    session.add(m)
    session.flush()
    cache[name] = m
    return m.id


def _get_or_create_church_entity(session: Session, name: Optional[str], is_arch: bool, cache: Dict[str, ChurchEntity]) -> Optional[int]:
    if not name: return None
    name = name.strip()
    if name in cache: return cache[name].id
    existing = session.exec(select(ChurchEntity).where(ChurchEntity.name == name)).first()
    if existing:
        if is_arch: existing.is_archdiocese = 1
        cache[name] = existing
        return existing.id
    ce = ChurchEntity(name=name, is_archdiocese=1 if is_arch else 0)
    session.add(ce)
    session.flush()
    cache[name] = ce
    return ce.id


def _add_manuscript_resource(
    ms: Manuscript,
    url: str,
    resource_type: str,
    comment: Optional[str],
    col_name: str,
    excel_row: int,
    cache: Dict[str, ExternalResource],
    session: Session,
    report: "ImportReport",
    stats: Dict[str, int],
) -> None:
    url = _validate_url(url, excel_row, col_name, report)
    if not url:
        stats["urls_skipped"] += 1
        return
    resource = _get_or_create_resource(url, resource_type, comment, cache, session)
    exists = session.exec(
        select(ManuscriptExternalResource).where(
            ManuscriptExternalResource.manuscript_id == ms.id,
            ManuscriptExternalResource.resource_id == resource.id,
        )
    ).first()
    if not exists:
        session.add(ManuscriptExternalResource(
            manuscript_id=ms.id,
            resource_id=resource.id,
        ))
    stats["urls_imported"] += 1


# ---------------------------------------------------------------------------
# Cell colour -> inspection_status  (Tab 2, cols W-AL)
# ---------------------------------------------------------------------------

def _cell_inspection_status(cell: Cell) -> str:
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
        r = int(argb[2:4], 16)
        g = int(argb[4:6], 16)
        b = int(argb[6:8], 16)
        if r < 100 and g > 150 and b < 100:
            return "direct"
        if r > 200 and 100 <= g <= 200 and b < 100:
            return "uncertain"
        if r > 200 and g < 100 and b < 100:
            return "indirect"
        return "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Batch chunking
# ---------------------------------------------------------------------------

def _chunked(iterable, n: int):
    it = iter(iterable)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk


# ---------------------------------------------------------------------------
# Row -> cell dict & typed accessors
# ---------------------------------------------------------------------------

def row_to_cell_dict(
    row_cells_list: List[Cell],
    headers: List[Optional[str]],
) -> Dict[str, Cell]:
    """Maps header name -> Cell object. None-header columns are skipped."""
    return {h: c for h, c in zip(headers, row_cells_list) if h is not None}


def cval(row: Dict[str, Cell], col: str) -> Optional[str]:
    cell = row.get(col)
    return clean_value(cell.value) if cell else None


def cint(row: Dict[str, Cell], col: str) -> Optional[int]:
    cell = row.get(col)
    v, _ = parse_int(cell.value if cell else None)
    return v


def cfloat(row: Dict[str, Cell], col: str) -> Optional[float]:
    cell = row.get(col)
    return parse_float(cell.value if cell else None)


def cyesno(row: Dict[str, Cell], col: str) -> Optional[int]:
    cell = row.get(col)
    return parse_yesno(cell.value if cell else None)


def _read_headers(ws: Worksheet) -> Tuple[List[Optional[str]], Any]:
    """Reads header row, returns (headers, rows_iterator past header)."""
    rows_iter = ws.rows
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], iter([])
    headers = [
        str(c.value).strip() if c.value is not None else None
        for c in header_row
    ]
    logger.info(f"[Headers] {headers}")
    return headers, rows_iter


# ---------------------------------------------------------------------------
# Import report
# ---------------------------------------------------------------------------

class ImportReport:
    CATEGORIES = [
        "url_skipped",
        "relation_inconsistency",
        "invalid_format",
        "critical_error",
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
# Tab 3 — HagiText import
# ---------------------------------------------------------------------------

def import_texts(session: Session, wb, report: ImportReport) -> Dict[str, Text]:
    """
    Imports Tab 3 "Corpus hagio" into Text.
    """
    ws = wb["Corpus hagio"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        logger.error("Tab 'Corpus hagio' is empty.")
        return {}
    logger.info(f"[Tab 3] Headers: {[h for h in headers if h]}")

    text_cache: Dict[str, Text] = {}
    
    # Normalization caches
    place_cache: Dict[str, Place] = {}
    church_cache: Dict[str, ChurchEntity] = {}
    author_cache: Dict[str, Author] = {}
    milieu_cache: Dict[str, Milieu] = {}
    typology_cache: Dict[str, Typology] = {}
    
    inserted = skipped = 0

    for excel_row, row_cells_list in _iter_data_rows(rows_iter, "Corpus hagio"):
        row = row_to_cell_dict(row_cells_list, headers)

        bhl = cval(row, "BHL reference") # Fixed header
        if not bhl:
            # Try Col 1 (BHL reference with extra info)
            bhl = cval(row, "BHL reference (orange = versions with multiple Unique Identifiers or IDd redactions in one box)")
        
        if not bhl:
            skipped += 1
            continue
            
        if bhl in text_cache:
            skipped += 1
            continue

        existing = session.exec(
            select(Text).where(Text.bhl_number == bhl)
        ).first()
        if existing:
            text_cache[bhl] = existing
            skipped += 1
            continue

        # Normalization
        orig_arch_id = _get_or_create_church_entity(session, cval(row, "Archbishopric"), True, church_cache)
        orig_dio_id = _get_or_create_church_entity(session, cval(row, "Bishopric"), False, church_cache)
        
        orig_lat = cfloat(row, "GPS Latitude OR")
        orig_lon = cfloat(row, "GPS Longitude OR")
        orig_loc_id = _get_or_create_place(session, cval(row, "Origin"), place_cache, lat=orig_lat, lon=orig_lon)
        
        dest_lat = cfloat(row, "GPS Latitude DES")
        dest_lon = cfloat(row, "GPS Longitude DES")
        dest_loc_id = _get_or_create_place(session, cval(row, "Primary destinatary"), place_cache, lat=dest_lat, lon=dest_lon)
        
        auth_id = _get_or_create_author(session, cval(row, "Author"), author_cache)
        auth_loc_id = _get_or_create_place(session, cval(row, "Locally based in Origin (see col. O)?"), place_cache)
        auth_edu_id = _get_or_create_place(session, cval(row, "Education"), place_cache)
        auth_ant_id = _get_or_create_place(session, cval(row, "Antecedents"), place_cache)
        
        milieu_id = _get_or_create_milieu(session, cval(row, "Milieu"), milieu_cache)
        
        src_typo_id = _get_or_create_typology(session, cval(row, "Source type"), None, typology_cache)
        sub_typo_id = _get_or_create_typology(session, cval(row, "Subtype"), src_typo_id, typology_cache)

        text = Text(
            bhl_number=bhl,
            title=cval(row, "Title"),
            word_count=cint(row, "Approx. length in words"),
            code=cval(row, "Code"),
            
            checked_bhl=cyesno(row, "Check BHL"),
            checked_isb=cyesno(row, "Check Index scriptorum Belgii"),
            checked_naso=cyesno(row, "Check Narrative Sources"),
            checked_dg=cyesno(row, "Check Deutschlands Geschichtsquellen"),
            checked_philippart=cyesno(row, "Check  Philippart"),
            checked_secondary=cyesno(row, "Check secondaryliterature"),
            checked_leg=cyesno(row, "Check Narrative Sources"), # Using Narrative Sources for LEG as per header list

            origin_precise=cyesno(row, "Precise origin?"),
            destinatary_precise=cyesno(row, "Precise destinatary?"),
            author_locally_based=cyesno(row, "Locally based in Origin (see col. O)?"),
            
            dating_quarter_century=cval(row, "Rough chronology"),
            dating_rough=cval(row, "Rough chronology"),
            dating_precise=cval(row, "Dating"),
            
            origin_archdiocese_id=orig_arch_id,
            origin_diocese_id=orig_dio_id,
            origin_location_id=orig_loc_id,
            origin_known=cyesno(row, "Precise origin?"),
            
            primary_destinatary_location_id=dest_loc_id,
            destinatary_known=cyesno(row, "Precise destinatary?"),
            
            author_id=auth_id,
            author_location_id=auth_loc_id,
            author_education_location_id=auth_edu_id,
            author_earlier_location_id=auth_ant_id,
            author_milieu_id=milieu_id,
            
            source_type_id=src_typo_id,
            subtype_id=sub_typo_id,
            prose_or_verse=cval(row, "Mainly prose or verse"),
            
            reecriture=cyesno(row, "Réécriture?"),
            reecriture_of=cval(row, "Of which text(s)?"),
            based_on_pre880=cyesno(row, "Based on pre-880 text?"),
            
            preferred_edition=cval(row, "Edition reference"),
            edition_link_aass=cval(row, "Direct AASS link"),
            edition_link_other=cval(row, "Direct other links"),
            edition_link_mgh=cval(row, "MGH"),
            
            ocr_pre_1800=cyesno(row, "Definitely OCR pre-1800 + look for alternatives"),
            ocr_post_1800=cyesno(row, "Definitely OCR post-1800"),
            
            has_full_ocr=cyesno(row, "Full OCR/XML available?"),
            ocr_cleaned=cyesno(row, "Cleaned?"),
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
# Tab 1 — Manuscript import
# ---------------------------------------------------------------------------

def import_manuscripts(
    session: Session,
    wb,
    text_cache: Dict[str, "Text"],
    report: ImportReport,
) -> Tuple[Dict[int, Manuscript], Dict[str, Manuscript]]:
    """
    Imports Tab 1 "Manuscripts".

    Returns ({unique_id: Manuscript}, {collection_id_lower: Manuscript}).
    """
    ws = wb["Manuscripts"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        logger.error("Tab 'Manuscripts' is empty.")
        return {}
    logger.info(f"[Tab 1] Headers: {[h for h in headers if h]}")

    resource_cache: Dict[str, ExternalResource] = {}
    # Normalization caches
    place_cache: Dict[str, Place] = {}
    inst_cache: Dict[str, Institution] = {}
    church_cache: Dict[str, ChurchEntity] = {}
    mt_cache: Dict[str, ManuscriptType] = {}

    stats: Dict[str, int] = {
        "manuscripts_inserted": 0,
        "manuscripts_skipped": 0,
        "urls_imported": 0,
        "urls_skipped": 0,
        "images_created": 0,
    }

    ms_cache: Dict[int, Manuscript] = {}
    ms_coll_cache: Dict[str, Manuscript] = {}
    for existing in session.exec(select(Manuscript)).all():
        if existing.unique_id is not None:
            ms_cache[existing.unique_id] = existing
        if existing.collection_identifier:
            ms_coll_cache[normalize_id(existing.collection_identifier)] = existing

    # We will collect relations to create at the end, after all batches are processed
    # structure: list of (source_uid, target_uid, relation_type, certainty, notes, source_col, excel_row)
    relation_tasks: List[Tuple[int, int, str, str, str, str, int]] = []

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
                    report.add("invalid_format", {
                        "Row": excel_row,
                        "Column": "Unique ID",
                        "Value": row["Unique ID"].value if "Unique ID" in row else None,
                        "Reason": "Could not parse as integer",
                    })

                # Resolve Text: try BHL key (Col A)
                text_obj = text_cache.get(col_a_value)

                if uid_raw is not None and uid_raw in ms_cache:
                    ms = ms_cache[uid_raw]
                    stats["manuscripts_skipped"] += 1
                    if text_obj and ms.text_id is None:
                        ms.text_id = text_obj.id
                        session.add(ms)
                else:
                    txt_arch_id = _get_or_create_church_entity(session, cval(row, "Archbishopric"), True, church_cache)
                    txt_bish_id = _get_or_create_church_entity(session, cval(row, "Bishopric"), False, church_cache)
                    txt_orig_id = _get_or_create_place(session, cval(row, "Origin"), place_cache)
                    
                    coll_loc_id = _get_or_create_place(session, cval(row, "Location"), place_cache)
                    heri_inst_id = _get_or_create_institution(session, cval(row, "Heritage institution"), coll_loc_id, inst_cache)
                    
                    prov_arch_id = _get_or_create_church_entity(session, cval(row, "Provenance archdiocese"), True, church_cache)
                    prov_dio_id = _get_or_create_church_entity(session, cval(row, "Provenance diocese"), False, church_cache)
                    prov_inst_id = _get_or_create_institution(session, cval(row, "Provenance institution"), None, inst_cache)
                    
                    ms_typo_id = _get_or_create_manuscript_type(session, cval(row, "Manuscript type"), mt_cache)

                    ms = Manuscript(
                        ms_number_per_bhl=ms_number,
                        unique_id=uid_raw,
                        bhl_number=col_a_value,
                        title=cval(row, "Title"),
                        collection_identifier=cval(row, _COL_MS_COLLECTION_ID),
                        text_archdiocese_id=txt_arch_id,
                        text_bishopric_id=txt_bish_id,
                        text_origin_id=txt_orig_id,
                        checked_leg=cyesno(row, "LEG"),
                        checked_dg=cyesno(row, "DG"),
                        checked_naso=cyesno(row, _COL_MS_NASO),
                        checked_ed_sec=cyesno(row, "ED/SEC"),
                        collection_location_id=coll_loc_id,
                        heritage_institution_id=heri_inst_id,
                        shelfmark=cval(row, "Shelfmark"),
                        folio_pages=cval(row, _COL_MS_FOLIO),
                        dating_century=cint(row, _COL_MS_DATING_CENTURY),
                        dating_precise=cval(row, "Dating"),
                        provenance_general=cval(row, "Provenance general"),
                        provenance_archdiocese_id=prov_arch_id,
                        provenance_diocese_id=prov_dio_id,
                        provenance_institution_id=prov_inst_id,
                        vernacular_region=cval(row, _COL_MS_VERNACULAR),
                        image_availability=cval(row, _COL_MS_IMAGE_AVAIL),
                        notes=cval(row, "Notes"),
                        witness_relation_notes=cval(row, _COL_MS_RELATIONS),
                        manuscript_type_id=ms_typo_id,
                        dimension_width_cm=cfloat(row, "Width"),
                        dimension_height_cm=cfloat(row, "Height"),
                        text_id=text_obj.id if text_obj else None,
                    )
                    session.add(ms)
                    session.flush()
                    if uid_raw is not None:
                        ms_cache[uid_raw] = ms
                    coll_id = cval(row, _COL_MS_COLLECTION_ID)
                    if coll_id:
                        ms_coll_cache[normalize_id(coll_id)] = ms
                    stats["manuscripts_inserted"] += 1

                # --- Relation extraction logic (One Pass!) ---
                if uid_raw is not None:
                    certainty_val = cyesno(row, _COL_MS_EXEMPLAR_CERTAIN)
                    certainty = "certain" if certainty_val == 1 else "uncertain"
                    notes_copy = cval(row, "Notes on exemplar")
                    notes_exemplar = cval(row, "Notes on copies")

                    for col in _COPY_OF_COLS:
                        cell = row.get(col)
                        if cell and cell.value:
                            target_uid, _ = parse_int(cell.value)
                            if target_uid is not None:
                                relation_tasks.append((uid_raw, target_uid, "copy_of", certainty, notes_copy, col, excel_row))

                    for col in _EXEMPLAR_OF_COLS:
                        cell = row.get(col)
                        if cell and cell.value:
                            copy_uid, _ = parse_int(cell.value)
                            if copy_uid is not None:
                                # Reversed: copy_uid is the COPY OF uid_raw (the exemplar)
                                relation_tasks.append((copy_uid, uid_raw, "copy_of", "uncertain", notes_exemplar, col, excel_row))

                # --- ExternalResource links ---
                for col_name, resource_type in _MANUSCRIPT_RESOURCE_COLS:
                    cell = row.get(col_name)
                    if cell is None: continue
                    url, comment = _extract_hyperlink(cell)
                    if not url:
                        if cell.value: stats["urls_skipped"] += 1
                        continue
                    _add_manuscript_resource(ms, url, resource_type, comment, col_name, excel_row, resource_cache, session, report, stats)

                # --- Image link ---
                img_cell = row.get(_COL_MS_IMAGES)
                if img_cell is not None:
                    url, comment = _extract_hyperlink(img_cell)
                    if url:
                        url = _validate_url(url, excel_row, _COL_MS_IMAGES, report)
                    if url:
                        itype = _infer_image_type(cval(row, _COL_MS_IMAGE_AVAIL))
                        exists = session.exec(select(Image).where(Image.manuscript_id == ms.id, Image.url == url)).first()
                        if not exists:
                            session.add(Image(url=url, image_type=itype, comment=comment, manuscript_id=ms.id))
                            stats["images_created"] += 1
                    elif img_cell.value:
                        stats["urls_skipped"] += 1

            session.commit()
        except Exception as e:
            logger.error(f"[Tab 1] Batch error: {e}")
            report.add("critical_error", {"Error": str(e)})
            session.rollback()
            continue

    # --- Now process all relations ---
    logger.info(f"[Relations] Processing {len(relation_tasks)} relation tasks...")
    rel_created = rel_skipped = 0
    for src_uid, tgt_uid, rel_type, cert, notes, col, row_num in relation_tasks:
        src_ms = ms_cache.get(src_uid)
        tgt_ms = ms_cache.get(tgt_uid)
        
        # If not in cache, try DB lookup
        if not src_ms:
            src_ms = session.exec(select(Manuscript).where(Manuscript.unique_id == src_uid)).first()
            if src_ms: ms_cache[src_uid] = src_ms
        if not tgt_ms:
            tgt_ms = session.exec(select(Manuscript).where(Manuscript.unique_id == tgt_uid)).first()
            if tgt_ms: ms_cache[tgt_uid] = tgt_ms
            
        if not src_ms or not tgt_ms:
            continue
            
        exists = session.exec(select(ManuscriptRelation).where(
            ManuscriptRelation.source_manuscript_id == src_ms.id,
            ManuscriptRelation.target_manuscript_id == tgt_ms.id,
            ManuscriptRelation.relation_type == rel_type,
        )).first()
        if exists:
            rel_skipped += 1
            continue
            
        session.add(ManuscriptRelation(
            source_manuscript_id=src_ms.id,
            target_manuscript_id=tgt_ms.id,
            relation_type=rel_type,
            certainty=cert,
            notes=notes,
            source_reference=f"Excel import — Manuscripts tab (row {row_num}, column '{col}')",
        ))
        rel_created += 1

    session.commit()
    logger.info(f"[Relations] {rel_created} created, {rel_skipped} skipped.")

    logger.info(
        f"[Tab 1] Done — "
        f"{stats['manuscripts_inserted']} inserted, "
        f"{stats['manuscripts_skipped']} skipped, "
        f"{rel_created} relations created, "
        f"{stats['urls_imported']} URLs imported, "
        f"{stats['images_created']} images created."
    )
    return ms_cache, ms_coll_cache


# ---------------------------------------------------------------------------
# Tab 2 — Edition import
# ---------------------------------------------------------------------------

def import_editions(
    session: Session,
    wb,
    text_cache: Dict[str, "Text"],
    ms_cache: Dict[int, Manuscript],
    ms_coll_cache: Dict[str, Manuscript],
    report: ImportReport,
) -> None:
    """Imports Tab 2 'Editions' + EditionManuscript join rows."""
    ws = wb["Editions"]
    headers, rows_iter = _read_headers(ws)
    if not headers:
        logger.error("Tab 'Editions' is empty.")
        return
    logger.info(f"[Tab 2] Headers: {[h for h in headers if h]}")

    resource_cache: Dict[str, ExternalResource] = {}
    stats: Dict[str, int] = {
        "editions_inserted": 0,
        "ms_links_created": 0,
        "urls_imported": 0,
        "urls_skipped": 0,
    }

    for batch in _chunked(_iter_data_rows(rows_iter, "Editions"), 500):
        try:
            for excel_row, row_cells_list in batch:
                row = row_to_cell_dict(row_cells_list, headers)

                bhl   = cval(row, _COL_ED_BHL)
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

                # Derive has_scan from whether the scan link cell has content
                scan_cell = row.get(_COL_ED_SCAN_LINK)
                scan_url, scan_comment = _extract_hyperlink(scan_cell) if scan_cell else (None, None)
                has_scan = 1 if scan_url else 0

                edition = Edition(
                    bhl_number=bhl,
                    title=cval(row, "Title"),
                    edition_identifier=ed_id,
                    edition_reference_per_text=cval(row, "Ed. reference per individual text"),
                    checked_leg=None,                                # no LEG col in Tab 2
                    checked_dg=cyesno(row, "DG"),
                    checked_naso=cyesno(row, "NASO"),
                    checked_ed_sec=cyesno(row, "ED/SEC"),
                    unique_id_numeric=cint(row, _COL_ED_UID_NUM),
                    unique_id_descriptive=cval(row, _COL_ED_UID_DESC),
                    year_of_publication=cint(row, _COL_ED_YEAR),
                    bibliographic_reference=cval(row, _COL_ED_BIBREF),
                    page_range=cval(row, _COL_ED_PAGES),
                    is_reprint=cyesno(row, "Reprint?"),
                    reprint_of=cval(row, _COL_ED_REPRINT_OF),
                    reprint_notes=" | ".join(filter(None, [
                        cval(row, "If reprint, identically typeset?"),
                        cval(row, "If reprint, newly typeset?"),
                    ])) or None,
                    has_scan=has_scan,
                    has_transcription=cyesno(row, _COL_ED_TRANSCRIBED),
                    transcription_notes=cval(row, "Our transcribed ed.?"),
                    collated=cyesno(row, _COL_ED_COLLATED),
                    edition_refs=", ".join(edition_ref_parts) or None,
                    notes=cval(row, "Notes"),
                    text_id=text_obj.id if text_obj else None,
                )
                session.add(edition)
                session.flush()
                stats["editions_inserted"] += 1

                # --- Scan URL -> ExternalResource ---
                if scan_url:
                    scan_url = _validate_url(scan_url, excel_row, _COL_ED_SCAN_LINK, report)
                if scan_url:
                    resource = _get_or_create_resource(
                        scan_url, "scan", scan_comment, resource_cache, session
                    )
                    exists = session.exec(
                        select(EditionExternalResource).where(
                            EditionExternalResource.edition_id == edition.id,
                            EditionExternalResource.resource_id == resource.id,
                        )
                    ).first()
                    if not exists:
                        session.add(EditionExternalResource(
                            edition_id=edition.id,
                            resource_id=resource.id,
                        ))
                    stats["urls_imported"] += 1
                elif scan_cell and scan_cell.value:
                    stats["urls_skipped"] += 1

                # --- EditionManuscript links (cols W-AL, positional) ---
                for idx in _EDITION_MS_COL_INDICES:
                    if idx >= len(row_cells_list):
                        continue
                    ms_cell = row_cells_list[idx]
                    # --- Link to Manuscript via Collection ID (Fuzzy Match) ---
                    ms_val = str(ms_cell.value).strip() if ms_cell.value else ""
                    if not ms_val or ms_val.upper() == "N/A":
                        continue
                    
                    match_val = normalize_id(ms_val)
                    target_ms = ms_coll_cache.get(match_val)
                    
                    if target_ms is None:
                        report.add("invalid_format", {
                            "Row": excel_row,
                            "Column": f"col index {idx} (W-AL)",
                            "Value": ms_val,
                            "Reason": f"Collection identifier '{match_val}' not found in Manuscript table",
                        })
                        continue
                    
                    inspection = "uncertain" if "(?)" in ms_val else _cell_inspection_status(ms_cell)
                    exists = session.exec(
                        select(EditionManuscript).where(
                            EditionManuscript.edition_id == edition.id,
                            EditionManuscript.manuscript_id == target_ms.id,
                        )
                    ).first()
                    if not exists:
                        session.add(EditionManuscript(
                            edition_id=edition.id,
                            manuscript_id=target_ms.id,
                            inspection_status=inspection,
                        ))
                        stats["ms_links_created"] += 1

            session.commit()
            logger.info(
                f"[Tab 2] Batch committed — "
                f"{stats['editions_inserted']} editions inserted so far"
            )
        except Exception as e:
            logger.error(f"[Tab 2] Batch error: {e}")
            report.add("critical_error", {"Error": str(e)})
            session.rollback()
            continue

    logger.info(
        f"[Tab 2] Done — "
        f"{stats['editions_inserted']} editions inserted, "
        f"{stats['ms_links_created']} edition-manuscript links created, "
        f"{stats['urls_imported']} scan URLs imported, "
        f"{stats['urls_skipped']} URLs skipped."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info(f"Using database at {DB_PATH}")
    logger.info(f"Reading: {EXCEL}")

    if not EXCEL.exists():
        logger.error(f"File not found: {EXCEL}")
        return

    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    wb = load_workbook(EXCEL, data_only=True)
    logger.info(f"Worksheets: {wb.sheetnames}")

    report = ImportReport()

    with Session(engine) as session:
        logger.info("=== Step 1: Importing Text (Tab 3) ===")
        text_cache = import_texts(session, wb, report)

        logger.info("=== Step 2: Importing Manuscripts (Tab 1) ===")
        ms_cache, ms_coll_cache = import_manuscripts(session, wb, text_cache, report)

        logger.info("=== Step 3: Importing Editions (Tab 2) ===")
        import_editions(session, wb, text_cache, ms_cache, ms_coll_cache, report)

    report.save(str(DATA_ROOT / "import_hagio_validation.xlsx"))
    logger.info(
        f"Import complete. "
        f"Validation report: {DATA_ROOT / 'import_hagio_validation.xlsx'}"
    )


if __name__ == "__main__":
    main()
