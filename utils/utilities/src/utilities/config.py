import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent.parent.parent

# load environment variables for development
# in production (docker), env variables are loaded by Docker (.env)
load_dotenv(ROOT / "dev.env")

DB_PATH = Path(os.getenv("DB_PATH", "/data/hagiographies.db"))
DB_STRING = f"sqlite:///{DB_PATH}"

DATA_ROOT = Path(os.getenv("DATA_ROOT", "/data"))
CSV = DATA_ROOT / "hagiographies.csv"
EXCEL = DATA_ROOT / "hagiographies.xlsx"