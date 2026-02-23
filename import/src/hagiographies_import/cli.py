"""
cli.py — Excel-to-database import pipeline for the Hagiographies project.

Entry point: main() — called via the package CLI or directly.

Import order
------------
1. "Corpus hagio" sheet  -> CorpusHagio (+ Origin, Archbishopric, Bishopric)
2. "Manuscripts" sheet   -> Manuscript, Location, City, Library, Witness,
                            Provenance (+ backfill CorpusHagio if missing)
3. "Editions" sheet      -> Edition, Reference, EditionManuscriptLink

GPS coordinate note
-------------------
The source Excel has the "GPS Latitude OR" and "GPS Longitude OR" column
headers *swapped*.  The mapping below corrects this intentionally.
Do NOT change these assignments without verifying the source file.

  col_lat_org = "GPS Longitude OR"  # mislabelled in Excel -> actually Latitude
  col_lon_org = "GPS Latitude OR"   # mislabelled in Excel -> actually Longitude

Dating notation (Witness)
--------------------------
The Manuscripts sheet already contains pre-parsed numeric columns
"Dating range start" and "Dating range end".  These are used directly.
"Dating " (trailing space!) holds the verbatim source string.
"Dating by (earliest) century" holds the rough century label.

parse_dating() is applied as a *fallback* only when start/end are missing
but dating_raw is present.  Conversion table:

  "1036-1055"   -> 1036 - 1055
  "1050"        -> 1050 - 1050
  "11de eeuw"   -> 1001 - 1100
  "11(1)"       -> 1001 - 1050  (first half)
  "11(2)"       -> 1051 - 1100  (second half)
  "11(1/4)"     -> 1001 - 1025  (first quarter)
  "11(2/4)"     -> 1026 - 1050
  "11(3/4)"     -> 1051 - 1075
  "11(4/4)"     -> 1076 - 1100
  "11(2)-12(1)" -> 1051 - 1150  (cross-century range)
  "circa 1050"  -> 1045 - 1055  (+/- 5 year window)

Manuscripts sheet column names
-------------------------------
Several headers contain artefacts from the source Excel:
  "Unique  identifier per collection"  -- double space (handled by _find_column)
  "Dating "                            -- trailing space
  " Certain?"                          -- leading space
The _find_column() helper and the explicit COL_* constants below account
for these quirks so that renames in the source file break loudly rather
than silently producing NULL values.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple, Type

import pandas as pd
from rich.logging import RichHandler
from sqlmodel import SQLModel, Session, select

from .config import EXCEL
from .db import engine, create_updated_at_trigger
from .model import (
    CorpusHagio, Manuscript, Witness, Edition, EditionManuscriptLink,
    City, Library, Location, Origin, Reference, Provenance,
    Archbishopric, Bishopric,
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
# Safe-conversion helpers
# ---------------------------------------------------------------------------

def safe_str(value) -> Optional[str]:
    """Return stripped string or None for NaN / empty values."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def safe_int(value) -> Optional[int]:
    """Convert value to int, tolerating floats like 6318.0 and comma strings."""
    if pd.isna(value):
        return None
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (ValueError, TypeError):
        return None


def safe_bool(value) -> Optional[bool]:
    """Convert Y/N / YES/NO / TRUE/FALSE strings to bool."""
    if pd.isna(value):
        return None
    s = str(value).strip().upper()
    if s in ("Y", "YES", "TRUE", "1", "T"):
        return True
    if s in ("N", "NO", "FALSE", "0", "F"):
        return False
    return None


def _normalize_float_str(raw: str) -> str:
    """Normalise a raw string to a parseable float literal.

    - Removes commas (thousands separator).
    - Collapses multiple dots ("5.189.84") to a single decimal separator.
    """
    raw = raw.replace(",", "").strip()
    parts = raw.split(".")
    if len(parts) > 2:
        raw = parts[0] + "." + "".join(parts[1:])
    return raw


def safe_float(value) -> Optional[float]:
    """Convert value to float, normalising string artefacts.

    Returns None for NaN, empty strings, or non-parseable values.
    """
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = _normalize_float_str(value)
        if not value:
            return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_coordinate(value, *, lo: float, hi: float) -> Optional[float]:
    """Parse a GPS coordinate and validate against the expected range.

    Some source values are stored as microdegrees (integer x 1e-6 degrees).
    When the parsed value exceeds hi * 1000 it is scaled down by 1_000_000.

    Args:
        value: Raw cell value.
        lo:    Minimum valid coordinate (e.g. -90.0 for latitude).
        hi:    Maximum valid coordinate (e.g.  90.0 for latitude).

    Returns:
        Decimal-degree float, or None if missing / out of range.
    """
    f = safe_float(value)
    if f is None:
        return None
    if abs(f) > abs(hi) * 1000:
        f /= 1_000_000
    if not (lo <= f <= hi):
        logger.warning("Coordinate %s out of range [%s, %s] -- skipping.", f, lo, hi)
        return None
    return f


def safe_latitude(value) -> Optional[float]:
    """Parse a latitude value (WGS-84, range -90 to +90)."""
    return safe_coordinate(value, lo=-90.0, hi=90.0)


def safe_longitude(value) -> Optional[float]:
    """Parse a longitude value (WGS-84, range -180 to +180)."""
    return safe_coordinate(value, lo=-180.0, hi=180.0)


# ---------------------------------------------------------------------------
# Dating parser (fallback for rows missing pre-parsed range columns)
# ---------------------------------------------------------------------------

_RE_CENTURY = re.compile(r"^(\d{1,2})(?:\((\d)(?:/(\d))?\))?$")
_RE_RANGE   = re.compile(r"^(\d{1,2})(?:\((\d)(?:/(\d))?\))?-(\d{1,2})(?:\((\d)(?:/(\d))?\))?$")
_RE_YEAR    = re.compile(r"^(\d{3,4})(?:-(\d{3,4}))?$")
_RE_CIRCA   = re.compile(r"^(?:c(?:irca|\.)?|ca\.?)\s*(\d{3,4})$", re.IGNORECASE)


def _century_bounds(
    century: int, half: Optional[int], quarter: Optional[int]
) -> Tuple[int, int]:
    """Return (start_year, end_year) for a century notation.

    Args:
        century: Century number (e.g. 11 for the 11th century).
        half:    1 = first half, 2 = second half, or None for full century.
        quarter: Quarter numerator 1-4 (from X/4 notation), or None.

    Examples:
        _century_bounds(11, None, None) -> (1001, 1100)
        _century_bounds(11, 1, None)    -> (1001, 1050)
        _century_bounds(11, 2, None)    -> (1051, 1100)
        _century_bounds(11, 1, 4)       -> (1001, 1025)  # 11(1/4)
        _century_bounds(11, 3, 4)       -> (1051, 1075)  # 11(3/4)
    """
    base_start = (century - 1) * 100 + 1
    base_end   = century * 100

    if half is None:
        return base_start, base_end

    half_start = base_start + (half - 1) * 50
    half_end   = half_start + 49

    if quarter is None:
        return half_start, half_end

    qtr_start = base_start + (half - 1) * 25
    qtr_end   = qtr_start + 24
    return qtr_start, qtr_end


def parse_dating(raw: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Parse a raw dating string into (start_year, end_year, comment).

    This is a *fallback* parser used only when the Manuscripts sheet does not
    already provide numeric "Dating range start" / "Dating range end" values.

    Supported formats
    ------------------
    Input            start   end
    "1036-1055"      1036   1055
    "1050"           1050   1050
    "11de eeuw"      1001   1100
    "11(1)"          1001   1050
    "11(2)"          1051   1100
    "11(1/4)"        1001   1025
    "11(2/4)"        1026   1050
    "11(3/4)"        1051   1075
    "11(4/4)"        1076   1100
    "11(2)-12(1)"    1051   1150
    "circa 1050"     1045   1055
    "c. 1050"        1045   1055

    Returns:
        (start, end, comment) where comment echoes the original string.
        Returns (None, None, None) for empty / unrecognised input.
    """
    if not raw:
        return None, None, None
    s = raw.strip()
    if s.lower() in ("nan", "n/a", "none", "-", ""):
        return None, None, None

    comment = s

    # Strip textual suffixes: "de eeuw", "ste eeuw", "th century", etc.
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

def get_or_create(session: Session, model: Type, **kwargs):
    """Return the first row matching kwargs, or INSERT and return a new one.

    After insertion the session is flushed so that the new row gets a PK
    that can be referenced within the same transaction.

    Args:
        session: Active SQLModel session.
        model:   SQLModel table class.
        **kwargs: Column filters / initial values for the new row.

    Returns:
        An instance of model, either pre-existing or freshly created.
    """
    instance = session.exec(select(model).filter_by(**kwargs)).first()
    if instance:
        return instance
    instance = model(**kwargs)
    session.add(instance)
    session.flush()
    session.refresh(instance)
    return instance


def get_or_create_jurisdiction(
    session: Session,
    model: Type,
    cache: Cache,
    raw_name,
) -> Optional[int]:
    """Return the DB id for a jurisdiction row, creating it if needed.

    Normalises the name and rejects sentinel values ("nan", "n/a", "-").
    Results are cached in cache to avoid redundant SELECTs.

    Args:
        session:  Active SQLModel session.
        model:    Either Archbishopric or Bishopric.
        cache:    Per-import dict mapping name -> id; mutated in place.
        raw_name: Raw cell value from the Excel sheet.

    Returns:
        Integer PK, or None if the value is absent or a sentinel.
    """
    if pd.isna(raw_name):
        return None
    name = str(raw_name).strip()
    if not name or name.lower() in ("nan", "n/a", "none", "-"):
        return None
    if name not in cache:
        obj = get_or_create(session, model, name=name)
        cache[name] = obj.id
    return cache[name]


def clean_bhl(raw) -> Optional[str]:
    """Normalise a BHL number from an Excel cell.

    Strips trailing ".0" from numeric representations (e.g. "1234.0" -> "1234").
    Returns None for NaN or empty strings.
    """
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s and s.lower() != "nan" else None


def clean_unique_id(raw) -> Optional[str]:
    """Normalise a manuscript Unique ID.

    - Strips parenthetical suffixes such as "(lost)" or "(lost?)".
    - Strips trailing ".0" from numeric representations.

    Returns None if the cell is NaN.
    """
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if "(" in s:
        s = s.split("(")[0].strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s else None


def _find_column(df: pd.DataFrame, exact: str, substring: str) -> str:
    """Return the first column matching exact, or the first matching substring.

    Useful for columns whose headers sometimes carry extra whitespace or
    minor spelling variations between Excel versions.

    Args:
        df:        DataFrame to search.
        exact:     Exact column name to look for first.
        substring: Fallback substring to match against all column names.

    Returns:
        Matching column name, or exact if nothing is found.
    """
    if exact in df.columns:
        return exact
    for col in df.columns:
        if substring in str(col):
            return col
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
    """Populate CorpusHagio (and Origin) from the "Corpus hagio" sheet.

    GPS NOTE: column headers are swapped in the source Excel -- see module
    docstring.  Do NOT change the col_lat_org / col_lon_org mapping below.
    """
    COL_BHL     = "BHL reference"
    # Swapped column names -- see module docstring
    COL_LAT_ORG = "GPS Longitude OR"
    COL_LON_ORG = "GPS Latitude OR"
    COL_LAT_DES = "GPS Longitude DES"
    COL_LON_DES = "GPS Latitude DES"

    logger.warning(
        "GPS coordinate columns are swapped in the source Excel. "
        "Latitude/Longitude mapping has been corrected in code."
    )

    for _, row in df.iterrows():
        bhl = clean_bhl(row.get(COL_BHL))
        if not bhl:
            continue

        # Origin
        origin_id: Optional[int] = None
        origin_name = safe_str(row.get("Origin"))
        if origin_name:
            if origin_name not in origins_cache:
                origin = get_or_create(session, Origin, name=origin_name)
                origin.latitude = safe_latitude(row.get(COL_LAT_ORG))
                origin.longitude = safe_longitude(row.get(COL_LON_ORG))
                origin.archbishopric_id = get_or_create_jurisdiction(
                    session, Archbishopric, archbishoprics_cache, row.get("Archbishopric")
                )
                origin.bishopric_id = get_or_create_jurisdiction(
                    session, Bishopric, bishoprics_cache, row.get("Bishopric")
                )
                origins_cache[origin_name] = origin
            origin_id = origins_cache[origin_name].id

        # CorpusHagio
        text = get_or_create(session, CorpusHagio, bhl_number=bhl)
        text.title            = safe_str(row.get("Title")) or text.title or "Unknown"
        text.author           = safe_str(row.get("Author")) or text.author
        text.dating_rough     = safe_str(row.get("Rough chronology")) or text.dating_rough
        text.origin_id        = origin_id
        text.primary_destinatary   = safe_str(row.get("Primary destinatary"))
        text.destinatary_latitude  = safe_latitude(row.get(COL_LAT_DES))
        text.destinatary_longitude = safe_longitude(row.get(COL_LON_DES))
        text.approx_length    = safe_int(row.get("Approx. length in words"))
        text.archbishopric_id = get_or_create_jurisdiction(
            session, Archbishopric, archbishoprics_cache, row.get("Archbishopric")
        )
        text.bishopric_id     = get_or_create_jurisdiction(
            session, Bishopric, bishoprics_cache, row.get("Bishopric")
        )
        text.source_type      = safe_str(row.get("Source type"))
        text.subtype          = safe_str(row.get("Subtype"))
        text.prose_verse      = safe_str(row.get("Mainly prose or verse"))
        text.is_reecriture    = safe_bool(row.get("Reecriture?"))
        text.ocr_status       = safe_str(row.get("Cleaned?"))
        text.notes            = safe_str(row.get("Notes"))

        session.add(text)
        existing_texts[bhl] = text

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
    """Populate Manuscript, Location, City, Library, Witness, and Provenance.

    Also backfills CorpusHagio rows for BHL numbers not in "Corpus hagio".

    Column name notes
    -----------------
    "Dating "             -- trailing space in Excel header
    " Certain?"           -- leading space in Excel header
    col_collection_id     -- may contain double spaces; resolved by _find_column

    Returns:
        collection_id_map: dict mapping "identifier per collection" -> Manuscript,
        used when linking editions to manuscripts.
    """
    existing_manuscripts: dict[str, Manuscript] = {}
    collection_id_map: dict[str, Manuscript] = {}
    cities_cache: dict[str, City] = {}
    libraries_cache: dict[str, Library] = {}
    locations_cache: dict[tuple, Location] = {}
    provenance_cache: dict[str, Provenance] = {}

    # Resolve column names with whitespace quirks
    col_dating_raw     = _find_column(df, "Dating ",     "Dating")
    col_dating_century = _find_column(df, "Dating by (earliest) century", "Dating by")
    col_dating_start   = _find_column(df, "Dating range start", "range start")
    col_dating_end     = _find_column(df, "Dating range end",   "range end")
    col_certain        = _find_column(df, " Certain?", "Certain")

    for _, row in df.iterrows():
        bhl = clean_bhl(row[col_bhl])
        if not bhl:
            continue

        # Backfill CorpusHagio if missing from the Corpus hagio sheet
        if bhl not in existing_texts:
            origin_id: Optional[int] = None
            origin_name = safe_str(row.get("Origin"))
            if origin_name:
                if origin_name not in origins_cache:
                    origins_cache[origin_name] = get_or_create(session, Origin, name=origin_name)
                origin_id = origins_cache[origin_name].id
            text = get_or_create(session, CorpusHagio, bhl_number=bhl)
            text.title     = safe_str(row.get(col_title)) or text.title or "Unknown"
            text.origin_id = origin_id
            session.add(text)
            existing_texts[bhl] = text

        # Manuscript
        ms_unique_id = clean_unique_id(row.get(col_ms_id))
        if not ms_unique_id:
            continue

        if ms_unique_id not in existing_manuscripts:
            city_name    = safe_str(row.get("Location"))              or "Unknown"
            library_name = safe_str(row.get("Heritage institution"))  or "Unknown"
            shelfmark    = safe_str(row.get("Shelfmark"))             or "Unknown"

            city     = cities_cache.setdefault(
                city_name, get_or_create(session, City, name=city_name)
            )
            library  = libraries_cache.setdefault(
                library_name, get_or_create(session, Library, name=library_name)
            )
            loc_key  = (city.id, library.id, shelfmark)
            location = locations_cache.setdefault(
                loc_key,
                get_or_create(session, Location,
                              city_id=city.id, library_id=library.id,
                              shelfmark=shelfmark),
            )

            ms = Manuscript(location_id=location.id, unique_id=ms_unique_id)
            ms.preservation_status    = safe_str(row.get("Preservation status"))
            ms.vernacular_region      = safe_str(row.get("Vernacular region (Romance/Germanic)"))
            ms.manuscript_type        = safe_str(row.get("Manuscript type"))
            ms.height                 = safe_float(row.get("Height"))
            ms.width                  = safe_float(row.get("Width"))
            # Boolean flags
            ms.leg                    = safe_bool(row.get("LEG"))
            ms.dg                     = safe_bool(row.get("DG"))
            ms.naso                   = safe_bool(row.get("NASO"))
            ms.ed_sec                 = safe_bool(row.get("ED/SEC"))
            # Catalogue / image links
            ms.catalog_link           = safe_str(row.get("Online catalogue link"))
            ms.bollandist_catalog_link = safe_str(row.get("Bollandist catalogue link"))
            ms.other_catalog_link     = safe_str(row.get("Other relevant catalogue link"))
            ms.image_availability     = safe_str(row.get("IIIF, scan, or no images"))
            ms.image_link             = safe_str(row.get("Link to images"))
            # Stemmatic fields
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

            session.add(ms)
            session.flush()
            session.refresh(ms)
            existing_manuscripts[ms_unique_id] = ms

            coll_id = safe_str(row.get(col_collection_id))
            if coll_id:
                collection_id_map[coll_id] = ms

        # Witness
        manuscript = existing_manuscripts[ms_unique_id]
        text       = existing_texts[bhl]

        provenance_id: Optional[int] = None
        prov_name = safe_str(row.get("Provenance general"))
        if prov_name:
            prov = provenance_cache.setdefault(
                prov_name, get_or_create(session, Provenance, name=prov_name)
            )
            provenance_id = prov.id

        dating_raw   = safe_str(row.get(col_dating_raw))
        dating_start = safe_int(row.get(col_dating_start))
        dating_end   = safe_int(row.get(col_dating_end))

        # Fallback: derive start/end from raw string when pre-parsed values absent
        dating_comment: Optional[str] = None
        if (dating_start is None or dating_end is None) and dating_raw:
            fb_start, fb_end, fb_comment = parse_dating(dating_raw)
            dating_start   = dating_start   or fb_start
            dating_end     = dating_end     or fb_end
            dating_comment = fb_comment
        else:
            dating_comment = dating_raw  # echo raw as comment when pre-parsed values exist

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
            provenance_archdiocese  = safe_str(row.get("Provenance archdiocese")),
            provenance_diocese      = safe_str(row.get("Provenance diocese")),
            provenance_institution  = safe_str(row.get("Provenance institution")),
            archbishopric_id        = get_or_create_jurisdiction(
                session, Archbishopric, archbishoprics_cache, row.get("Archbishopric")
            ),
            bishopric_id            = get_or_create_jurisdiction(
                session, Bishopric, bishoprics_cache, row.get("Bishopric")
            ),
        )
        session.add(witness)

    session.commit()
    logger.info("Processed %d manuscripts and witnesses.", len(existing_manuscripts))
    return collection_id_map


def _process_editions(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    collection_id_map: dict,
) -> None:
    """Populate Edition, Reference, and EditionManuscriptLink rows."""
    references_cache: dict[str, Reference] = {}

    # BHL column sometimes has a trailing space in the source
    col_bhl = _find_column(df, "BHL", "BHL")

    for _, row in df.iterrows():
        bhl = clean_bhl(row.get(col_bhl))
        if not bhl or bhl not in existing_texts:
            continue

        ref_name = safe_str(row.get("Edition reference")) or "Unknown"
        ref = references_cache.setdefault(
            ref_name, get_or_create(session, Reference, title=ref_name)
        )

        edition = Edition(
            text_id=existing_texts[bhl].id,
            title=safe_str(row.get("Title")) or "Unknown",
            reference_id=ref.id,
            year=safe_int(row.get("Date")),
        )
        session.add(edition)
        session.flush()
        session.refresh(edition)

        linked_ms_ids: set[int] = set()
        for i in range(1, 17):
            val = safe_str(row.get(f"MS USED {i}"))
            if val:
                ms_obj = collection_id_map.get(val)
                if ms_obj and ms_obj.id not in linked_ms_ids:
                    session.add(
                        EditionManuscriptLink(
                            edition_id=edition.id, manuscript_id=ms_obj.id
                        )
                    )
                    linked_ms_ids.add(ms_obj.id)

    session.commit()
    logger.info("Editions processed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full Excel-to-database import pipeline."""
    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    if not EXCEL.exists():
        logger.warning("Excel file not found at %s, skipping import.", EXCEL)
        return

    logger.info("Reading Excel file: %s", EXCEL)

    try:
        df_ms = pd.read_excel(EXCEL, sheet_name="Manuscripts", header=0)
    except ValueError:
        logger.error("Sheet 'Manuscripts' not found -- aborting.")
        return

    try:
        df_ch = pd.read_excel(EXCEL, sheet_name="Corpus hagio")
    except ValueError:
        logger.warning("Sheet 'Corpus hagio' not found -- primary metadata will be missing.")
        df_ch = pd.DataFrame()

    try:
        df_ed = pd.read_excel(EXCEL, sheet_name="Editions")
    except ValueError:
        logger.warning("Sheet 'Editions' not found -- skipping editions.")
        df_ed = pd.DataFrame()

    # Resolve column names in the Manuscripts sheet
    col_bhl           = df_ms.columns[0]
    col_title         = "Title"
    col_ms_id         = "Unique ID"
    col_collection_id = _find_column(
        df_ms,
        "Unique  identifier per collection",  # double space -- as in source
        "identifier per collection",
    )

    # Shared caches live for the full import transaction
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
