import json
import logging
from pathlib import Path
from typing import List

from rich.logging import RichHandler
from sqlmodel import create_engine
import sqlalchemy
from sqlalchemy import MetaData, Table, inspect, ForeignKeyConstraint

from utilities.config import ROOT, DATA_ROOT
from utilities.db import engine as source_engine

# Import map export to trigger after sqlite generation
from exporter.export_map import main as export_map_main

handler = RichHandler(rich_tracebacks=True, markup=True, show_time=True, show_path=True)
logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler])
logger = logging.getLogger(__name__)

OUTPUT_DB = DATA_ROOT / "public_hagiographies.db"
FILTER_JSON_PATH = Path(__file__).parent / "filter.json"

def load_filters() -> List[str]:
    if FILTER_JSON_PATH.exists():
        try:
            return json.loads(FILTER_JSON_PATH.read_text())["DropColumns"]
        except Exception as e:
            logger.warning(f"Could not parse filter.json: {e}")
    return []

def main() -> None:
    logger.info("Initializing PG -> SQLite dump...")
    
    # Load columns to drop
    drop_columns = load_filters()
    if drop_columns:
        logger.info(f"Filtering out columns: {drop_columns}")
        
    # Set up SQLite engine
    if OUTPUT_DB.exists():
        logger.info(f"Removing existing {OUTPUT_DB}")
        OUTPUT_DB.unlink()
        
    sqlite_url = f"sqlite:///{OUTPUT_DB}"
    target_engine = create_engine(sqlite_url)

    # Reflect schema from source
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    
    # Prepare target metadata
    target_metadata = MetaData()
    
    # Build schema and copy data
    for table_name, source_table in source_metadata.tables.items():
        logger.info(f"Processing table: {table_name}")
        
        # Copy columns, excluding requested ones and stripping defaults
        columns = []
        for col in source_table.columns:
            if col.name not in drop_columns:
                # Copy column and strip dialect-specific defaults
                new_col = col._copy()
                new_col.server_default = None
                new_col.default = None
                columns.append(new_col)
        
        # Explicitly copy Foreign Key constraints
        # col._copy() usually handles FKs, but we re-add them to be sure and strip schemas
        constraints = []
        for const in source_table.constraints:
            if isinstance(const, sqlalchemy.ForeignKeyConstraint):
                new_const = const._copy()
                # SQLite doesn't use schemas, so we strip 'public.' or similar
                for fk in new_const.elements:
                    if fk.target_fullname and "." in fk.target_fullname:
                        parts = fk.target_fullname.split(".")
                        if len(parts) > 2: # schema.table.column
                            fk.target_fullname = f"{parts[-2]}.{parts[-1]}"
                        # if it's just table.column, it's fine
                constraints.append(new_const)

        target_table = Table(
            table_name,
            target_metadata,
            *(columns + constraints)
        )
        
    # Create tables in target
    target_metadata.create_all(target_engine)
    
    # Copy data using chunks
    with source_engine.connect() as src_conn, target_engine.begin() as tgt_conn:
        for table_name, source_table in source_metadata.tables.items():
            logger.info(f"Copying data for {table_name}...")
            
            target_table = target_metadata.tables[table_name]
            
            # Use chunks
            result = src_conn.execute(source_table.select())
            
            # Get valid keys from the target table to insert
            valid_keys = [c.name for c in target_table.columns]
            
            chunk_size = 5000
            while True:
                chunk = result.fetchmany(chunk_size)
                if not chunk:
                    break
                    
                # Format to dict, excluding drop_columns
                records = []
                for row in chunk:
                    row_dict = row._mapping
                    clean_row = {k: v for k, v in row_dict.items() if k in valid_keys}
                    records.append(clean_row)
                    
                if records:
                    tgt_conn.execute(target_table.insert(), records)
                    
    logger.info(f"Successfully exported data to {OUTPUT_DB}")
    
    logger.info("Triggering map export...")
    try:
        export_map_main()
    except Exception as e:
        logger.error(f"Error during map export: {e}")

if __name__ == "__main__":
    main()
