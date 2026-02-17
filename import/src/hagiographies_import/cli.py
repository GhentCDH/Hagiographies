import logging
import pandas as pd
from rich.logging import RichHandler
from sqlmodel import SQLModel, Session, select

from .config import EXCEL
from .db import create_updated_at_trigger, engine
from .model import (
    Text, Manuscript, Witness, Edition, EditionManuscriptLink,
    City, Library, Location, Origin, Reference, Provenance
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
    
    # Read Manuscripts sheet with header=0 (Verified)
    try:
        df_ms = pd.read_excel(EXCEL, sheet_name='Manuscripts', header=0)
    except ValueError:
        logger.error("Sheet 'Manuscripts' not found.")
        return

    # Read Editions sheet
    try:
        df_ed = pd.read_excel(EXCEL, sheet_name='Editions')
    except ValueError:
        logger.warning("Sheet 'Editions' not found. Skipping editions.")
        df_ed = pd.DataFrame()

    # Identify columns in Manuscripts
    col_bhl = df_ms.columns[0] # Usually 'Unnamed: 0' or similar if header is empty
    col_title = 'Title'
    col_ms_id = 'Unique ID'
    col_collection_id = 'Unique  identifier per collection'
    
    # Verify columns exist
    if col_collection_id not in df_ms.columns:
        # Fallback search
        for c in df_ms.columns:
            if 'identifier per collection' in str(c):
                col_collection_id = c
                break
    
    logger.info(f"Using columns: BHL='{col_bhl}', MS_ID='{col_ms_id}', Coll_ID='{col_collection_id}'")

    with Session(engine) as session:
        # 1. Create Texts
        logger.info("Processing Texts...")
        existing_texts = {} # map BHL -> Text object
        
        # Caches for lookups to reduce DB hits
        origins_cache = {}

        for index, row in df_ms.iterrows():
            bhl = str(row[col_bhl]).strip()
            # BHL might be float '29.0', convert to '29'
            if bhl.endswith('.0'):
                bhl = bhl[:-2]
                
            title = str(row.get(col_title, '')).strip()
            
            if not bhl or bhl.lower() == 'nan':
                continue
                
            if bhl not in existing_texts:
                origin_name = row.get('Origin')
                origin_id = None
                
                if pd.notna(origin_name):
                    origin_name_str = str(origin_name).strip()
                    if origin_name_str:
                        if origin_name_str not in origins_cache:
                            origin = get_or_create(session, Origin, name=origin_name_str)
                            origins_cache[origin_name_str] = origin
                        origin_id = origins_cache[origin_name_str].id

                text = Text(
                    bhl_number=bhl,
                    title=title,
                    origin_id=origin_id
                )
                session.add(text)
                existing_texts[bhl] = text
        
        session.commit()
        for text in existing_texts.values():
            session.refresh(text)
            
        logger.info(f"Created {len(existing_texts)} Texts.")

        # 2. Create Manuscripts and Witnesses
        logger.info("Processing Manuscripts and Witnesses...")
        existing_manuscripts = {} # map Unique ID (str) -> Manuscript object
        collection_id_map = {} # map Collection ID (str) -> Manuscript object
        
        # Caches
        cities_cache = {}
        libraries_cache = {}
        locations_cache = {} # key: (city_id, library_id, shelfmark)
        provenance_cache = {}

        for index, row in df_ms.iterrows():
            # Manuscript Info
            ms_unique_id = row.get(col_ms_id)
            if pd.isna(ms_unique_id):
                continue
            
            # Normalize MS ID
            try:
                ms_unique_id_str = str(int(ms_unique_id))
            except:
                ms_unique_id_str = str(ms_unique_id).strip()
            
            if ms_unique_id_str not in existing_manuscripts:
                # Handle Location Hierarchy
                city_name = str(row.get('Location', 'Unknown')).strip()
                library_name = str(row.get('Heritage institution', 'Unknown')).strip()
                shelfmark = str(row.get('Shelfmark', 'Unknown')).strip()
                
                # City
                if city_name not in cities_cache:
                    city = get_or_create(session, City, name=city_name)
                    cities_cache[city_name] = city
                city_obj = cities_cache[city_name]
                
                # Library
                if library_name not in libraries_cache:
                    library = get_or_create(session, Library, name=library_name)
                    libraries_cache[library_name] = library
                library_obj = libraries_cache[library_name]
                
                # Location
                loc_key = (city_obj.id, library_obj.id, shelfmark)
                if loc_key not in locations_cache:
                    location = get_or_create(session, Location, city_id=city_obj.id, library_id=library_obj.id, shelfmark=shelfmark)
                    locations_cache[loc_key] = location
                location_obj = locations_cache[loc_key]

                ms = Manuscript(
                    location_id=location_obj.id,
                    iiif_url=None # Currently not in Excel?
                )
                session.add(ms)
                session.flush() 
                session.refresh(ms)
                
                existing_manuscripts[ms_unique_id_str] = ms
                
                # Map collection ID
                coll_id = row.get(col_collection_id)
                if pd.notna(coll_id):
                    coll_id_str = str(coll_id).strip()
                    collection_id_map[coll_id_str] = ms
            
            manuscript = existing_manuscripts[ms_unique_id_str]
            
            # Witness Info
            bhl = str(row[col_bhl]).strip()
            if bhl.endswith('.0'):
                bhl = bhl[:-2]
                
            if bhl in existing_texts:
                text = existing_texts[bhl]
                
                # Provenance
                provenance_name = row.get('Provenance general')
                provenance_id = None
                if pd.notna(provenance_name):
                    prov_str = str(provenance_name).strip()
                    if prov_str:
                        if prov_str not in provenance_cache:
                            prov = get_or_create(session, Provenance, name=prov_str)
                            provenance_cache[prov_str] = prov
                        provenance_id = provenance_cache[prov_str].id

                witness = Witness(
                    text_id=text.id,
                    manuscript_id=manuscript.id,
                    page_range=str(row.get('Folio or page per BHL', '')) if pd.notna(row.get('Folio or page per BHL')) else None,
                    dating=str(row.get('Dating', '')) if pd.notna(row.get('Dating')) else None,
                    provenance_id=provenance_id
                )
                session.add(witness)
        
        session.commit()
        logger.info(f"Created {len(existing_manuscripts)} Manuscripts.")

        # 3. Create Editions
        if not df_ed.empty:
            logger.info("Processing Editions...")
            count = 0
            links_count = 0
            
            # Identify columns in Editions
            col_ed_bhl = 'BHL ' # space?
            if col_ed_bhl not in df_ed.columns:
                col_ed_bhl = 'BHL'
            
            references_cache = {}

            for index, row in df_ed.iterrows():
                bhl = str(row.get(col_ed_bhl, '')).strip()
                if not bhl or bhl.lower() == 'nan':
                     continue
                
                if bhl.endswith('.0'):
                    bhl = bhl[:-2]
                
                text_id = existing_texts[bhl].id if bhl in existing_texts else None
                
                # Title & Ref
                title = row.get('Title', 'Unknown')
                ref_name = row.get('Edition reference')
                year = row.get('Date')
                try:
                    year_int = int(year) if pd.notna(year) else None
                except:
                    year_int = None
                
                # Reference
                reference_id = None
                if pd.notna(ref_name):
                    ref_str = str(ref_name).strip() or "Unknown"
                    if ref_str:
                        if ref_str not in references_cache:
                            reference = get_or_create(session, Reference, title=ref_str)
                            references_cache[ref_str] = reference
                        reference_id = references_cache[ref_str].id
                else:
                    # Handle empty reference if needed, maybe create an 'Unknown' reference?
                    # Or check model if optional? Model says reference_id is Optional.
                    pass 

                edition = Edition(
                    text_id=text_id,
                    title=title,
                    reference_id=reference_id,
                    year=year_int
                )
                session.add(edition)
                session.flush()
                session.refresh(edition)
                
                # Link to Manuscripts using Collection IDs in columns 'MS USED X'
                linked_ms_ids = set()
                for i in range(1, 17):
                    col_name = f'MS USED {i}'
                    if col_name not in df_ed.columns:
                        continue
                        
                    val = row.get(col_name)
                    if pd.notna(val):
                        # val is the Collection ID (e.g. 'Admont 3')
                        coll_id_key = str(val).strip()
                            
                        # Lookup in collection_id_map
                        if coll_id_key in collection_id_map:
                            ms_obj = collection_id_map[coll_id_key]
                            
                            # Prevent duplicates for this edition
                            if ms_obj.id in linked_ms_ids:
                                continue
                                
                            link = EditionManuscriptLink(
                                edition_id=edition.id,
                                manuscript_id=ms_obj.id
                            )
                            session.add(link)
                            linked_ms_ids.add(ms_obj.id)
                            links_count += 1
                count += 1
            
            session.commit()
            logger.info(f"Created {count} Editions with {links_count} links.")

    logger.info("Import complete.")
