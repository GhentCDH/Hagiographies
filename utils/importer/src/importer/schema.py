"""Schema (metadata) operations, separate from data import."""

import logging

from sqlalchemy import text as sql
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel

# Importing the model registers the current tables (and only those) on
# SQLModel.metadata. Never import utilities.legacy_model here.
import utilities.model  # noqa: F401

log = logging.getLogger(__name__)


class SchemaGuardError(RuntimeError):
    """Refused to run a destructive operation against this database."""


def create_schema(engine: Engine) -> None:
    """Create the metadata schema (tables, constraints, column comments)."""
    SQLModel.metadata.create_all(engine)
    log.info(
        "created schema (%s)", ", ".join(sorted(SQLModel.metadata.tables))
    )


def drop_public_schema(engine: Engine) -> None:
    """Drop and recreate the research DB's public schema.

    A raw DROP SCHEMA ... CASCADE (rather than metadata.drop_all) so that
    tables from older schema generations are removed too. Mathesar's own
    schemas (msar, mathesar_types, ...) in this database are untouched, and
    the separate mathesar_django metadata database is refused outright.
    """
    database = engine.url.database
    if database == "mathesar_django":
        raise SchemaGuardError(
            "refusing to drop the public schema of mathesar_django "
            "(Mathesar's metadata database)"
        )
    with engine.connect() as connection:
        connection.execute(sql("DROP SCHEMA public CASCADE"))
        connection.execute(sql("CREATE SCHEMA public"))
        connection.commit()
    log.info("dropped and recreated schema 'public' of database %r", database)
