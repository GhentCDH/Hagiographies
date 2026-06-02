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

# Output path for the derived, publishable SQLite snapshot.
DB_PATH = Path(os.getenv("DB_PATH", "/data/hagiographies.db"))

DATA_ROOT = Path(os.getenv("DATA_ROOT", "/data"))
CSV = DATA_ROOT / "hagiographies.csv"
EXCEL = DATA_ROOT / "hagiographies.xlsx"