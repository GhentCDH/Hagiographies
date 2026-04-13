import sqlite3
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, MetaData

# Constants matching export_sqlite.py
DATA_ROOT = Path("/data")
OUTPUT_DB = DATA_ROOT / "public_hagiographies.db"
FILTER_JSON_PATH = Path(__file__).parent.parent / "src" / "exporter" / "filter.json"

@pytest.fixture
def sqlite_conn():
    """Connection to the exported SQLite database."""
    if not OUTPUT_DB.exists():
        pytest.fail(f"Exported database not found at {OUTPUT_DB}. Run 'just export-from-pg-to-sqlite' first.")
    conn = sqlite3.connect(OUTPUT_DB)
    yield conn
    conn.close()

def test_exported_tables_exist(sqlite_conn):
    """Verify that core tables exist in the exported database."""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    
    expected_tables = {"text", "manuscript", "place", "author", "edition"}
    for table in expected_tables:
        assert table in tables, f"Table {table} missing from export."

def test_column_filtering(sqlite_conn):
    """Verify that columns in filter.json are NOT present in the export."""
    if not FILTER_JSON_PATH.exists():
        pytest.skip("filter.json missing, skipping filtering test.")
        
    filters = json.loads(FILTER_JSON_PATH.read_text())
    drop_columns = filters.get("DropColumns", [])
    
    cursor = sqlite_conn.cursor()
    
    # Check all tables for dropped columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = {row[1] for row in cursor.fetchall()}
        
        for dropped in drop_columns:
            assert dropped not in columns, f"Column {dropped} found in table {table} despite filter."

def test_foreign_keys_presence(sqlite_conn):
    """Verify that foreign keys are preserved in the exported schema."""
    cursor = sqlite_conn.cursor()
    
    # Check 'manuscript' table foreign keys
    cursor.execute("PRAGMA foreign_key_list(manuscript);")
    fks = cursor.fetchall()
    
    # Example: manuscript should point to place, institution, etc.
    referenced_tables = {row[2] for row in fks}
    assert "place" in referenced_tables
    assert "institution" in referenced_tables

def test_data_integrity_counts(sqlite_conn):
    """Basic integrity check: ensures main tables are not empty."""
    cursor = sqlite_conn.cursor()
    
    for table in ["text", "manuscript", "place"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        count = cursor.fetchone()[0]
        assert count > 0, f"Table {table} is empty after export."
