# utilities/model.py
# ---------------------------------------------------------------------------
# Minimal Hagiographies schema — rebuilt from scratch (July 2026) and grown
# incrementally from the June 2026 corpus workbook. The previous 20-table
# model is parked in utilities/legacy_model.py.
#
# Conventions:
#   - Primary key is <table>_id (autoincrement), never plain 'id'.
#   - Every imported field documents its source Excel column via
#     excel_field(), which records the mapping both as a pydantic description
#     and as a PostgreSQL column comment (visible in `\d+` and in Mathesar).
#   - The importer NEVER fixes source data: rows failing strict validation
#     are skipped and reported, not repaired. Two documented, deliberate
#     exceptions: preservation-status labels are matched case-insensitively
#     to Lost/Preserved, and holding-institution names that differ only in
#     case/whitespace are merged into one row (most frequent spelling wins).
# ---------------------------------------------------------------------------

from typing import Any, List, Optional

from sqlmodel import Field, Relationship, SQLModel


def excel_field(excel_column: str, *, sheet: str = "TEXTS", **kwargs: Any) -> Any:
    """A Field mapped from an Excel column.

    Records the mapping as the pydantic description AND as a PostgreSQL
    column comment, so the Excel provenance of every column is visible in
    the database itself.
    """
    note = f"Excel {sheet} → '{excel_column}'"
    kwargs.setdefault("description", note)
    kwargs.setdefault("sa_column_kwargs", {}).setdefault("comment", note)
    return Field(**kwargs)


class TextForm(SQLModel, table=True):
    """Lookup: prose vs verse (distinct values of TEXTS 'Prose or verse')."""

    __tablename__ = "text_form"

    text_form_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field("Prose or verse", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_form")


class TextSourceType(SQLModel, table=True):
    """Lookup: distinct values of TEXTS 'Source type'."""

    __tablename__ = "text_source_type"

    text_source_type_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field("Source type", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_source_type")


class TextSourceSubtype(SQLModel, table=True):
    """Lookup: distinct values of TEXTS 'Subtype'."""

    __tablename__ = "text_source_subtype"

    text_source_subtype_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field("Subtype", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_source_subtype")


class Text(SQLModel, table=True):
    """One row per TEXTS-sheet data row.

    identifier is the given, stable identifier: the 'BHL or NO BHL' prefix
    (spaces → '_') joined with '_' to the stringified 'Unique identifier'
    value, e.g. BHL_29, BHL_1055-1056, NO_BHL_ALPER.
    """

    __tablename__ = "text"

    text_id: Optional[int] = Field(default=None, primary_key=True)
    identifier: str = excel_field(
        "'BHL or NO BHL' + '_' + 'Unique identifier'",
        unique=True,
        index=True,
    )
    title: Optional[str] = excel_field("Title of the work", default=None)
    approximate_token_count: Optional[int] = excel_field(
        "Approximate token count", default=None
    )
    text_form_id: Optional[int] = excel_field(
        "Prose or verse",
        default=None,
        foreign_key="text_form.text_form_id",
    )
    text_source_type_id: Optional[int] = excel_field(
        "Source type",
        default=None,
        foreign_key="text_source_type.text_source_type_id",
    )
    text_source_subtype_id: Optional[int] = excel_field(
        "Subtype",
        default=None,
        foreign_key="text_source_subtype.text_source_subtype_id",
    )

    text_form: Optional[TextForm] = Relationship(back_populates="texts")
    text_source_type: Optional[TextSourceType] = Relationship(back_populates="texts")
    text_source_subtype: Optional[TextSourceSubtype] = Relationship(
        back_populates="texts"
    )


class ManuscriptPreservationStatus(SQLModel, table=True):
    """Lookup: Lost / Preserved.

    Canonicalised case-insensitively from MANUSCRIPTS 'Preservation status of
    manuscript copy' (the workbook mixes 'LOST' and 'Lost').
    """

    __tablename__ = "manuscript_preservation_status"

    manuscript_preservation_status_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    label: str = excel_field(
        "Preservation status of manuscript copy", sheet="MANUSCRIPTS", unique=True
    )

    manuscripts: List["Manuscript"] = Relationship(back_populates="preservation_status")


class ManuscriptHoldingInstitution(SQLModel, table=True):
    """Lookup: deduplicated holding institutions.

    Names that differ only in case/whitespace are merged into one row; the
    most frequent raw spelling in the workbook wins. 'N/A' is not stored
    (those manuscripts get a NULL institution).
    """

    __tablename__ = "manuscript_holding_institution"

    manuscript_holding_institution_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    name: str = excel_field(
        "Manuscript holding institution", sheet="MANUSCRIPTS", unique=True
    )

    manuscripts: List["Manuscript"] = Relationship(back_populates="holding_institution")


class Manuscript(SQLModel, table=True):
    """One row per MANUSCRIPTS-sheet data row (one manuscript copy).

    identifier is the given, stable copy identifier: the 'BHL or NO BHL'
    prefix (spaces → '_') joined with '_' to the 'Manuscript copy unique
    identifier per text' value, e.g. BHL_29-4.
    """

    __tablename__ = "manuscript"

    manuscript_id: Optional[int] = Field(default=None, primary_key=True)
    identifier: str = excel_field(
        "'BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text'",
        sheet="MANUSCRIPTS",
        unique=True,
        index=True,
    )
    title: Optional[str] = excel_field("Title", sheet="MANUSCRIPTS", default=None)
    manuscript_preservation_status_id: Optional[int] = excel_field(
        "Preservation status of manuscript copy",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="manuscript_preservation_status.manuscript_preservation_status_id",
    )
    manuscript_holding_institution_id: Optional[int] = excel_field(
        "Manuscript holding institution",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="manuscript_holding_institution.manuscript_holding_institution_id",
    )

    preservation_status: Optional[ManuscriptPreservationStatus] = Relationship(
        back_populates="manuscripts"
    )
    holding_institution: Optional[ManuscriptHoldingInstitution] = Relationship(
        back_populates="manuscripts"
    )


class Edition(SQLModel, table=True):
    """One row per EDITIONS-sheet data row (basic metadata only for now)."""

    __tablename__ = "edition"

    edition_id: Optional[int] = Field(default=None, primary_key=True)
    title: str = excel_field("Title", sheet="EDITIONS")
    publication_year: Optional[int] = excel_field(
        "Publication year", sheet="EDITIONS", default=None
    )
    reprint: Optional[bool] = excel_field("Reprint ?", sheet="EDITIONS", default=None)
