import csv
import logging

from rich.logging import RichHandler
from sqlmodel import SQLModel, Session

from .config import CSV
from .db import create_updated_at_trigger, engine
from .model import Entry

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


def main():
    SQLModel.metadata.create_all(engine)
    create_updated_at_trigger(engine)

    if not CSV.exists():
        logger.warning(f"CSV file not found at {CSV}, skipping import.")
        logger.info("Database tables created successfully.")
        return

    with Session(engine) as session:
        with open(CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                entry = Entry(
                    name=row.get("name", ""),
                    description=row.get("description"),
                    source=row.get("source"),
                )
                session.add(entry)

                if i % 100 == 0:
                    logger.info(f"Processed {i} rows...")
                    session.commit()

        session.commit()
        logger.info("Import complete.")
