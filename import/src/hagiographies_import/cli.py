import logging
import pandas as pd
from rich.logging import RichHandler
from sqlmodel import SQLModel, Session, select

from .config import EXCEL
from .db import engine, create_updated_at_trigger
from .model import (
    CorpusHagio, Manuscript, Witness, Edition, EditionManuscriptLink,
    City, Library, Location, Origin, Reference, Provenance, Archbishopric, Bishopric
)

handler = RichHandler(
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    markup=True,
    show_time=True,
    show_path=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[handler],
)

logger = logging.getLogger(__name__)


def safe_float(value):
    """Safely convert a value to float, handling malformed strings and scaling."""
    if pd.isna(value):
        return None
    
    # Pre-process strings
    if isinstance(value, str):
        # Remove commas and normalize multiple dots (e.g. '5.189.84')
        value = value.replace(',', '').strip()
        if not value: return None
        parts = value.split('.')
        if len(parts) > 2:
            value = parts[0] + '.' + ''.join(parts[1:])
    
    try:
        f_val = float(value)
        # Check whether the value is very large and needs scaling
        if abs(f_val) > 10000:  # Threshold for large coordinates
            f_val = f_val / 1000000
        return f_val
    except (ValueError, TypeError):
        return None


def safe_int(value):
    """Safely convert a value to int."""
    if pd.isna(value):
        return None
    try:
        return int(float(value)) if not isinstance(value, str) else int(float(str(value).strip().replace(',', '')))
    except (ValueError, TypeError):
        return None


def safe_bool(value):
    """Safely convert a Y/N or YES/NO string to boolean."""
    if pd.isna(value):
        return None
    s = str(value).strip().upper()
    if s in ('Y', 'YES', 'TRUE', '1', 'T'):
        return True
    if s in ('N', 'NO', 'FALSE', '0', 'F'):
        return False
    return None


def get_or_create(session, model, **kwargs):
    """
    Get an instance of `model` matching `kwargs`, or create it if it doesn't exist.
    """
    statement = select(model).filter_by(**kwargs)
    instance = session.exec(statement).first()
    if instance:
        return instance
    else:
        instance = model(**kwargs)
        session.add(instance)
        session.flush()
        session.refresh(instance)
        return instance


def main():
    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    if not EXCEL.exists():
        logger.warning(f"Excel file not found at {EXCEL}, skipping import.")
        return

    logger.info(f"Reading Excel file: {EXCEL}")
    
    # Read Sheets
    try:
        df_ms = pd.read_excel(EXCEL, sheet_name='Manuscripts', header=0)
    except ValueError:
        logger.error("Sheet 'Manuscripts' not found.")
        return

    try:
        df_ch = pd.read_excel(EXCEL, sheet_name='Corpus hagio')
    except ValueError:
        logger.warning("Sheet 'Corpus hagio' not found. Primary metadata might be missing.")
        df_ch = pd.DataFrame()

    try:
        df_ed = pd.read_excel(EXCEL, sheet_name='Editions')
    except ValueError:
        logger.warning("Sheet 'Editions' not found. Skipping editions.")
        df_ed = pd.DataFrame()

    # Identify columns in Manuscripts
    col_bhl = df_ms.columns[0] 
    col_title = 'Title'
    col_ms_id = 'Unique ID'
    col_collection_id = 'Unique  identifier per collection'
    
    if col_collection_id not in df_ms.columns:
        for c in df_ms.columns:
            if 'identifier per collection' in str(c):
                col_collection_id = c
                break
    
    with Session(engine) as session:
        # Caches
        origins_cache = {}
        archbishoprics_cache = {}
        bishoprics_cache = {}
        existing_texts = {} # map BHL -> CorpusHagio object

        def get_archbishopric_id(name):
            if pd.isna(name): return None
            name_str = str(name).strip()
            if not name_str or name_str.lower() in ('nan', 'n/a', 'none', '-'): return None
            if name_str not in archbishoprics_cache:
                archbishopric = get_or_create(session, Archbishopric, name=name_str)
                archbishoprics_cache[name_str] = archbishopric.id
            return archbishoprics_cache[name_str]

        def get_bishopric_id(name):
            if pd.isna(name): return None
            name_str = str(name).strip()
            if not name_str or name_str.lower() in ('nan', 'n/a', 'none', '-'): return None
            if name_str not in bishoprics_cache:
                bishopric = get_or_create(session, Bishopric, name=name_str)
                bishoprics_cache[name_str] = bishopric.id
            return bishoprics_cache[name_str]

        # 1. Process "Corpus hagio" sheet first (Primary Metadata & Coordinates)
        if not df_ch.empty:
            logger.info("Processing Corpus Hagio sheet...")
            # Detect coordinate columns (NOTE: Swapped in Excel, so we map them correctly here)
            col_lat_org = 'GPS Longitude OR'  # Excel "Longitude" actually has Latitude
            col_lon_org = 'GPS Latitude OR'   # Excel "Latitude" actually has Longitude
            col_lat_des = 'GPS Longitude DES' # Excel "Longitude" actually has Latitude
            col_lon_des = 'GPS Latitude DES'  # Excel "Latitude" actually has Longitude
            col_bhl_ref = 'BHL reference'
            
            for index, row in df_ch.iterrows():
                bhl = str(row.get(col_bhl_ref, '')).strip()
                if bhl.endswith('.0'): bhl = bhl[:-2]
                if not bhl or bhl.lower() == 'nan': continue

                # Origin
                origin_name = row.get('Origin')
                origin_id = None
                if pd.notna(origin_name):
                    name_str = str(origin_name).strip()
                    if name_str:
                        if name_str not in origins_cache:
                            # Use get_or_create but update coordinates if present
                            origin = get_or_create(session, Origin, name=name_str)
                            origin.latitude = safe_float(row.get(col_lat_org))
                            origin.longitude = safe_float(row.get(col_lon_org))
                            origin.archbishopric_id = get_archbishopric_id(row.get('Archbishopric'))
                            origin.bishopric_id = get_bishopric_id(row.get('Bishopric'))
                            origins_cache[name_str] = origin
                        origin_id = origins_cache[name_str].id

                # CorpusHagio entry
                text = get_or_create(session, CorpusHagio, bhl_number=bhl)
                text.title = str(row.get('Title', text.title or 'Unknown')).strip()
                text.author = str(row.get('Author')) if pd.notna(row.get('Author')) else text.author
                text.dating_rough = str(row.get('Rough chronology')) if pd.notna(row.get('Rough chronology')) else text.dating_rough
                text.origin_id = origin_id
                
                text.primary_destinatary = str(row.get('Primary destinatary')) if pd.notna(row.get('Primary destinatary')) else None
                text.destinatary_latitude = safe_float(row.get(col_lat_des))
                text.destinatary_longitude = safe_float(row.get(col_lon_des))
                
                # New metadata
                text.approx_length = safe_int(row.get('Approx. length in words'))
                text.archbishopric_id = get_archbishopric_id(row.get('Archbishopric'))
                text.bishopric_id = get_bishopric_id(row.get('Bishopric'))
                text.source_type = str(row.get('Source type')) if pd.notna(row.get('Source type')) else None
                text.subtype = str(row.get('Subtype')) if pd.notna(row.get('Subtype')) else None
                text.prose_verse = str(row.get('Mainly prose or verse')) if pd.notna(row.get('Mainly prose or verse')) else None
                text.is_reecriture = safe_bool(row.get('Réécriture?'))
                text.ocr_status = str(row.get('Cleaned?')) if pd.notna(row.get('Cleaned?')) else None
                text.notes = str(row.get('Notes')) if pd.notna(row.get('Notes')) else None
                
                session.add(text)
                existing_texts[bhl] = text
            
            session.commit()
            logger.info(f"Processed {len(existing_texts)} entries from Corpus hagio.")

        # 2. Process Manuscripts (and backfill Texts not in Corpus hagio sheet)
        logger.info("Processing Manuscripts...")
        existing_manuscripts = {}
        collection_id_map = {}
        cities_cache = {}
        libraries_cache = {}
        locations_cache = {}
        provenance_cache = {}

        for index, row in df_ms.iterrows():
            bhl = str(row[col_bhl]).strip()
            if bhl.endswith('.0'): bhl = bhl[:-2]
            if not bhl or bhl.lower() == 'nan': continue
            
            # Backfill if missing
            if bhl not in existing_texts:
                origin_name = row.get('Origin')
                origin_id = None
                if pd.notna(origin_name):
                    name_str = str(origin_name).strip()
                    if name_str:
                        if name_str not in origins_cache:
                            origins_cache[name_str] = get_or_create(session, Origin, name=name_str)
                        origin_id = origins_cache[name_str].id
                
                text = get_or_create(session, CorpusHagio, bhl_number=bhl)
                text.title = str(row.get(col_title, text.title or 'Unknown')).strip()
                text.origin_id = origin_id
                session.add(text)
                existing_texts[bhl] = text

            ms_unique_id = row.get(col_ms_id)
            if pd.isna(ms_unique_id): continue
            
            # Clean Unique ID: remove (lost) or (lost?)
            ms_unique_id_str = str(ms_unique_id).strip()
            if '(' in ms_unique_id_str:
                ms_unique_id_str = ms_unique_id_str.split('(')[0].strip()
            
            # Normalize numeric IDs (like '6318.0' -> '6318')
            if ms_unique_id_str.endswith('.0'):
                ms_unique_id_str = ms_unique_id_str[:-2]
            
            if ms_unique_id_str not in existing_manuscripts:
                city_name = str(row.get('Location', 'Unknown')).strip()
                library_name = str(row.get('Heritage institution', 'Unknown')).strip()
                shelfmark = str(row.get('Shelfmark', 'Unknown')).strip()
                
                city = cities_cache.get(city_name) or get_or_create(session, City, name=city_name)
                cities_cache[city_name] = city
                
                library = libraries_cache.get(library_name) or get_or_create(session, Library, name=library_name)
                libraries_cache[library_name] = library
                
                loc_key = (city.id, library.id, shelfmark)
                location = locations_cache.get(loc_key) or get_or_create(session, Location, city_id=city.id, library_id=library.id, shelfmark=shelfmark)
                locations_cache[loc_key] = location

                ms = Manuscript(location_id=location.id, unique_id=ms_unique_id_str)
                ms.preservation_status = str(row.get('Preservation status')) if pd.notna(row.get('Preservation status')) else None
                ms.vernacular_region = str(row.get('Vernacular region (Romance/Germanic)')) if pd.notna(row.get('Vernacular region (Romance/Germanic)')) else None
                ms.catalog_link = str(row.get('Online catalogue link')) if pd.notna(row.get('Online catalogue link')) else None
                ms.manuscript_type = str(row.get('Manuscript type')) if pd.notna(row.get('Manuscript type')) else None
                ms.height = safe_float(row.get('Height'))
                ms.width = safe_float(row.get('Width'))
                ms.iiif_url = str(row.get('Link to images')) if pd.notna(row.get('Link to images')) else None
                
                session.add(ms)
                session.flush()
                existing_manuscripts[ms_unique_id_str] = ms
                
                coll_id = row.get(col_collection_id)
                if pd.notna(coll_id):
                    collection_id_map[str(coll_id).strip()] = ms
            
            manuscript = existing_manuscripts[ms_unique_id_str]
            text = existing_texts[bhl]
            
            provenance_name = row.get('Provenance general')
            prov_id = None
            if pd.notna(provenance_name):
                p_str = str(provenance_name).strip()
                if p_str:
                    prov = provenance_cache.get(p_str) or get_or_create(session, Provenance, name=p_str)
                    provenance_cache[p_str] = prov
                    prov_id = prov.id

            witness = Witness(
                text_id=text.id,
                manuscript_id=manuscript.id,
                page_range=str(row.get('Folio or page per BHL', '')) if pd.notna(row.get('Folio or page per BHL')) else None,
                dating=str(row.get('Dating', '')) if pd.notna(row.get('Dating')) else None,
                provenance_id=prov_id,
                archbishopric_id=get_archbishopric_id(row.get('Archbishopric')),
                bishopric_id=get_bishopric_id(row.get('Bishopric')),
                dating_century=str(row.get('Dating by (earliest) century')) if pd.notna(row.get('Dating by (earliest) century')) else None,
                dating_range_start=safe_int(row.get('Dating range start')),
                dating_range_end=safe_int(row.get('Dating range end'))
            )
            session.add(witness)
        
        session.commit()

        # 3. Create Editions
        if not df_ed.empty:
            logger.info("Processing Editions...")
            col_ed_bhl = 'BHL' if 'BHL' in df_ed.columns else 'BHL '
            references_cache = {}

            for index, row in df_ed.iterrows():
                bhl = str(row.get(col_ed_bhl, '')).strip()
                if bhl.endswith('.0'): bhl = bhl[:-2]
                if not bhl or bhl.lower() == 'nan' or bhl not in existing_texts: continue
                
                ref_name = row.get('Edition reference')
                reference_id = None
                if pd.notna(ref_name):
                    r_str = str(ref_name).strip() or "Unknown"
                    ref = references_cache.get(r_str) or get_or_create(session, Reference, title=r_str)
                    references_cache[r_str] = ref
                    reference_id = ref.id
                
                year = row.get('Date')
                try: year_int = int(year) if pd.notna(year) else None
                except: year_int = None

                edition = Edition(
                    text_id=existing_texts[bhl].id,
                    title=str(row.get('Title', 'Unknown')),
                    reference_id=reference_id,
                    year=year_int
                )
                session.add(edition)
                session.flush()
                
                linked_ms_ids = set()
                for i in range(1, 17):
                    val = row.get(f'MS USED {i}')
                    if pd.notna(val):
                        ms_obj = collection_id_map.get(str(val).strip())
                        if ms_obj and ms_obj.id not in linked_ms_ids:
                            session.add(EditionManuscriptLink(edition_id=edition.id, manuscript_id=ms_obj.id))
                            linked_ms_ids.add(ms_obj.id)
            session.commit()

    logger.info("Import complete.")


if __name__ == "__main__":
    main()
