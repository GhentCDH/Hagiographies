from datetime import datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel


class Table(SQLModel):
    """Base class with common fields for all tables."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default=None,
        sa_type=DateTime(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default=None,
        sa_type=DateTime(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )


class Entry(Table, table=True):
    """Placeholder model to demonstrate the pattern."""

    name: str
    description: str | None = None
    source: str | None = None
