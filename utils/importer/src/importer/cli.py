"""Excel-to-database import pipeline for the Hagiographies project."""

import logging
import re
from typing import Optional, Tuple, Type, Any
from collections import Counter

import pandas as pd
import openpyxl
from rich.logging import RichHandler
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, select

from utilities.config import EXCEL
from utilities.db import engine, create_updated_at_trigger
from utilities.model import (
    Text, Manuscript, Witness, Edition, EditionManuscriptLink,
    City, Library, Location, Origin, Reference, Provenance,
    Archbishopric, Bishopric, Author, DatingRough, Subtype, Destinatary,
    ProseVerse, SourceType, PreservationStatus, VernacularRegion,
    ManuscriptType, ImageAvailability, ManuscriptRelation,
    ExternalResource, ManuscriptImage
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

handler = RichHandler(rich_tracebacks=True, markup=True, show_time=True)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])
logger = logging.getLogger(__name__)

Cache = dict[str, int]

# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------

def dedup_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename duplicate column names in-place so that row.get(col) always
    returns a scalar rather than a Series.

    The first occurrence keeps its original name; subsequent duplicates
    become '<name>.dup1', '<name>.dup2', etc.

    Example: two columns named 'BHL' → 'BHL', 'BHL.dup1'
    """
    seen: dict[str, int] = {}
    new_cols = []
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}.dup{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    df.columns = new_cols
    return df


# ---------------------------------------------------------------------------
# Safe-conversion & cleaning helpers
# ---------------------------------------------------------------------------

def _scalar(value: Any) -> Any:
    """
    If *value* is a pandas Series (happens when a DataFrame has duplicate
    column names and you call row.get(col)), return its first element.
    This prevents downstream pd.isna() / str() calls from crashing.
    """
    if isinstance(value, pd.Series):
        return value.iloc[0] if len(value) > 0 else None
    return value


def safe_str(value: Any) -> Optional[str]:
    value = _scalar(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def safe_int(value: Any) -> Optional[int]:
    value = _scalar(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (ValueError, TypeError):
        return None


def safe_bool(value: Any) -> Optional[bool]:
    value = _scalar(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip().upper()
    if s in ("Y", "YES", "TRUE", "1", "T"):
        return True
    if s in ("N", "NO", "FALSE", "0", "F"):
        return False
    return None


def safe_float(value: Any) -> Optional[float]:
    value = _scalar(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    raw = str(value).replace(",", "").strip()
    parts = raw.split(".")
    if len(parts) > 2:
        raw = parts[0] + "." + "".join(parts[1:])
    try:
        return float(raw)
    except ValueError:
        return None


def safe_coordinate(value: Any, *, lo: float, hi: float) -> Optional[float]:
    f = safe_float(value)
    if f is None:
        return None
    if abs(f) > abs(hi) * 1000:
        f /= 1_000_000
    return f if lo <= f <= hi else None


def safe_latitude(value: Any) -> Optional[float]:
    return safe_coordinate(value, lo=-90.0, hi=90.0)


def safe_longitude(value: Any) -> Optional[float]:
    return safe_coordinate(value, lo=-180.0, hi=180.0)


def clean_id(raw: Any) -> Optional[str]:
    """
    Normalize an identifier cell:
    - Coerce to scalar if a Series (duplicate-column guard)
    - Strip trailing '.0' from float-formatted integers
    - Do NOT strip parenthetical suffixes here; use normalize_ms_ref for that
    """
    raw = _scalar(raw)
    try:
        if pd.isna(raw):
            return None
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if s and s.lower() not in ("nan", "n/a", "none", "-") else None


# ---------------------------------------------------------------------------
# MS USED cell normaliser
# ---------------------------------------------------------------------------

_UNCERTAIN_RE = re.compile(r"\s*\(\?\)\s*$")


def normalize_ms_ref(raw: Any) -> tuple[Optional[str], bool]:
    """
    Clean a value from an 'MS USED X' cell for matching against the
    'Unique identifier per collection' column (col L of Manuscripts sheet).

    Returns (normalised_key, is_uncertain).

    Rules
    -----
    * Coerce Series → scalar.
    * Strip surrounding whitespace.
    * Trailing '(?)' → is_uncertain=True, marker removed.
    * Other parenthetical content kept intact: 'Brussels KBR 74 (70)' stays.
    * Returns (None, False) for empty / N/A / LOST / bare '?' values.
    """
    raw = _scalar(raw)
    try:
        if pd.isna(raw):
            return None, False
    except (TypeError, ValueError):
        pass
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "n/a", "none", "-", "?"):
        return None, False
    if s.upper().startswith("LOST"):
        return None, False
    is_uncertain = bool(_UNCERTAIN_RE.search(s))
    s = _UNCERTAIN_RE.sub("", s).strip()
    return (s if s else None), is_uncertain


# ---------------------------------------------------------------------------
# Dating parser
# ---------------------------------------------------------------------------

def parse_dating(raw: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    if not raw:
        return None, None, None
    s = str(raw).strip()
    if s.lower() in ("nan", "n/a", "none", "-", ""):
        return None, None, None
    return None, None, s


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create(session: Session, model: Type, **kwargs) -> Any:
    """
    Fetch or insert a row.  Uses a savepoint (begin_nested) so that a
    constraint violation never poisons the outer transaction.
    """
    instance = session.exec(select(model).filter_by(**kwargs)).first()
    if instance:
        return instance
    try:
        with session.begin_nested():
            instance = model(**kwargs)
            session.add(instance)
            session.flush()
        session.refresh(instance)
        return instance
    except IntegrityError:
        return session.exec(select(model).filter_by(**kwargs)).first()


def get_or_create_lookup(
    session: Session,
    model: Type,
    cache: Cache,
    raw_value: Any,
    field_name: str = "name",
) -> Optional[int]:
    val = safe_str(raw_value)
    if not val or val.lower() in ("nan", "n/a", "none", "-"):
        return None
    if val not in cache:
        obj = get_or_create(session, model, **{field_name: val})
        if obj:
            cache[val] = obj.id
    return cache.get(val)


# ---------------------------------------------------------------------------
# Hyperlink extraction
# ---------------------------------------------------------------------------

def _extract_hyperlinks_openpyxl(
    filepath: str,
    sheet_name: str,
    df: pd.DataFrame,
    columns_to_check: list,
) -> pd.DataFrame:
    logger.info("Extracting hidden hyperlinks from '%s'...", sheet_name)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    if sheet_name not in wb.sheetnames:
        return df

    ws = wb[sheet_name]
    header_row = [str(cell.value).strip() if cell.value else "" for cell in ws[1]]
    col_indices = {
        col: header_row.index(col) + 1
        for col in columns_to_check
        if col in header_row
    }

    for row_idx in range(len(df)):
        xl_row = row_idx + 2
        for col_name, col_idx in col_indices.items():
            cell = ws.cell(row=xl_row, column=col_idx)
            val = str(cell.value).strip() if cell.value else ""
            is_generic = val.lower() in ("link", "check", "nan", "none", "")

            if cell.hyperlink and cell.hyperlink.target:
                df.at[row_idx, col_name + "_URL"] = cell.hyperlink.target
                df.at[row_idx, col_name + "_COMMENT"] = val if not is_generic else None
            elif val.startswith("http"):
                df.at[row_idx, col_name + "_URL"] = val
                df.at[row_idx, col_name + "_COMMENT"] = None
            else:
                df.at[row_idx, col_name + "_URL"] = None
                df.at[row_idx, col_name + "_COMMENT"] = (
                    safe_str(cell.value) if not is_generic else None
                )
    wb.close()
    return df


# ---------------------------------------------------------------------------
# Sheet processors
# ---------------------------------------------------------------------------

def _process_text(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    origins_cache: dict,
    archbishoprics_cache: Cache,
    bishoprics_cache: Cache,
) -> None:
    col_bhl_ch = df.columns[0]  # first column is always the BHL reference

    for _, row in df.iterrows():
        bhl = clean_id(row.get(col_bhl_ch))
        if not bhl:
            continue

        text = get_or_create(session, Text, bhl_number=bhl)
        if not text:
            continue

        text.title = safe_str(row.get("Title")) or text.title or "Unknown"
        text.is_reecriture = safe_bool(row.get("Réécriture?"))
        text.notes = safe_str(row.get("Notes"))

        try:
            with session.begin_nested():
                session.add(text)
                session.flush()
            existing_texts[bhl] = text
        except IntegrityError:
            pass

    session.commit()
    logger.info("Processed %d entries from Corpus hagio (Text).", len(existing_texts))


def _process_manuscripts(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    origins_cache: dict,
    archbishoprics_cache: Cache,
    bishoprics_cache: Cache,
    col_bhl: str,
) -> tuple[dict, dict]:
    """
    Returns
    -------
    ms_lookup_by_linking_id   : {'29-1' → Manuscript}   (MS N° per BHL number)
    ms_lookup_by_collection_id: {'Paris BN 8' → Manuscript}  (Unique identifier per collection)
    """
    existing_manuscripts: dict[str, Manuscript] = {}
    ms_lookup_by_linking_id: dict[str, Manuscript] = {}
    ms_lookup_by_collection_id: dict[str, Manuscript] = {}

    cities_cache: dict = {}
    libraries_cache: dict = {}
    locations_cache: dict = {}

    # ------------------------------------------------------------------ Pass 1
    for _, row in df.iterrows():
        bhl = clean_id(row.get(col_bhl))
        if not bhl:
            continue

        # Ensure corresponding Text exists
        if bhl not in existing_texts:
            text = get_or_create(session, Text, bhl_number=bhl)
            if text:
                text.title = safe_str(row.get("Title")) or text.title or "Unknown"
                try:
                    with session.begin_nested():
                        session.add(text)
                        session.flush()
                    existing_texts[bhl] = text
                except IntegrityError:
                    pass

        ms_unique_id = clean_id(row.get("Unique ID"))
        if not ms_unique_id:
            continue

        # '29-1' style identifier
        linking_id = clean_id(row.get("MS N° per BHL number"))

        # Create Manuscript if new
        if ms_unique_id not in existing_manuscripts:
            city_name    = safe_str(row.get("Location")) or "Unknown"
            library_name = safe_str(row.get("Heritage institution")) or "Unknown"
            shelfmark    = safe_str(row.get("Shelfmark")) or "Unknown"

            city     = cities_cache.setdefault(city_name, get_or_create(session, City, name=city_name))
            library  = libraries_cache.setdefault(library_name, get_or_create(session, Library, name=library_name))
            loc_key  = (city.id, library.id, shelfmark)
            location = locations_cache.setdefault(
                loc_key,
                get_or_create(session, Location, city_id=city.id, library_id=library.id, shelfmark=shelfmark),
            )

            ms = get_or_create(session, Manuscript, unique_id=ms_unique_id, location_id=location.id)
            if ms:
                ms.title = safe_str(row.get("Title"))
                try:
                    with session.begin_nested():
                        session.add(ms)
                        session.flush()
                    session.refresh(ms)
                except IntegrityError:
                    ms = session.exec(select(Manuscript).filter_by(unique_id=ms_unique_id)).first()

                if ms:
                    existing_manuscripts[ms_unique_id] = ms

        ms_obj = existing_manuscripts.get(ms_unique_id)

        # Populate lookup dictionaries
        if ms_obj:
            if linking_id:
                ms_lookup_by_linking_id[linking_id] = ms_obj

            # ------------------------------------------------------------------
            # KEY FIX: index by 'Unique identifier per collection' (col L).
            # This is the value that 'MS USED X' cells in the Editions sheet
            # reference (e.g. 'Paris BN 8', 'Brussels KBR 30').
            # ------------------------------------------------------------------
            collection_id = safe_str(row.get("Unique  identifier per collection"))
            if collection_id:
                ms_lookup_by_collection_id[collection_id.strip()] = ms_obj

        # Create Witness
        text = existing_texts.get(bhl)
        if ms_obj and text:
            witness = get_or_create(session, Witness, text_id=text.id, manuscript_id=ms_obj.id)
            if witness:
                witness.ms_number_per_bhl = linking_id
                try:
                    with session.begin_nested():
                        session.add(witness)
                        session.flush()
                except IntegrityError:
                    pass

    # ------------------------------------------------------------------ Pass 2
    relations_created = 0
    for _, row in df.iterrows():
        linking_id = clean_id(row.get("MS N° per BHL number"))
        if not linking_id:
            continue
        ms_obj = ms_lookup_by_linking_id.get(linking_id)
        if not ms_obj:
            continue

        certainty = "certain" if safe_bool(row.get("Certain?")) else "uncertain"

        for col_tmpl in [
            "Copy of which first exemplar?",
            "Copy of which second exemplar?",
            "Copy of which third exemplar?",
        ]:
            target_id = clean_id(row.get(col_tmpl))
            if target_id and target_id in ms_lookup_by_linking_id:
                get_or_create(
                    session, ManuscriptRelation,
                    source_manuscript_id=ms_obj.id,
                    target_manuscript_id=ms_lookup_by_linking_id[target_id].id,
                    relation_type="copy_of",
                    certainty=certainty,
                    source_reference="Excel import",
                )
                relations_created += 1

        for i in range(1, 5):
            source_id = clean_id(row.get(f"Exemplar of which manuscript ({i})?"))
            if source_id and source_id in ms_lookup_by_linking_id:
                get_or_create(
                    session, ManuscriptRelation,
                    source_manuscript_id=ms_lookup_by_linking_id[source_id].id,
                    target_manuscript_id=ms_obj.id,
                    relation_type="copy_of",
                    certainty=certainty,
                    source_reference="Excel import",
                )
                relations_created += 1

    session.commit()
    logger.info(
        "Processed %d manuscripts and %d MS-relations. "
        "Collection-ID lookup has %d keys.",
        len(existing_manuscripts), relations_created, len(ms_lookup_by_collection_id),
    )
    return ms_lookup_by_linking_id, ms_lookup_by_collection_id


def _process_editions(
    df: pd.DataFrame,
    session: Session,
    existing_texts: dict,
    ms_lookup_by_collection_id: dict,
) -> None:
    """
    Process the Editions sheet.

    Column mapping (after dedup_columns() in main())
    -------------------------------------------------
    'BHL'                              → col A: BHL number  (first occurrence kept)
    'BHL.dup1'                         → col D: Y/N repertory flag (renamed duplicate)
    'Ed. reference per individual text'→ col C: unique per-text edition ID e.g. '4046-E'
    'MS USED 1' … 'MS USED 16'        → col W–AL: 'Unique identifier per collection' refs

    The 'MS USED X' values are matched against ms_lookup_by_collection_id, which
    is keyed on column L of the Manuscripts sheet.
    """
    # ---------------------------------------------------------------- Diagnostics
    logger.info(
        "Starting editions import. MS collection-ID lookup has %d entries.",
        len(ms_lookup_by_collection_id),
    )
    if len(ms_lookup_by_collection_id) == 0:
        logger.warning(
            "ms_lookup_by_collection_id is EMPTY — no Edition→Manuscript links "
            "will be created. Check that _process_manuscripts ran correctly."
        )

    references_cache: dict[str, Reference] = {}
    editions_cache: dict[str, Edition] = {}   # unique_ed_id → Edition

    editions_created = 0
    links_created = 0
    uncertain_links = 0
    ms_miss_count = 0

    for row_idx, (_, row) in enumerate(df.iterrows()):
        # ---------------------------------------------------------------- Parse row
        bhl_raw   = clean_id(row.get("BHL"))          # scalar after dedup_columns()
        ref_name  = safe_str(row.get("Edition reference"))
        title     = safe_str(row.get("Title"))
        unique_ed = safe_str(row.get("Ed. reference per individual text"))

        if not ref_name and not title:
            continue

        # ---------------------------------------------------------- Resolve Text FK
        text_id: Optional[int] = None
        if bhl_raw and bhl_raw in existing_texts:
            text_id = existing_texts[bhl_raw].id
        # Missing text_id is non-fatal (FK is nullable)

        # ------------------------------------------------------- Resolve Reference
        ref: Optional[Reference] = None
        if ref_name:
            if ref_name not in references_cache:
                references_cache[ref_name] = get_or_create(session, Reference, title=ref_name)
            ref = references_cache[ref_name]

        # --------------------------------------------------------- Resolve Edition
        edition: Optional[Edition] = None

        if unique_ed:
            # 1. In-memory cache first (avoids repeated SELECT)
            edition = editions_cache.get(unique_ed)
            # 2. Database lookup
            if edition is None:
                edition = session.exec(
                    select(Edition).where(Edition.unique_ed_id == unique_ed)
                ).first()

        if edition is None:
            # 3. Create new edition inside a savepoint
            try:
                new_ed = Edition(
                    unique_ed_id=unique_ed,
                    text_id=text_id,
                    reference_id=ref.id if ref else None,
                    title=title,
                    year=safe_int(row.get("Date")),
                    pages=safe_str(row.get("Pages")),
                    unique_id_per_volume=safe_str(
                        row.get("Unique  identifier per edition + volume")
                    ),
                    link_format=safe_str(row.get("Link format")),
                    dg=safe_bool(row.get("DG")),
                    naso=safe_bool(row.get("NASO")),
                    isb=safe_bool(row.get("ISB")),
                    ed_sec=safe_bool(row.get("ED/SEC")),
                    transcribed=safe_bool(row.get("Transcribed?")),
                    our_transcribed_ed=safe_bool(row.get("Our transcribed ed.?")),
                    collation_done=safe_bool(row.get("Collation done?")),
                    is_reprint=(
                        None
                        if safe_str(row.get("Reprint?")) in ("NO", "N/A", None)
                        else safe_bool(row.get("Reprint?"))
                    ),
                    reprint_of=safe_str(row.get("If reprint, of what?")),
                    notes=safe_str(row.get("Notes")),
                )
                with session.begin_nested():
                    session.add(new_ed)
                    session.flush()
                session.refresh(new_ed)
                edition = new_ed
                editions_created += 1
                if unique_ed:
                    editions_cache[unique_ed] = edition
            except Exception as exc:
                logger.warning(
                    "Row %d: failed to create Edition "
                    "(unique_ed=%r, bhl=%r, ref=%r): %s: %s",
                    row_idx, unique_ed, bhl_raw,
                    ref_name[:40] if ref_name else None,
                    type(exc).__name__, exc,
                )
                continue
        else:
            # Edition already in DB: cache it; optionally fill in missing title
            if unique_ed and unique_ed not in editions_cache:
                editions_cache[unique_ed] = edition
            if not edition.title and title:
                edition.title = title
                try:
                    with session.begin_nested():
                        session.add(edition)
                        session.flush()
                except Exception:
                    pass

        if edition is None or edition.id is None:
            logger.warning(
                "Row %d: edition has no id after create/fetch — skipping MS links.",
                row_idx,
            )
            continue

        # ------------------------------------------------------ Link Manuscripts
        linked_ms_ids: set[int] = set()

        for i in range(1, 20):
            col_name = f"MS USED {i}"
            if col_name not in df.columns:
                break  # columns are contiguous

            norm_key, is_uncertain = normalize_ms_ref(row.get(col_name))
            if not norm_key:
                continue

            ms_obj = ms_lookup_by_collection_id.get(norm_key)
            if ms_obj is None:
                ms_miss_count += 1
                logger.debug(
                    "Row %d MS USED miss: %r (raw=%r)",
                    row_idx, norm_key, row.get(col_name),
                )
                continue

            if ms_obj.id in linked_ms_ids:
                continue  # already linked this manuscript to this edition

            try:
                link = get_or_create(
                    session, EditionManuscriptLink,
                    edition_id=edition.id,
                    manuscript_id=ms_obj.id,
                )
                if link and is_uncertain and not link.uncertain:
                    link.uncertain = True
                    try:
                        with session.begin_nested():
                            session.add(link)
                            session.flush()
                    except Exception:
                        pass
                linked_ms_ids.add(ms_obj.id)
                links_created += 1
                if is_uncertain:
                    uncertain_links += 1
            except Exception as exc:
                logger.warning(
                    "Row %d: failed to link MS %r to edition %r: %s",
                    row_idx, norm_key, unique_ed, exc,
                )

    session.commit()
    logger.info(
        "Editions processed: %d editions created, %d MS links (%d uncertain). "
        "%d MS USED values had no matching manuscript.",
        editions_created, links_created, uncertain_links, ms_miss_count,
    )


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

    # ---------------------------------------------------------------- Manuscripts
    try:
        df_ms = pd.read_excel(EXCEL, sheet_name="Manuscripts", header=0)
        df_ms.columns = df_ms.columns.astype(str).str.strip()
        df_ms = dedup_columns(df_ms)
        df_ms = _extract_hyperlinks_openpyxl(
            EXCEL, "Manuscripts", df_ms,
            ["Online catalogue link", "Bollandist catalogue link",
             "Other relevant catalogue link", "Link to images"],
        )
    except ValueError:
        logger.error("Sheet 'Manuscripts' not found — aborting.")
        return

    # ---------------------------------------------------------------- Corpus hagio
    try:
        df_ch = pd.read_excel(EXCEL, sheet_name="Corpus hagio")
        df_ch.columns = df_ch.columns.astype(str).str.strip()
        df_ch = dedup_columns(df_ch)
    except ValueError:
        df_ch = pd.DataFrame()

    # ---------------------------------------------------------------- Editions
    try:
        df_ed = pd.read_excel(EXCEL, sheet_name="Editions", header=0)
        df_ed.columns = df_ed.columns.astype(str).str.strip()
        # CRITICAL: Editions sheet has two columns both called 'BHL':
        #   col A = BHL number (the actual identifier we need)
        #   col D = Y/N repertory flag
        # Without deduplication, row.get('BHL') returns a pandas Series
        # instead of a scalar, causing clean_id() to crash on every row.
        df_ed = dedup_columns(df_ed)
        dupe_report = {c: n for c, n in Counter(df_ed.columns).items() if "dup" in c}
        if dupe_report:
            logger.info("Deduplicated Editions columns: %s", dupe_report)
    except ValueError:
        df_ed = pd.DataFrame()

    # Column A of Manuscripts is the BHL number (unnamed in the header row)
    col_bhl_ms = df_ms.columns[0]

    origins_cache: dict = {}
    archbishoprics_cache: Cache = {}
    bishoprics_cache: Cache = {}
    existing_texts: dict = {}

    with Session(engine) as session:
        if not df_ch.empty:
            logger.info("Processing Corpus Hagio sheet...")
            _process_text(
                df_ch, session, existing_texts,
                origins_cache, archbishoprics_cache, bishoprics_cache,
            )

        logger.info("Processing Manuscripts sheet...")
        ms_lookup_by_linking_id, ms_lookup_by_collection_id = _process_manuscripts(
            df_ms, session, existing_texts,
            origins_cache, archbishoprics_cache, bishoprics_cache,
            col_bhl_ms,
        )

        if not df_ed.empty:
            logger.info("Processing Editions sheet...")
            _process_editions(
                df_ed, session, existing_texts, ms_lookup_by_collection_id,
            )

    logger.info("Import complete.")


if __name__ == "__main__":
    main()