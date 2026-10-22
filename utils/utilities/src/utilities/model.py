# utilities/model.py
# ---------------------------------------------------------------------------
# Minimal Hagiographies schema — rebuilt from scratch (July 2026) and grown
# incrementally from the June 2026 corpus workbook.
#
# Conventions:
#   - Primary key is <table>_id (autoincrement), never plain 'id'.
#   - Every imported field documents its source Excel column via
#     excel_field(), which records the mapping both as a pydantic description
#     and as a PostgreSQL column comment (visible in `\d+` and in Mathesar).
#   - The one-off Excel import (July 2026, since removed) loaded the initial
#     data; the PostgreSQL database, curated in Mathesar, is now the source
#     of truth. Docstrings mentioning the importer describe that initial load.
#   - This model mirrors the public schema after db/migrations/ 000–062
#     (codex/publication split, hoisted and dropped columns). The migrations
#     are the source of truth: every new migration that touches public must
#     update this file in the same change, so `just db_diagram` stays current.
#   - The url columns (codex_link_url, manuscript_link_url, edition_link_url,
#     text__repertory_url) are
#     the mathesar_types.uri domain on QAS/PRD (migrations 004–006, applied
#     only where Mathesar is installed); the model declares them as text.
# ---------------------------------------------------------------------------

from typing import Any, List, Optional

from sqlalchemy import Text as SAText
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy import text as sql_text
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


def unique_identifier_rules(table: str) -> tuple:
    """Constraints making <table>_unique_identifier unique regardless of case
    and surrounding spaces (migrations 053-056): no leading/trailing spaces,
    and a unique index on lower(). The exact UNIQUE constraint comes from the
    field's unique=True."""
    column = f"{table}_unique_identifier"
    return (
        CheckConstraint(f"{column} = btrim({column})", name=f"{table}_{column}_check"),
        Index(f"{table}_{column}_lower_key", sql_text(f"lower({column})"), unique=True),
    )


class TextForm(SQLModel, table=True):
    """Lookup: prose vs verse (distinct values of TEXTS 'Prose or verse')."""

    __tablename__ = "text_form"

    text_form_id: Optional[int] = Field(default=None, primary_key=True)
    text_form: str = excel_field("Prose or verse", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_form")


class TextSourceType(SQLModel, table=True):
    """Lookup: distinct values of TEXTS 'Source type'."""

    __tablename__ = "text_source_type"

    text_source_type_id: Optional[int] = Field(default=None, primary_key=True)
    text_source_type: str = excel_field("Source type", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_source_type")


class TextSourceSubtype(SQLModel, table=True):
    """Lookup: distinct values of TEXTS 'Subtype'."""

    __tablename__ = "text_source_subtype"

    text_source_subtype_id: Optional[int] = Field(default=None, primary_key=True)
    text_source_subtype: str = excel_field("Subtype", unique=True)

    texts: List["Text"] = Relationship(back_populates="text_source_subtype")


class Location(SQLModel, table=True):
    """A geographic point (Western Europe), deduplicated by coordinates.

    Coordinates come from the TEXTS GPS columns, whose headers are SWAPPED
    in the workbook: the 'GPS Longitude' column holds latitude ×10⁶ and the
    'GPS Latitude' column holds longitude ×10⁶. The importer reads them
    swapped and unscaled (documented workbook defect); values outside
    Western Europe (lat 44–56, lon −2–10) are rejected with a warning.
    location_name is the first entity name seen at these coordinates.
    """

    __tablename__ = "location"

    location_id: Optional[int] = Field(default=None, primary_key=True)
    location_name: Optional[str] = Field(default=None)
    # Optional: manuscript locations (MANUSCRIPTS 'Manuscript location') are
    # bare place names created without coordinates.
    location_latitude: Optional[float] = excel_field(
        "… GPS Longitude (sic, swapped) / 1e6", default=None
    )
    location_longitude: Optional[float] = excel_field(
        "… GPS Latitude (sic, swapped) / 1e6", default=None
    )

    archdioceses: List["Archdiocese"] = Relationship(back_populates="location")
    dioceses: List["Diocese"] = Relationship(back_populates="location")
    institutions: List["Institution"] = Relationship(back_populates="location")
    codices: List["Codex"] = Relationship(back_populates="location")


class Archdiocese(SQLModel, table=True):
    """Lookup: archdioceses (no coordinates in the TEXTS sheet yet)."""

    __tablename__ = "archdiocese"

    archdiocese_id: Optional[int] = Field(default=None, primary_key=True)
    archdiocese_name: str = excel_field("Text creation - location by archdiocese", unique=True)
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    archdiocese_note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="archdioceses")
    origin_codices: List["Codex"] = Relationship(
        back_populates="origin_archdiocese"
    )


class Diocese(SQLModel, table=True):
    """Lookup: dioceses (no coordinates in the TEXTS sheet yet)."""

    __tablename__ = "diocese"

    diocese_id: Optional[int] = Field(default=None, primary_key=True)
    diocese_name: str = excel_field("Text creation - location by diocese", unique=True)
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    diocese_note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="dioceses")
    origin_codices: List["Codex"] = Relationship(
        back_populates="origin_diocese"
    )


class Institution(SQLModel, table=True):
    """Lookup: institutions (cloisters, chapters, …), deduplicated by name.

    The location comes from the institution's GPS pair in the TEXTS sheet
    (first occurrence wins; a second, different coordinate pair for the same
    name is reported as a warning).
    """

    __tablename__ = "institution"

    institution_id: Optional[int] = Field(default=None, primary_key=True)
    institution_name: str = excel_field(
        "'Text creation - location by institution' / 'Primary institutional destinatary'",
        unique=True,
    )
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    institution_note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="institutions")
    origin_codices: List["Codex"] = Relationship(
        back_populates="origin_institution",
        sa_relationship_kwargs={"foreign_keys": "Codex.origin_institution_id"},
    )
    provenance_early_codices: List["Codex"] = Relationship(
        back_populates="provenance_early_institute",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.provenance_early_institution_id"
        },
    )
    provenance_later_codices: List["Codex"] = Relationship(
        back_populates="provenance_later_institute",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.provenance_later_institution_id"
        },
    )


class DatingConfidence(SQLModel, table=True):
    """Lookup: dating confidence rating (A/B/C/D)."""

    __tablename__ = "dating_confidence"

    dating_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    dating_confidence: str = excel_field("Dating confidence rating", unique=True)
    dating_confidence_note: Optional[str] = Field(default=None)

    texts: List["Text"] = Relationship(back_populates="dating_confidence")
    codices: List["Codex"] = Relationship(back_populates="dating_confidence")


class AuthorMilieu(SQLModel, table=True):
    """Lookup: author milieu (Monastic, Clerical; 'Unknown' becomes NULL)."""

    __tablename__ = "author_milieu"

    author_milieu_id: Optional[int] = Field(default=None, primary_key=True)
    author_milieu: str = excel_field("Author milieu", unique=True)
    author_milieu_note: Optional[str] = Field(default=None)

    authors: List["Author"] = Relationship(back_populates="milieu")


class Author(SQLModel, table=True):
    """An author, deduplicated by name.

    Anonymous authors ('Anon…' in the workbook) get one row per text, named
    'Anonymous ' + text.identifier (e.g. 'Anonymous BHL_767'), with the raw
    workbook value kept in note (e.g. 'Anon. (same author as BHL 1290)').
    """

    __tablename__ = "author"

    author_id: Optional[int] = Field(default=None, primary_key=True)
    author_name: str = excel_field("Author of the text", unique=True)
    author_institutional_training_ground: Optional[str] = excel_field(
        "Institutional training ground of the author", default=None
    )
    author_regional_antecedents: Optional[str] = excel_field(
        "Regional or local antecedents of the author", default=None
    )
    author_milieu_id: Optional[int] = excel_field(
        "Author milieu", default=None, foreign_key="author_milieu.author_milieu_id"
    )
    author_note: Optional[str] = Field(default=None)

    milieu: Optional[AuthorMilieu] = Relationship(back_populates="authors")
    texts: List["Text"] = Relationship(back_populates="author")


class Text(SQLModel, table=True):
    """One row per TEXTS-sheet data row.

    text_unique_identifier is the given, stable identifier: the 'BHL or NO BHL' prefix
    (spaces → '_') joined with '_' to the stringified 'Unique identifier'
    value, e.g. BHL_29, BHL_1055-1056, NO_BHL_ALPER.

    The 'Precise institutional origin?' / 'Precise destinatary?' workbook
    flags are not stored: institution presence implies precision.
    """

    __tablename__ = "text"
    __table_args__ = unique_identifier_rules("text")

    text_id: Optional[int] = Field(default=None, primary_key=True)
    text_unique_identifier: str = excel_field(
        "'BHL or NO BHL' + '_' + 'Unique identifier'",
        unique=True,
    )
    text_title: Optional[str] = excel_field("Title of the work", default=None)
    text_approximate_token_count: Optional[int] = excel_field(
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
    text_reecriture: Optional[bool] = excel_field("Réécriture?", default=None)
    reecriture_of_text_id: Optional[int] = excel_field(
        "Réécriture of which text(s)? (resolved)",
        default=None,
        foreign_key="text.text_id",
    )
    text_reecriture_note: Optional[str] = excel_field(
        "Réécriture of which text(s)?", default=None
    )
    text_dating_range_start: Optional[int] = excel_field(
        "Dating range (beginning)", default=None
    )
    text_dating_range_end: Optional[int] = excel_field("Dating range (end)", default=None)
    text_dating_quarter_century: Optional[str] = excel_field(
        "Quarter century chronology", default=None
    )
    dating_confidence_id: Optional[int] = excel_field(
        "Dating confidence rating",
        default=None,
        foreign_key="dating_confidence.dating_confidence_id",
    )
    text_dating_note: Optional[str] = excel_field("Dating notes", default=None)
    author_id: Optional[int] = excel_field(
        "Author of the text", default=None, foreign_key="author.author_id"
    )
    text_author_in_destinatary_institution: Optional[bool] = excel_field(
        "Is author based in destinatary institution?",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    creation_archdiocese_id: Optional[int] = excel_field(
        "Text creation - location by archdiocese",
        default=None,
        foreign_key="archdiocese.archdiocese_id",
    )
    creation_diocese_id: Optional[int] = excel_field(
        "Text creation - location by diocese",
        default=None,
        foreign_key="diocese.diocese_id",
    )
    creation_institution_id: Optional[int] = excel_field(
        "Text creation - location by institution",
        default=None,
        foreign_key="institution.institution_id",
    )
    text_creation_note: Optional[str] = Field(default=None)
    destinatary_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="archdiocese.archdiocese_id"
    )
    destinatary_diocese_id: Optional[int] = Field(
        default=None, foreign_key="diocese.diocese_id"
    )
    destinatary_institution_id: Optional[int] = excel_field(
        "Primary institutional destinatary",
        default=None,
        foreign_key="institution.institution_id",
    )
    text_destinatary_note: Optional[str] = Field(default=None)
    text_reference: Optional[str] = excel_field("Selected reference", default=None)
    text_general_note: Optional[str] = excel_field("Notes", default=None)

    text_form: Optional[TextForm] = Relationship(back_populates="texts")
    text_source_type: Optional[TextSourceType] = Relationship(back_populates="texts")
    text_source_subtype: Optional[TextSourceSubtype] = Relationship(
        back_populates="texts"
    )
    dating_confidence: Optional[DatingConfidence] = Relationship(back_populates="texts")
    author: Optional[Author] = Relationship(back_populates="texts")
    reecriture_of: Optional["Text"] = Relationship(
        back_populates="reecritures",
        sa_relationship_kwargs={"remote_side": "Text.text_id"},
    )
    reecritures: List["Text"] = Relationship(back_populates="reecriture_of")
    creation_archdiocese: Optional[Archdiocese] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.creation_archdiocese_id"}
    )
    creation_diocese: Optional[Diocese] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.creation_diocese_id"}
    )
    creation_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.creation_institution_id"}
    )
    destinary_archdiocese: Optional[Archdiocese] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.destinatary_archdiocese_id"}
    )
    destinary_diocese: Optional[Diocese] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.destinatary_diocese_id"}
    )
    destinary_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.destinatary_institution_id"}
    )
    editions: List["Edition"] = Relationship(back_populates="text")
    manuscripts: List["Manuscript"] = Relationship(back_populates="text")
    repertory_links: List["TextRepertory"] = Relationship(back_populates="text")


class CodexPreservationStatus(SQLModel, table=True):
    """Lookup: Lost / Preserved.

    Canonicalised case-insensitively from MANUSCRIPTS 'Preservation status of
    manuscript copy' (the workbook mixes 'LOST' and 'Lost').
    """

    __tablename__ = "codex_preservation_status"

    codex_preservation_status_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    codex_preservation_status: str = excel_field(
        "Preservation status of manuscript copy", sheet="MANUSCRIPTS", unique=True
    )

    codices: List["Codex"] = Relationship(back_populates="preservation_status")


class CodexHoldingInstitution(SQLModel, table=True):
    """Lookup: deduplicated holding institutions.

    Names that differ only in case/whitespace are merged into one row; the
    most frequent raw spelling in the workbook wins. 'N/A' is not stored
    (those manuscripts get a NULL institution).
    """

    __tablename__ = "codex_holding_institution"

    codex_holding_institution_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    codex_holding_institution_name: str = excel_field(
        "Manuscript holding institution", sheet="MANUSCRIPTS", unique=True
    )

    codices: List["Codex"] = Relationship(back_populates="holding_institution")


class Codex(SQLModel, table=True):
    """One physical codex (migration 002; codex-level columns hoisted from
    manuscript in 009).

    codex_unique_identifier deduplicates the MANUSCRIPTS 'Codex unique identifier' (whitespace-
    collapsed, 'N/A' → no codex). The number of corpus copies in a codex and
    whether it holds several are derived: count(*) of its manuscripts.
    dating_range_start/_end are 0 when the workbook value was not an
    integer; the raw values are then kept in dating_note. dating_reference
    stores the cell's hyperlink URL when present.
    """

    __tablename__ = "codex"
    __table_args__ = (
        *unique_identifier_rules("codex"),
        {
            "comment": "One physical codex. Excel MANUSCRIPTS → "
            "'Codex unique identifier', deduplicated."
        },
    )

    codex_id: Optional[int] = Field(default=None, primary_key=True)
    codex_unique_identifier: str = excel_field(
        "Codex unique identifier", sheet="MANUSCRIPTS", unique=True
    )
    codex_preservation_status_id: Optional[int] = excel_field(
        "Preservation status of manuscript copy",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="codex_preservation_status.codex_preservation_status_id",
    )
    location_id: Optional[int] = excel_field(
        "Manuscript location",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="location.location_id",
    )
    codex_holding_institution_id: Optional[int] = excel_field(
        "Manuscript holding institution",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="codex_holding_institution.codex_holding_institution_id",
    )
    codex_height: Optional[str] = excel_field(
        "Manuscript height", sheet="MANUSCRIPTS", default=None
    )
    codex_width: Optional[str] = excel_field(
        "Manuscript width", sheet="MANUSCRIPTS", default=None
    )
    codex_dating_by_century: Optional[int] = excel_field(
        "Manuscript dating by (earliest) century", sheet="MANUSCRIPTS", default=None
    )
    codex_dating_range_start: Optional[int] = excel_field(
        "Manuscript dating range start (0 when not an integer in the workbook)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_dating_range_end: Optional[int] = excel_field(
        "Manuscript dating range end (0 when not an integer in the workbook)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_dating_reference: Optional[str] = excel_field(
        "Preferred secondary reference for manuscript dating "
        "(hyperlink URL when the cell is hyperlinked)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    dating_confidence_id: Optional[int] = excel_field(
        "Confidence rating for manuscript dating",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="dating_confidence.dating_confidence_id",
    )
    codex_dating_note: Optional[str] = excel_field(
        "raw 'Manuscript dating range start/end' when not integers",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_legendiers_usable: Optional[bool] = excel_field(
        "Usable Légendiers entry for codex contents",
        sheet="MANUSCRIPTS",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    codex_composite: Optional[bool] = excel_field(
        "Composite?",
        sheet="MANUSCRIPTS",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    codex_legendiers_entry_code: Optional[str] = excel_field(
        "Légendiers entry code", sheet="MANUSCRIPTS", default=None
    )
    codex_contents_note: Optional[str] = excel_field(
        "Notes on codex contents", sheet="MANUSCRIPTS", default=None
    )
    vernacular_region_id: Optional[int] = excel_field(
        "Vernacular region (Romance/Germanic)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="vernacular_region.vernacular_region_id",
    )
    origin_archdiocese_id: Optional[int] = excel_field(
        "Manuscript origin by archdiocese",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="archdiocese.archdiocese_id",
    )
    origin_diocese_id: Optional[int] = excel_field(
        "Manuscript origin by diocese",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="diocese.diocese_id",
    )
    origin_diocese_confidence_id: Optional[int] = excel_field(
        "Manuscript origin by diocese confidence rating",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="origin_confidence.origin_confidence_id",
    )
    origin_institution_id: Optional[int] = excel_field(
        "Manuscript origin by institution",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="institution.institution_id",
    )
    origin_institution_confidence_id: Optional[int] = excel_field(
        "Manuscript origin confidence rating",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="origin_confidence.origin_confidence_id",
    )
    provenance_early_institution_id: Optional[int] = excel_field(
        "Manuscript provenance by early/earliest institutional owner "
        "(second occurrence of this duplicated header)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="institution.institution_id",
    )
    provenance_early_confidence_id: Optional[int] = excel_field(
        "Manuscript provenance by early/earliest institutional owner "
        "confidence rating (second occurrence of this duplicated header)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="provenance_confidence.provenance_confidence_id",
    )
    provenance_later_institution_id: Optional[int] = excel_field(
        "Manuscript provenance by undetermined or later institutional owner",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="institution.institution_id",
    )
    provenance_later_confidence_id: Optional[int] = excel_field(
        "no source column yet (the workbook has no confidence rating for the "
        "undetermined/later owner) — always NULL for now",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="provenance_confidence.provenance_confidence_id",
    )
    codex_origin_or_provenance_secondary_reference: Optional[str] = excel_field(
        "Manuscript origin and provenance preferred secondary reference "
        "(hyperlink URL when the cell is hyperlinked)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_type_id: Optional[int] = excel_field(
        "Manuscript type (whitespace-normalized label)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="codex_type.codex_type_id",
    )
    codex_type_selection_note: Optional[str] = excel_field(
        "Manuscript type (raw cell, incl. notes on type selection)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_general_note: Optional[str] = excel_field(
        "'Notes', prefixed with the raw 'Unique text identifier' when it "
        "resolves to no text",
        sheet="MANUSCRIPTS",
        default=None,
    )
    codex_shelfmark: Optional[str] = excel_field(
        "Manuscript shelfmark", sheet="MANUSCRIPTS", default=None
    )

    preservation_status: Optional[CodexPreservationStatus] = Relationship(
        back_populates="codices"
    )
    location: Optional[Location] = Relationship(back_populates="codices")
    holding_institution: Optional[CodexHoldingInstitution] = Relationship(
        back_populates="codices"
    )
    dating_confidence: Optional[DatingConfidence] = Relationship(
        back_populates="codices"
    )
    vernacular_region: Optional["VernacularRegion"] = Relationship(
        back_populates="codices"
    )
    origin_archdiocese: Optional[Archdiocese] = Relationship(
        back_populates="origin_codices"
    )
    origin_diocese: Optional[Diocese] = Relationship(
        back_populates="origin_codices"
    )
    origin_diocese_confidence: Optional["OriginConfidence"] = Relationship(
        back_populates="diocese_rated_codices",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.origin_diocese_confidence_id"
        },
    )
    origin_institution: Optional[Institution] = Relationship(
        back_populates="origin_codices",
        sa_relationship_kwargs={"foreign_keys": "Codex.origin_institution_id"},
    )
    origin_institution_confidence: Optional["OriginConfidence"] = Relationship(
        back_populates="institution_rated_codices",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.origin_institution_confidence_id"
        },
    )
    provenance_early_institute: Optional[Institution] = Relationship(
        back_populates="provenance_early_codices",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.provenance_early_institution_id"
        },
    )
    provenance_early_confidence: Optional["ProvenanceConfidence"] = Relationship(
        back_populates="early_codices",
        sa_relationship_kwargs={"foreign_keys": "Codex.provenance_early_confidence_id"},
    )
    provenance_later_institute: Optional[Institution] = Relationship(
        back_populates="provenance_later_codices",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.provenance_later_institution_id"
        },
    )
    provenance_later_confidence: Optional["ProvenanceConfidence"] = Relationship(
        back_populates="later_codices",
        sa_relationship_kwargs={"foreign_keys": "Codex.provenance_later_confidence_id"},
    )
    manuscript_type: Optional["CodexType"] = Relationship(
        back_populates="codices"
    )
    manuscripts: List["Manuscript"] = Relationship(back_populates="codex")
    links: List["CodexLink"] = Relationship(back_populates="codex")


class Manuscript(SQLModel, table=True):
    """One row per MANUSCRIPTS-sheet data row (one manuscript copy).

    manuscript_unique_identifier is the given, stable copy identifier: the 'BHL or NO BHL'
    prefix (spaces → '_') joined with '_' to the 'Manuscript copy unique
    identifier per text' value, e.g. BHL_29-4. Not constrained unique: the
    workbook had duplicates (imported as-is); PRD has none since Oct 2026. text_id links the copy to
    its text via prefix + 'Unique text identifier'; when that reference does
    not resolve to a text, the manuscript is still imported with text_id
    NULL and the raw reference kept in the codex's codex_general_note.

    Since migrations 009–012 a manuscript is only the text copy: everything
    describing the physical book (shelfmark, holding institution, dating,
    origin/provenance, …) lives on its codex. folio_or_page_range locates
    the copy inside the codex. URLs about the codex (catalogues, Légendiers,
    IIIF, scans) live in codex_link; copy-level URLs in manuscript_link.
    """

    __tablename__ = "manuscript"
    __table_args__ = unique_identifier_rules("manuscript")

    manuscript_id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_unique_identifier: str = excel_field(
        "'BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text' "
        "(workbook duplicates are imported as-is and warned)",
        sheet="MANUSCRIPTS",
        unique=True,
    )
    text_id: Optional[int] = excel_field(
        "Unique text identifier (NULL when the reference is unresolvable; "
        "see general_notes)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="text.text_id",
        index=True,
    )
    manuscript_folio_or_page_range: Optional[str] = excel_field(
        "Folio or page range", sheet="MANUSCRIPTS", default=None
    )
    codex_id: Optional[int] = Field(
        default=None,
        foreign_key="codex.codex_id",
        index=True,
        sa_column_kwargs={
            "comment": "The codex this copy is bound in; resolved from "
            "'Codex unique identifier'"
        },
    )

    text: Optional["Text"] = Relationship(back_populates="manuscripts")
    codex: Optional[Codex] = Relationship(back_populates="manuscripts")
    links: List["ManuscriptLink"] = Relationship(back_populates="manuscript")
    relations: List["ManuscriptManuscript"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"foreign_keys": "ManuscriptManuscript.manuscript_id"},
    )
    related_by: List["ManuscriptManuscript"] = Relationship(
        back_populates="related_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "ManuscriptManuscript.related_manuscript_id"
        },
    )
    edition_links: List["EditionManuscript"] = Relationship(back_populates="manuscript")


class CodexLinkType(SQLModel, table=True):
    """Lookup: what a codex URL points at (catalogue description, Légendiers
    entry, IIIF manifest, scans, …). Was manuscript_link_type until
    migration 060.
    """

    __tablename__ = "codex_link_type"

    codex_link_type_id: Optional[int] = Field(default=None, primary_key=True)
    codex_link_type: str = Field(unique=True)
    codex_link_type_note: Optional[str] = Field(default=None)

    links: List["CodexLink"] = Relationship(back_populates="link_type")


class CodexLink(SQLModel, table=True):
    """A URL describing a whole codex, typed via codex_link_type.

    From the MANUSCRIPTS link columns ('Légendiers entry link', 'Viable
    alternative for Légendiers entry on codex contents', 'Online catalogue
    link', 'Bollandist catalogue link', 'Other relevant catalogue link',
    'Online manuscript images' routed by 'Type of online images'). The
    workbook repeated these on every text copy of a codex; migration 061
    moved them to the codex and merged the repeats (notes joined with ' | ').
    codex_link_url is the cell's hyperlink target, never its display text.
    The file explorer tracks these URLs in hagio_admin.codex_link_reference.
    """

    __tablename__ = "codex_link"
    __table_args__ = (  # migration 061
        UniqueConstraint(
            "codex_id", "codex_link_type_id", "codex_link_url",
            name="codex_link_codex_id_codex_link_type_id_codex_link_url_key",
        ),
    )

    codex_link_id: Optional[int] = Field(default=None, primary_key=True)
    codex_link_type_id: int = excel_field(
        "link column → type",
        sheet="MANUSCRIPTS",
        foreign_key="codex_link_type.codex_link_type_id",
    )
    codex_link_url: str = excel_field("link cell hyperlink target", sheet="MANUSCRIPTS")
    codex_link_note: Optional[str] = Field(default=None)
    codex_id: int = Field(
        foreign_key="codex.codex_id",
        index=True,
        sa_column_kwargs={
            "comment": "The codex this link describes (moved from manuscript "
            "level in migration 061)"
        },
    )

    codex: Optional[Codex] = Relationship(back_populates="links")
    link_type: Optional[CodexLinkType] = Relationship(back_populates="links")


class ManuscriptLinkType(SQLModel, table=True):
    """Lookup: what a copy-level manuscript URL points at. Created empty in
    migration 062; the researchers define the types in Mathesar.
    """

    __tablename__ = "manuscript_link_type"

    manuscript_link_type_id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_link_type: str = Field(unique=True)
    manuscript_link_type_note: Optional[str] = Field(default=None)

    links: List["ManuscriptLink"] = Relationship(back_populates="link_type")


class ManuscriptLink(SQLModel, table=True):
    """A URL about one text copy (manuscript), not the whole codex: links
    about the codex live in codex_link. Created empty in migration 062. Not
    tracked by the file explorer.
    """

    __tablename__ = "manuscript_link"

    manuscript_link_id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: int = Field(foreign_key="manuscript.manuscript_id", index=True)
    manuscript_link_type_id: int = Field(
        foreign_key="manuscript_link_type.manuscript_link_type_id"
    )
    manuscript_link_url: str
    manuscript_link_note: Optional[str] = Field(default=None)

    manuscript: Optional[Manuscript] = Relationship(back_populates="links")
    link_type: Optional[ManuscriptLinkType] = Relationship(back_populates="links")


class ProvenanceConfidence(SQLModel, table=True):
    """Lookup: A/B/C/D confidence rating for manuscript provenance owners.

    Populated from the early/earliest-owner confidence column (the second
    occurrence of its duplicated header). The undetermined/later owner has
    no confidence column in the workbook yet, so later_codices links
    stay empty for now.
    """

    __tablename__ = "provenance_confidence"

    provenance_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    provenance_confidence: str = excel_field(
        "Manuscript provenance by early/earliest institutional owner "
        "confidence rating",
        sheet="MANUSCRIPTS",
        unique=True,
    )
    provenance_confidence_note: Optional[str] = Field(default=None)

    early_codices: List["Codex"] = Relationship(
        back_populates="provenance_early_confidence",
        sa_relationship_kwargs={"foreign_keys": "Codex.provenance_early_confidence_id"},
    )
    later_codices: List["Codex"] = Relationship(
        back_populates="provenance_later_confidence",
        sa_relationship_kwargs={"foreign_keys": "Codex.provenance_later_confidence_id"},
    )


class OriginConfidence(SQLModel, table=True):
    """Lookup: A/B/C/D confidence rating for manuscript origin columns."""

    __tablename__ = "origin_confidence"

    origin_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    origin_confidence: str = excel_field(
        "'Manuscript origin by diocese confidence rating' / "
        "'Manuscript origin confidence rating'",
        sheet="MANUSCRIPTS",
        unique=True,
    )
    origin_confidence_note: Optional[str] = Field(default=None)

    diocese_rated_codices: List["Codex"] = Relationship(
        back_populates="origin_diocese_confidence",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.origin_diocese_confidence_id"
        },
    )
    institution_rated_codices: List["Codex"] = Relationship(
        back_populates="origin_institution_confidence",
        sa_relationship_kwargs={
            "foreign_keys": "Codex.origin_institution_confidence_id"
        },
    )


class VernacularRegion(SQLModel, table=True):
    """Lookup: vernacular region (distinct values: G, R, F).

    From MANUSCRIPTS 'Vernacular region (Romance/Germanic)'; 'Unknown' and
    'N/A' mean NULL, anything else is reported and skipped.
    """

    __tablename__ = "vernacular_region"

    vernacular_region_id: Optional[int] = Field(default=None, primary_key=True)
    vernacular_region: str = excel_field(
        "Vernacular region (Romance/Germanic)", sheet="MANUSCRIPTS", unique=True
    )
    vernacular_region_note: Optional[str] = Field(default=None)

    codices: List["Codex"] = Relationship(back_populates="vernacular_region")


class CodexType(SQLModel, table=True):
    """Lookup: manuscript type, one row per distinct whitespace-normalized
    'Manuscript type' value (the raw cell text, which may carry notes on
    type selection, is kept per codex in codex_type_selection_note).
    """

    __tablename__ = "codex_type"

    codex_type_id: Optional[int] = Field(default=None, primary_key=True)
    codex_type: str = excel_field(
        "Manuscript type (whitespace-normalized)", sheet="MANUSCRIPTS", unique=True
    )
    codex_type_note: Optional[str] = Field(default=None)

    codices: List["Codex"] = Relationship(back_populates="manuscript_type")


class ManuscriptManuscriptType(SQLModel, table=True):
    """Lookup: how two manuscripts relate.

    Seeded by the importer with 'Based on exemplar' and 'Exemplar of'.
    """

    __tablename__ = "manuscript__manuscript_type"

    manuscript__manuscript_type_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    manuscript__manuscript_type: str = Field(unique=True)
    manuscript__manuscript_type_note: Optional[str] = Field(default=None)

    relations: List["ManuscriptManuscript"] = Relationship(
        back_populates="relationship_type"
    )


class ManuscriptManuscript(SQLModel, table=True):
    """Link: a manuscript related to another manuscript, typed.

    From the MANUSCRIPTS 'Based on exemplar' and 'Exemplar of which
    manuscript(s)' columns (the latter comma-split); references are resolved
    like the EDITIONS manuscript refs — copy identifier first, then codex
    identifier within the row's own text. note has no Excel source.
    """

    __tablename__ = "manuscript__manuscript"
    __table_args__ = (  # migration 058
        UniqueConstraint(
            "manuscript_id", "related_manuscript_id", "manuscript__manuscript_type_id",
            name="manuscript__manuscript_relation_key",
        ),
        CheckConstraint(
            "manuscript_id <> related_manuscript_id",
            name="manuscript__manuscript_not_self_check",
        ),
    )

    manuscript__manuscript_id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: int = excel_field(
        "'Based on exemplar' / 'Exemplar of which manuscript(s)' (row)",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript.manuscript_id",
        index=True,
    )
    related_manuscript_id: int = excel_field(
        "'Based on exemplar' / 'Exemplar of which manuscript(s)' (resolved)",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript.manuscript_id",
        index=True,
    )
    manuscript__manuscript_type_id: int = excel_field(
        "source column → type",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript__manuscript_type.manuscript__manuscript_type_id",
    )
    manuscript__manuscript_note: Optional[str] = Field(default=None)

    manuscript: Optional[Manuscript] = Relationship(
        back_populates="relations",
        sa_relationship_kwargs={"foreign_keys": "ManuscriptManuscript.manuscript_id"},
    )
    related_manuscript: Optional[Manuscript] = Relationship(
        back_populates="related_by",
        sa_relationship_kwargs={
            "foreign_keys": "ManuscriptManuscript.related_manuscript_id"
        },
    )
    relationship_type: Optional[ManuscriptManuscriptType] = Relationship(
        back_populates="relations"
    )


class Publication(SQLModel, table=True):
    """One published volume (migration 003; columns hoisted from edition in
    010). publication_unique_identifier deduplicates EDITIONS 'Edition unique identifier (inc.
    volume)'.
    """

    __tablename__ = "publication"
    __table_args__ = (
        *unique_identifier_rules("publication"),
        {
            "comment": "One published volume. Excel EDITIONS → "
            "'Edition unique identifier (inc. volume)', deduplicated."
        },
    )

    publication_id: Optional[int] = Field(default=None, primary_key=True)
    publication_unique_identifier: str = excel_field(
        "Edition unique identifier (inc. volume)", sheet="EDITIONS", unique=True
    )
    publication_year: Optional[int] = excel_field(
        "Publication year", sheet="EDITIONS", default=None
    )
    publication_full_reference: Optional[str] = excel_field(
        "Edition reference", sheet="EDITIONS", default=None
    )

    editions: List["Edition"] = Relationship(back_populates="publication")


class Edition(SQLModel, table=True):
    """One row per EDITIONS-sheet data row.

    text_id links the edition to its text: the EDITIONS 'Unique identifier'
    value is the part of text.identifier after the BHL/NO-BHL prefix. When
    that reference does not resolve to a text, the edition is still imported
    with text_id NULL and the raw reference kept in edition_general_note.
    edition_unique_identifier carries that text's prefix (e.g. BHL_29-A), matching
    the text and manuscript identifier convention (stored unprefixed when
    the text is unresolvable).
    reprint_of_edition_id resolves 'If reprint, of what?' to another edition
    of the same text (the raw Excel value is kept in edition_reprint_of_note); references
    are matched first as a per-text edition identifier (e.g. '616-B'), then
    as an '(inc. volume)' identifier within the same text.
    The 'Edition images link' hyperlink URL lives in edition_link, typed by
    the 'Images of edition?' value (SCAN vs Transcription). Publication year
    and reference live on the publication (hoisted in migration 010).
    """

    __tablename__ = "edition"

    edition_id: Optional[int] = Field(default=None, primary_key=True)
    text_id: Optional[int] = excel_field(
        "Unique identifier (NULL when the reference is unresolvable; "
        "see general_notes)",
        sheet="EDITIONS",
        default=None,
        foreign_key="text.text_id",
        index=True,
    )
    edition_unique_identifier: str = excel_field(
        "'BHL or NO BHL' prefix + '_' + 'Edition unique identifier per individual text'",
        sheet="EDITIONS",
        index=True,
    )
    edition_page_numbers: Optional[str] = excel_field(
        "Page numbers", sheet="EDITIONS", default=None
    )
    edition_reprint: Optional[bool] = excel_field("Reprint ?", sheet="EDITIONS", default=None)
    edition_reprint_identical: Optional[bool] = excel_field(
        "If reprint, identically typeset?", sheet="EDITIONS", default=None
    )
    reprint_of_edition_id: Optional[int] = excel_field(
        "If reprint, of what? (resolved)",
        sheet="EDITIONS",
        default=None,
        foreign_key="edition.edition_id",
    )
    edition_reprint_of_note: Optional[str] = excel_field(
        "If reprint, of what?", sheet="EDITIONS", default=None
    )
    edition_collation_done: Optional[bool] = excel_field(
        "Collation done?",
        sheet="EDITIONS",
        default=None,
        description="Tri-state: true/false/NULL (unknown; a non-tristate "
        "workbook value warns and stays NULL).",
    )
    edition_general_note: Optional[str] = excel_field("Notes", sheet="EDITIONS", default=None)
    publication_id: Optional[int] = Field(
        default=None,
        foreign_key="publication.publication_id",
        index=True,
        sa_column_kwargs={
            "comment": "The volume this edition is printed in; resolved from "
            "'Edition unique identifier (inc. volume)'"
        },
    )

    text: Optional["Text"] = Relationship(back_populates="editions")
    publication: Optional["Publication"] = Relationship(back_populates="editions")
    reprint_of_edition: Optional["Edition"] = Relationship(
        back_populates="reprints",
        sa_relationship_kwargs={"remote_side": "Edition.edition_id"},
    )
    reprints: List["Edition"] = Relationship(back_populates="reprint_of_edition")
    links: List["EditionLink"] = Relationship(back_populates="edition")
    manuscript_links: List["EditionManuscript"] = Relationship(back_populates="edition")
    consulted_edition_links: List["EditionEdition"] = Relationship(
        back_populates="edition",
        sa_relationship_kwargs={"foreign_keys": "EditionEdition.edition_id"},
    )
    consulted_by_links: List["EditionEdition"] = Relationship(
        back_populates="consulted_edition",
        sa_relationship_kwargs={"foreign_keys": "EditionEdition.consulted_edition_id"},
    )


class EditionLinkType(SQLModel, table=True):
    """Lookup: what an edition URL points at.

    Seeded by the importer with: Images Scan, Transcription.
    """

    __tablename__ = "edition_link_type"

    edition_link_type_id: Optional[int] = Field(default=None, primary_key=True)
    edition_link_type: str = Field(unique=True)
    edition_link_type_note: Optional[str] = Field(default=None)

    links: List["EditionLink"] = Relationship(back_populates="link_type")


class EditionLink(SQLModel, table=True):
    """A URL attached to an edition, typed via edition_link_type.

    From the EDITIONS 'Edition images link' column, typed by the
    'Images of edition?' value (SCAN → Images Scan, Transcription →
    Transcription). url is the cell's hyperlink target, never its display
    text ('Link'). note has no Excel source (manual annotation).
    """

    __tablename__ = "edition_link"

    edition_link_id: Optional[int] = Field(default=None, primary_key=True)
    edition_id: int = excel_field(
        "Edition images link (row)",
        sheet="EDITIONS",
        foreign_key="edition.edition_id",
        index=True,
    )
    edition_link_type_id: int = excel_field(
        "Images of edition? → type",
        sheet="EDITIONS",
        foreign_key="edition_link_type.edition_link_type_id",
    )
    edition_link_url: str = excel_field("'Edition images link' hyperlink target", sheet="EDITIONS")
    edition_link_note: Optional[str] = Field(default=None)

    edition: Optional[Edition] = Relationship(back_populates="links")
    link_type: Optional[EditionLinkType] = Relationship(back_populates="links")


class EditionManuscript(SQLModel, table=True):
    """Link: a manuscript used by an edition.

    From the EDITIONS 'Manuscript used 1'–'Manuscript used 16' columns; the
    cell references a manuscript either by its per-text copy identifier
    (e.g. '29-1') or by its codex identifier within the edition's text
    (e.g. 'Cologne HA 6'). notes has no Excel source (manual annotation).
    """

    __tablename__ = "edition__manuscript"
    __table_args__ = (  # migration 057
        UniqueConstraint(
            "edition_id", "manuscript_id",
            name="edition__manuscript_edition_id_manuscript_id_key",
        ),
    )

    edition__manuscript_id: Optional[int] = Field(default=None, primary_key=True)
    edition_id: int = excel_field(
        "Manuscript used 1–16 (row)",
        sheet="EDITIONS",
        foreign_key="edition.edition_id",
        index=True,
    )
    manuscript_id: int = excel_field(
        "Manuscript used 1–16 (resolved)",
        sheet="EDITIONS",
        foreign_key="manuscript.manuscript_id",
        index=True,
    )
    edition__manuscript_likely_use_of_a_copy: Optional[bool] = excel_field(
        "Likely use of a copy of Manuscript 1–16?",
        sheet="EDITIONS",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    edition__manuscript_note: Optional[str] = Field(default=None)

    edition: Optional[Edition] = Relationship(back_populates="manuscript_links")
    manuscript: Optional[Manuscript] = Relationship(back_populates="edition_links")


class EditionEdition(SQLModel, table=True):
    """Link: an edition used or consulted by another edition.

    From the EDITIONS 'Edition used or consulted 1'–'5' columns; the cell
    references an edition by per-text identifier (e.g. '618-A') or by
    '(inc. volume)' identifier within the same text (e.g. 'Surius 5 (1574)').
    notes has no Excel source (manual annotation).
    """

    __tablename__ = "edition__edition"
    __table_args__ = (  # migration 059; the not-self CHECK is parked in db/migrations/pending/
        UniqueConstraint(
            "edition_id", "consulted_edition_id",
            name="edition__edition_edition_id_consulted_edition_id_key",
        ),
    )

    edition__edition_id: Optional[int] = Field(default=None, primary_key=True)
    edition_id: int = excel_field(
        "Edition used or consulted 1–5 (row)",
        sheet="EDITIONS",
        foreign_key="edition.edition_id",
        index=True,
    )
    consulted_edition_id: int = excel_field(
        "Edition used or consulted 1–5 (resolved)",
        sheet="EDITIONS",
        foreign_key="edition.edition_id",
        index=True,
    )
    edition__edition_note: Optional[str] = Field(default=None)

    edition: Optional[Edition] = Relationship(
        back_populates="consulted_edition_links",
        sa_relationship_kwargs={"foreign_keys": "EditionEdition.edition_id"},
    )
    consulted_edition: Optional[Edition] = Relationship(
        back_populates="consulted_by_links",
        sa_relationship_kwargs={"foreign_keys": "EditionEdition.consulted_edition_id"},
    )


class Repertory(SQLModel, table=True):
    """A repertory (external reference work), curated by hand.

    Not populated by the importer: the TEXTS sheet's 'Links to repertories'
    columns hold bare URLs with no repertory name to import.
    """

    __tablename__ = "repertory"

    repertory_id: Optional[int] = Field(default=None, primary_key=True)
    repertory_name: str = Field(unique=True)
    repertory_note: Optional[str] = Field(default=None)

    links: List["TextRepertory"] = Relationship(back_populates="repertory")


class TextRepertory(SQLModel, table=True):
    """Many-to-many: a text's entry in a repertory, curated by hand.

    One text can have several entries (URLs) in the same repertory; an exact
    repeat of (text, repertory, url) is refused (migration 051).
    """

    __tablename__ = "text__repertory"
    __table_args__ = (
        UniqueConstraint(
            "text_id",
            "repertory_id",
            "text__repertory_url",
            name="text__repertory_text_id_repertory_id_text__repertory_url_key",
        ),
    )

    text__repertory_id: Optional[int] = Field(default=None, primary_key=True)
    text_id: int = Field(foreign_key="text.text_id", index=True)
    repertory_id: int = Field(foreign_key="repertory.repertory_id", index=True)
    text__repertory_url: Optional[str] = Field(default=None, sa_type=SAText)
    text__repertory_note: Optional[str] = Field(default=None)

    text: Optional["Text"] = Relationship(back_populates="repertory_links")
    repertory: Optional[Repertory] = Relationship(back_populates="links")
