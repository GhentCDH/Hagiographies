"""Excel-to-database import pipeline for the Hagiographies project.

Entry point: main() — called via the package CLI or directly.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple, Type, Any

import pandas as pd
from rich.logging import RichHandler
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, select

from utilities.config import EXCEL
from utilities.db import engine, create_updated_at_trigger
from utilities.model import (
    CorpusHagio, Manuscript, Witness, Edition, EditionManuscriptLink,
    City, Library, Location, Origin, Reference, Provenance,
    Archbishopric, Bishopric, Author, DatingRough, Subtype, Destinatary, 
    ProseVerse, SourceType, PreservationStatus, VernacularRegion, 
    ManuscriptType, ImageAvailability
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
# Type aliases
# ---------------------------------------------------------------------------

Cache = dict[str, int]  # name -> DB id


# ---------------------------------------------------------------------------
# Safe-conversion helpers (Omitted for brevity, they remain identical to your original code)
# ---------------------------------------------------------------------------

def safe_str(value: Any) -> Optional[str]:
    if pd.isna(value): return None
    s = str(value).strip()
    return s if s else None

def safe_int(value: Any) -> Optional[int]:
    if pd.isna(value): return None
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (ValueError, TypeError):
        return None

def safe_bool(value: Any) -> Optional[bool]:
    if pd.isna(value): return None
    s = str(value).strip().upper()
    if s in ("Y", "YES", "TRUE", "1", "T"): return True
    if s in ("N", "NO", "FALSE", "0", "F"): return False
    return None

def _normalize_float_str(raw: str) -> str:
    raw = raw.replace(",", "").strip()
    parts = raw.split(".")
    if len(parts) > 2:
        raw = parts[0] + "." + "".join(parts[1:])
    return raw

def safe_float(value: Any) -> Optional[float]:
    if pd.isna(value): return None
    if isinstance(value, str):
        value = _normalize_float_str(value)
        if not value: return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def safe_coordinate(value: Any, *, lo: float, hi: float) -> Optional[float]:
    f = safe_float(value)
    if f is None: return None
    if abs(f) > abs(hi) * 1000: f /= 1_000_000
    if not (lo <= f <= hi):
        logger.warning("Coordinate %s out of range [%s, %s] -- skipping.", f, lo, hi)
        return None
    return f

def safe_latitude(value: Any) -> Optional[float]:
    return safe_coordinate(value, lo=-90.0, hi=90.0)

def safe_longitude(value: Any) -> Optional[float]:
    return safe_coordinate(value, lo=-180.0, hi=180.0)


# ---------------------------------------------------------------------------
# Dating parser
# ---------------------------------------------------------------------------
_RE_CENTURY = re.compile(r"^(\d{1,2})(?:\((\d)(?:/(\d))?\))?$")
_RE_RANGE   = re.compile(r"^(\d{1,2})(?:\((\d)(?:/(\d))?\))?-(\d{1,2})(?:\((\d)(?:/(\d))?\))?$")
_RE_YEAR    = re.compile(r"^(\d{3,4})(?:-(\d{3,4}))?$")
_RE_CIRCA   = re.compile(r"^(?:c(?:irca|\.)?|ca\.?)\s*(\d{3,4})$", re.IGNORECASE)

def _century_bounds(century: int, half: Optional[int], quarter: Optional[int]) -> Tuple[int, int]:
    base_start = (century - 1) * 100 + 1
    base_end   = century * 100
    if half is None: return base_start, base_end
    half_start = base_start + (half - 1) * 50
    half_end   = half_start + 49
    if quarter is None: return half_start, half_end
    qtr_start = base_start + (half - 1) * 25
    qtr_end   = qtr_start + 24
    return qtr_start, qtr_end

def parse_dating(raw: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    if not raw: return None, None, None
    s = raw.strip()
    if s.lower() in ("nan", "n/a", "none", "-", ""): return None, None, None
    comment = s
    s_clean = re.sub(r"(?i)(ste?|de?|th|nd|rd)?\s*eeuw.*$", "", s).strip()
    s_clean = re.sub(r"(?i)\s*century.*$", "", s_clean).strip()
    m = _RE_CIRCA.match(s_clean)
    if m:
        y = int(m.group(1))
        return y - 5, y + 5, comment
    m = _RE_YEAR.match(s_clean)
    if m:
        start = int(m.group(1))
        end   = int(m.group(2)) if m.group(2) else start
        return start, end, comment
    m = _RE_RANGE.match(s_clean)
    if m:
        c1, h1, q1 = int(m.group(1)), safe_int(m.group(2)), safe_int(m.group(3))
        c2, h2, q2 = int(m.group(4)), safe_int(m.group(5)), safe_int(m.group(6))
        start, _ = _century_bounds(c1, h1, q1)
        _, end   = _century_bounds(c2, h2, q2)
        return start, end, comment
    m = _RE_CENTURY.match(s_clean)
    if m:
        century = int(m.group(1))
        half    = safe_int(m.group(2))
        quarter = safe_int(m.group(3))
        start, end = _century_bounds(century, half, quarter)
        return start, end, comment
    logger.warning("parse_dating: unrecognised format %r -- stored as comment only.", raw)
    return None, None, comment


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create(session: Session, model: Type, **kwargs) -> Any:
    instance = session.exec(select(model).filter_by(**kwargs)).first()
    if instance:
        return instance
        
    instance = model(**kwargs)
    session.add(instance)
    
    try:
        with session.begin_nested():
            session.flush()
            session.refresh(instance)
        return instance
    except IntegrityError:
        logger.warning(f"Record voor {model.__name__} bestaat al of schendt constraint. Verdergaan...")
        return session.exec(select(model).filter_by(**kwargs)).first()


def get_or_create_lookup(
    session: Session, 
    model: Type, 
    cache: Cache, 
    raw_value: Any, 
    field_name: str = "name"
) -> Optional[int]:
    """Helper for fetching/creating ID for simple one-column lookup tables.

    Args:
        session (Session): DB session.
        model (Type): Lookup table class (e.g., Author, SourceType).
        cache (Cache): Dict mapping strings to DB IDs.
        raw_value (Any): Cell value.
        field_name (str): The column name to populate in the model.

    Returns:
        Optional[int]: The foreign key ID, or None if raw_value is empty.
    """
    val = safe_str(raw_value)
    if not val or val.lower() in ("nan", "n/a", "none", "-"):
        return None
    if val not in cache:
        kwargs = {field_name: val}
        obj = get_or_create(session, model, **kwargs)
        if obj:
            cache[val] = obj.id
    return cache.get(val)


def get_or_create_jurisdiction(session: Session, model: Type, cache: Cache, raw_name: Any) -> Optional[int]:
    return get_or_create_lookup(session, model, cache, raw_name)


def clean_bhl(raw: Any) -> Optional[str]:
    if pd.isna(raw): return None
    s = str(raw).strip()
    if s.endswith(".0"): s = s[:-2]
    return s if s and s.lower() != "nan" else None

def clean_unique_id(raw: Any) -> Optional[str]:
    if pd.isna(raw): return None
    s = str(raw).strip()
    if "(" in s: s = s.split("(")[0].strip()
    if s.endswith(".0"): s = s[:-2]
    return s if s else None

def _find_column(df: pd.DataFrame, exact: str, substring: str) -> str:
    if exact in df.columns: return exact
    for col in df.columns:
        if substring in str(col): return col
    return exact


# ---------------------------------------------------------------------------
# Sheet processors
# ---------------------------------------------------------------------------

def _process_corpus_hagio(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    origins_cache: dict,
    archbishoprics_cache: Cache,
    bishoprics_cache: Cache,
) -> None:
    COL_BHL     = "BHL reference"
    COL_LAT_ORG = "GPS Longitude OR"
    COL_LON_ORG = "GPS Latitude OR"
    COL_LAT_DES = "GPS Longitude DES"
    COL_LON_DES = "GPS Latitude DES"

    # Local caches for new category fields
    authors_cache: Cache = {}
    dating_rough_cache: Cache = {}
    destinatary_cache: Cache = {}
    source_type_cache: Cache = {}
    subtype_cache: Cache = {}
    prose_verse_cache: Cache = {}

    for _, row in df.iterrows():
        bhl = clean_bhl(row.get(COL_BHL))
        if not bhl:
            continue

        origin_id: Optional[int] = None
        origin_name = safe_str(row.get("Origin"))
        if origin_name:
            if origin_name not in origins_cache:
                origin = get_or_create(session, Origin, name=origin_name)
                if origin:
                    origin.latitude = safe_latitude(row.get(COL_LAT_ORG))
                    origin.longitude = safe_longitude(row.get(COL_LON_ORG))
                    origin.archbishopric_id = get_or_create_jurisdiction(session, Archbishopric, archbishoprics_cache, row.get("Archbishopric"))
                    origin.bishopric_id = get_or_create_jurisdiction(session, Bishopric, bishoprics_cache, row.get("Bishopric"))
                    origins_cache[origin_name] = origin
            origin_obj = origins_cache.get(origin_name)
            if origin_obj:
                origin_id = origin_obj.id

        text = get_or_create(session, CorpusHagio, bhl_number=bhl)
        if not text:
            continue
            
        text.title = safe_str(row.get("Title")) or text.title or "Unknown"
        text.origin_id = origin_id
        
        # Categorical lookups
        text.author_id = get_or_create_lookup(session, Author, authors_cache, row.get("Author"))
        text.dating_rough_id = get_or_create_lookup(session, DatingRough, dating_rough_cache, row.get("Rough chronology"))
        text.primary_destinatary_id = get_or_create_lookup(session, Destinatary, destinatary_cache, row.get("Primary destinatary"))
        text.source_type_id = get_or_create_lookup(session, SourceType, source_type_cache, row.get("Source type"))
        text.subtype_id = get_or_create_lookup(session, Subtype, subtype_cache, row.get("Subtype"))
        text.prose_verse_id = get_or_create_lookup(session, ProseVerse, prose_verse_cache, row.get("Mainly prose or verse"))

        text.destinatary_latitude  = safe_latitude(row.get(COL_LAT_DES))
        text.destinatary_longitude = safe_longitude(row.get(COL_LON_DES))
        text.approx_length    = safe_int(row.get("Approx. length in words"))
        text.archbishopric_id = get_or_create_jurisdiction(session, Archbishopric, archbishoprics_cache, row.get("Archbishopric"))
        text.bishopric_id     = get_or_create_jurisdiction(session, Bishopric, bishoprics_cache, row.get("Bishopric"))
        
        text.is_reecriture    = safe_bool(row.get("Reecriture?"))
        text.ocr_status       = safe_str(row.get("Cleaned?"))
        text.notes            = safe_str(row.get("Notes"))

        try:
            with session.begin_nested():
                session.add(text)
                session.flush()
                existing_texts[bhl] = text
        except IntegrityError:
            logger.warning(f"CorpusHagio record (BHL {bhl}) schendt unique constraint. Overslaan...")

    session.commit()
    logger.info("Processed %d entries from Corpus hagio.", len(existing_texts))


def _process_manuscripts(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    origins_cache: dict,
    archbishoprics_cache: Cache,
    bishoprics_cache: Cache,
    col_bhl: str,
    col_ms_id: str,
    col_collection_id: str,
    col_title: str,
) -> dict:
    existing_manuscripts: dict[str, Manuscript] = {}
    collection_id_map: dict[str, Manuscript] = {}
    
    cities_cache: dict[str, City] = {}
    libraries_cache: dict[str, Library] = {}
    locations_cache: dict[tuple, Location] = {}
    provenance_cache: dict[tuple, int] = {}  # composite key -> provenance ID

    # Caches for Manuscript status fields
    pres_status_cache: Cache = {}
    vernac_region_cache: Cache = {}
    ms_type_cache: Cache = {}
    img_avail_cache: Cache = {}

    col_dating_raw     = _find_column(df, "Dating ",     "Dating")
    col_dating_century = _find_column(df, "Dating by (earliest) century", "Dating by")
    col_dating_start   = _find_column(df, "Dating range start", "range start")
    col_dating_end     = _find_column(df, "Dating range end",   "range end")
    col_certain        = _find_column(df, " Certain?", "Certain")

    for _, row in df.iterrows():
        bhl = clean_bhl(row[col_bhl])
        if not bhl: continue

        if bhl not in existing_texts:
            origin_id: Optional[int] = None
            origin_name = safe_str(row.get("Origin"))
            if origin_name:
                if origin_name not in origins_cache:
                    origins_cache[origin_name] = get_or_create(session, Origin, name=origin_name)
                origin_obj = origins_cache.get(origin_name)
                if origin_obj:
                    origin_id = origin_obj.id
                    
            text = get_or_create(session, CorpusHagio, bhl_number=bhl)
            if text:
                text.title = safe_str(row.get(col_title)) or text.title or "Unknown"
                text.origin_id = origin_id
                try:
                    with session.begin_nested():
                        session.add(text)
                        session.flush()
                        existing_texts[bhl] = text
                except IntegrityError:
                    pass

        ms_unique_id = clean_unique_id(row.get(col_ms_id))
        if not ms_unique_id: continue

        if ms_unique_id not in existing_manuscripts:
            city_name    = safe_str(row.get("Location")) or "Unknown"
            library_name = safe_str(row.get("Heritage institution")) or "Unknown"
            shelfmark    = safe_str(row.get("Shelfmark")) or "Unknown"

            city = cities_cache.setdefault(city_name, get_or_create(session, City, name=city_name))
            library = libraries_cache.setdefault(library_name, get_or_create(session, Library, name=library_name))
            
            if not city or not library: continue

            loc_key  = (city.id, library.id, shelfmark)
            location = locations_cache.setdefault(
                loc_key,
                get_or_create(session, Location, city_id=city.id, library_id=library.id, shelfmark=shelfmark),
            )

            ms = Manuscript(location_id=location.id, unique_id=ms_unique_id)
            
            # Lookup fields mapping
            ms.preservation_status_id = get_or_create_lookup(session, PreservationStatus, pres_status_cache, row.get("Preservation status"))
            ms.vernacular_region_id = get_or_create_lookup(session, VernacularRegion, vernac_region_cache, row.get("Vernacular region (Romance/Germanic)"))
            ms.manuscript_type_id = get_or_create_lookup(session, ManuscriptType, ms_type_cache, row.get("Manuscript type"))
            ms.image_availability_id = get_or_create_lookup(session, ImageAvailability, img_avail_cache, row.get("IIIF, scan, or no images"))
            
            ms.height                 = safe_float(row.get("Height"))
            ms.width                  = safe_float(row.get("Width"))
            ms.leg                    = safe_bool(row.get("LEG"))
            ms.dg                     = safe_bool(row.get("DG"))
            ms.naso                   = safe_bool(row.get("NASO"))
            ms.ed_sec                 = safe_bool(row.get("ED/SEC"))
            ms.catalog_link           = safe_str(row.get("Online catalogue link"))
            ms.bollandist_catalog_link = safe_str(row.get("Bollandist catalogue link"))
            ms.other_catalog_link     = safe_str(row.get("Other relevant catalogue link"))
            ms.image_link             = safe_str(row.get("Link to images"))
            ms.copy_of_exemplar_1     = safe_str(row.get("Copy of which first exemplar?"))
            ms.copy_of_exemplar_2     = safe_str(row.get("Copy of which second exemplar?"))
            ms.copy_of_exemplar_3     = safe_str(row.get("Copy of which third exemplar?"))
            ms.exemplar_certain       = safe_bool(row.get(col_certain))
            ms.notes_on_exemplar      = safe_str(row.get("Notes on exemplar"))
            ms.exemplar_of_ms_1       = safe_str(row.get("Exemplar of which manuscript (1)?"))
            ms.exemplar_of_ms_2       = safe_str(row.get("Exemplar of which manuscript (2)?"))
            ms.exemplar_of_ms_3       = safe_str(row.get("Exemplar of which manuscript (3)?"))
            ms.exemplar_of_ms_4       = safe_str(row.get("Exemplar of which manuscript (4)?"))
            ms.notes_on_copies        = safe_str(row.get("Notes on copies"))

            try:
                with session.begin_nested():
                    session.add(ms)
                    session.flush()
                    session.refresh(ms)
                existing_manuscripts[ms_unique_id] = ms
                coll_id = safe_str(row.get(col_collection_id))
                if coll_id: collection_id_map[coll_id] = ms
            except IntegrityError:
                existing_ms = session.exec(select(Manuscript).filter_by(unique_id=ms_unique_id)).first()
                if existing_ms:
                    existing_manuscripts[ms_unique_id] = existing_ms
                    coll_id = safe_str(row.get(col_collection_id))
                    if coll_id: collection_id_map[coll_id] = existing_ms
                else:
                    continue

        manuscript = existing_manuscripts.get(ms_unique_id)
        text       = existing_texts.get(bhl)
        if not manuscript or not text: continue

        # Handle Composite Provenance
        prov_name = safe_str(row.get("Provenance general"))
        prov_arch = safe_str(row.get("Provenance archdiocese"))
        prov_dioc = safe_str(row.get("Provenance diocese"))
        prov_inst = safe_str(row.get("Provenance institution"))
        
        prov_key = (prov_name, prov_arch, prov_dioc, prov_inst)
        provenance_id: Optional[int] = None
        
        if prov_key != (None, None, None, None):
            if prov_key not in provenance_cache:
                prov_obj = get_or_create(
                    session, Provenance, 
                    name=prov_name, archdiocese=prov_arch, diocese=prov_dioc, institution=prov_inst
                )
                if prov_obj:
                    provenance_cache[prov_key] = prov_obj.id
            provenance_id = provenance_cache.get(prov_key)

        dating_raw   = safe_str(row.get(col_dating_raw))
        dating_start = safe_int(row.get(col_dating_start))
        dating_end   = safe_int(row.get(col_dating_end))

        if (dating_start is None or dating_end is None) and dating_raw:
            fb_start, fb_end, fb_comment = parse_dating(dating_raw)
            dating_start   = dating_start   or fb_start
            dating_end     = dating_end     or fb_end
            dating_comment = fb_comment
        else:
            dating_comment = dating_raw

        witness = Witness(
            text_id=text.id,
            manuscript_id=manuscript.id,
            ms_number_per_bhl       = safe_str(row.get("MS N° per BHL number")),
            page_range              = safe_str(row.get("Folio or page per BHL")),
            dating_century          = safe_str(row.get(col_dating_century)),
            dating_raw              = dating_raw,
            dating_start            = dating_start,
            dating_end              = dating_end,
            dating_comment          = dating_comment,
            provenance_id           = provenance_id,
            archbishopric_id        = get_or_create_jurisdiction(session, Archbishopric, archbishoprics_cache, row.get("Archbishopric")),
            bishopric_id            = get_or_create_jurisdiction(session, Bishopric, bishoprics_cache, row.get("Bishopric")),
        )
        
        try:
            with session.begin_nested():
                session.add(witness)
                session.flush()
        except IntegrityError:
            pass

    session.commit()
    logger.info("Processed %d manuscripts and witnesses.", len(existing_manuscripts))
    return collection_id_map


def _process_editions(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    collection_id_map: dict,
) -> None:
    references_cache: dict[str, Reference] = {}
    col_bhl = _find_column(df, "BHL", "BHL")

    for _, row in df.iterrows():
        bhl = clean_bhl(row.get(col_bhl))
        if not bhl or bhl not in existing_texts: continue

        ref_name = safe_str(row.get("Edition reference")) or "Unknown"
        ref = references_cache.setdefault(ref_name, get_or_create(session, Reference, title=ref_name))
        if not ref: continue

        edition = Edition(
            text_id=existing_texts[bhl].id,
            title=safe_str(row.get("Title")) or "Unknown",
            reference_id=ref.id,
            year=safe_int(row.get("Date")),
        )
        
        try:
            with session.begin_nested():
                session.add(edition)
                session.flush()
                session.refresh(edition)
        except IntegrityError:
            edition = session.exec(select(Edition).filter_by(text_id=edition.text_id, reference_id=ref.id)).first()
            if not edition: continue

        linked_ms_ids: set[int] = set()
        for i in range(1, 17):
            val = safe_str(row.get(f"MS USED {i}"))
            if val:
                ms_obj = collection_id_map.get(val)
                if ms_obj and ms_obj.id not in linked_ms_ids:
                    try:
                        with session.begin_nested():
                            session.add(EditionManuscriptLink(edition_id=edition.id, manuscript_id=ms_obj.id))
                            session.flush()
                            linked_ms_ids.add(ms_obj.id)
                    except IntegrityError:
                        pass

    session.commit()
    logger.info("Editions processed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    if not EXCEL.exists():
        logger.warning("Excel file not found at %s, skipping import.", EXCEL)
        return

    logger.info("Reading Excel file: %s", EXCEL)

    try: df_ms = pd.read_excel(EXCEL, sheet_name="Manuscripts", header=0)
    except ValueError:
        logger.error("Sheet 'Manuscripts' not found -- aborting.")
        return

    try: df_ch = pd.read_excel(EXCEL, sheet_name="Corpus hagio")
    except ValueError: df_ch = pd.DataFrame()

    try: df_ed = pd.read_excel(EXCEL, sheet_name="Editions")
    except ValueError: df_ed = pd.DataFrame()

    col_bhl           = df_ms.columns[0]
    col_title         = "Title"
    col_ms_id         = "Unique ID"
    col_collection_id = _find_column(df_ms, "Unique  identifier per collection", "identifier per collection")

    origins_cache:        dict = {}
    archbishoprics_cache: Cache = {}
    bishoprics_cache:     Cache = {}
    existing_texts:       dict = {}

    with Session(engine) as session:
        if not df_ch.empty:
            logger.info("Processing Corpus Hagio sheet...")
            _process_corpus_hagio(
                df_ch, session, existing_texts,
                origins_cache, archbishoprics_cache, bishoprics_cache,
            )

        logger.info("Processing Manuscripts sheet...")
        collection_id_map = _process_manuscripts(
            df_ms, session, existing_texts,
            origins_cache, archbishoprics_cache, bishoprics_cache,
            col_bhl, col_ms_id, col_collection_id, col_title,
        )

        if not df_ed.empty:
            logger.info("Processing Editions sheet...")
            _process_editions(df_ed, session, existing_texts, collection_id_map)

    logger.info("Import complete.")

if __name__ == "__main__":
    main()