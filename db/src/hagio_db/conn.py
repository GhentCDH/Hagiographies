"""Database connection and paths.

Deliberately independent of utils/utilities: no SQLModel, no ORM, just a
psycopg connection and the same environment variables the rest of the project
uses.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from rich.console import Console

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # the db/ directory
MIGRATIONS = PACKAGE_ROOT / "migrations"
DATA_ROOT = Path(os.getenv("DATA_ROOT", "/data"))
EXCEL = DATA_ROOT / os.getenv("EXCEL_FILE", "corpus_dedup.xlsx")

console = Console()


class ConfigError(RuntimeError):
    """No usable database URL."""


def resolve_url(override: str | None = None) -> str:
    """DATABASE_URL wins, then PG_DATABASE_URL, unless an override is given.

    SQLAlchemy's 'postgresql+psycopg://' prefix is accepted and stripped:
    dev.env is written for the ORM, and we read the same variable.
    """
    url = override or os.getenv("DATABASE_URL") or os.getenv("PG_DATABASE_URL")
    if not url:
        raise ConfigError(
            "no database URL: pass --database-url, or set DATABASE_URL "
            "or PG_DATABASE_URL"
        )
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def describe(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port or 5432}{parts.path}"


def announce(url: str) -> None:
    """Print the target, loudly when it is not the local Docker Postgres."""
    host = urlsplit(url).hostname or ""
    local = host in ("postgres", "localhost", "127.0.0.1", "::1")
    style = "green" if local else "bold red"
    label = "LOCAL" if local else "REMOTE"
    console.print(f"[{style}]{label}[/] database: {describe(url)}")


def connect(url: str, *, read_only: bool = False) -> psycopg.Connection:
    """Open a connection.

    read_only=True puts the *server* in read-only mode, so any accidental
    INSERT/UPDATE/DDL is rejected by PostgreSQL itself rather than merely
    rolled back at the end.
    """
    conn = psycopg.connect(url, connect_timeout=30)
    if read_only:
        conn.read_only = True
    return conn
