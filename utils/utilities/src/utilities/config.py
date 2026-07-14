import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent.parent

# load environment variables for development
# in production (docker), env variables are loaded by Docker (.env)
load_dotenv(ROOT / "dev.env")

# The model and importer target PostgreSQL. DATABASE_URL (set by the just
# recipes from PG_DATABASE_URL) wins; otherwise fall back to PG_DATABASE_URL.
DB_STRING = os.getenv("DATABASE_URL") or os.environ["PG_DATABASE_URL"]

# Pin the psycopg (v3) driver. A bare "postgresql://" URL lets SQLAlchemy pick
# psycopg2, which is not installed; normalise so remote URLs (e.g. from .env)
# that omit the "+psycopg" qualifier still work.
if DB_STRING.startswith("postgresql://"):
    DB_STRING = DB_STRING.replace("postgresql://", "postgresql+psycopg://", 1)

DATA_ROOT = Path(os.getenv("DATA_ROOT", "/data"))
CSV = DATA_ROOT / "hagiographies.csv"
# Source workbook. Override with EXCEL_FILE; defaults to the June 2026 corpus.
EXCEL = DATA_ROOT / os.getenv("EXCEL_FILE", "CORPUS for JOREN SIX 4 June 2026.xlsx")