"""
model.py — SQLAlchemy/SQLModel ORM definitions for the Hagiographies database.

Table hierarchy
---------------
Jurisdiction : Archbishopric, Bishopric
Geography    : Origin, City, Library, Location
Lookups      : Author, DatingRough, Subtype, Destinatary, ProseVerse,
               SourceType, PreservationStatus, VernacularRegion,
               ManuscriptType, ImageAvailability
Core content : Text, Manuscript, ManuscriptRelation, ExternalResource, ManuscriptImage, Witness
Editorial    : Provenance, Reference, Edition, EditionManuscriptLink
"""

# NOTE: "from __future__ import annotations" is intentionally absent.

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Table(SQLModel):
    """Abstract base that adds a surrogate PK and audit timestamps."""

    id: Optional[int] = Field(default=None, primary_key=True)

    created_at: datetime = Field(
        default=None,
        sa_type=DateTime(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )

    updated_at: datetime = Field(
        default=None,
        sa_type=DateTime(),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": func.now(),
            "nullable": False,
        },
    )


# ---------------------------------------------------------------------------
# Junction / link table (defined first)
# ---------------------------------------------------------------------------

class EditionManuscriptLink(SQLModel, table=True):
    """Many-to-many join between Edition and Manuscript."""
    edition_id: int = Field(foreign_key="edition.id", primary_key=True)
    manuscript_id: int = Field(foreign_key="manuscript.id", primary_key=True)
    uncertain: bool = Field(default=False, description="True when the MS reference carried a '(?)' marker in the source")


# ---------------------------------------------------------------------------
# Jurisdiction
# ---------------------------------------------------------------------------

class Archbishopric(Table, table=True):
    name: str = Field(index=True, unique=True)
    origins: List["Origin"] = Relationship(back_populates="archbishopric")
    texts: List["Text"] = Relationship(back_populates="archbishopric")
    witnesses: List["Witness"] = Relationship(back_populates="archbishopric")


class Bishopric(Table, table=True):
    name: str = Field(index=True, unique=True)
    origins: List["Origin"] = Relationship(back_populates="bishopric")
    texts: List["Text"] = Relationship(back_populates="bishopric")
    witnesses: List["Witness"] = Relationship(back_populates="bishopric")


# ---------------------------------------------------------------------------
# Lookup Tables (Normalized Categories)
# ---------------------------------------------------------------------------

class Author(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="author")

class DatingRough(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="dating_rough")

class Destinatary(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="primary_destinatary")

class ProseVerse(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="prose_verse")

class SourceType(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="source_type")

class Subtype(Table, table=True):
    name: str = Field(index=True, unique=True)
    texts: List["Text"] = Relationship(back_populates="subtype")

class PreservationStatus(Table, table=True):
    name: str = Field(index=True, unique=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="preservation_status")

class VernacularRegion(Table, table=True):
    name: str = Field(index=True, unique=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="vernacular_region")

class ManuscriptType(Table, table=True):
    name: str = Field(index=True, unique=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="manuscript_type")

class ImageAvailability(Table, table=True):
    name: str = Field(index=True, unique=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="image_availability")


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------

class Origin(Table, table=True):
    name: str = Field(index=True, unique=True)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    texts: List["Text"] = Relationship(back_populates="origin")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="origins")
    bishopric: Optional[Bishopric] = Relationship(back_populates="origins")


class City(Table, table=True):
    name: str = Field(index=True, unique=True)
    locations: List["Location"] = Relationship(back_populates="city")


class Library(Table, table=True):
    name: str = Field(index=True, unique=True)
    locations: List["Location"] = Relationship(back_populates="library")


class Location(Table, table=True):
    __table_args__ = (
        UniqueConstraint("city_id", "library_id", "shelfmark", name="uq_location"),
    )
    city_id: int = Field(foreign_key="city.id")
    library_id: int = Field(foreign_key="library.id")
    shelfmark: str

    city: City = Relationship(back_populates="locations")
    library: Library = Relationship(back_populates="locations")
    manuscripts: List["Manuscript"] = Relationship(back_populates="location")


# ---------------------------------------------------------------------------
# Core content
# ---------------------------------------------------------------------------

class Text(Table, table=True):
    """Formerly CorpusHagio: A text identified by its BHL number."""
    bhl_number: str = Field(index=True, unique=True)
    title: Optional[str] = None

    author_id: Optional[int] = Field(default=None, foreign_key="author.id")
    dating_rough_id: Optional[int] = Field(default=None, foreign_key="datingrough.id")
    origin_id: Optional[int] = Field(default=None, foreign_key="origin.id")

    primary_destinatary_id: Optional[int] = Field(default=None, foreign_key="destinatary.id")
    destinatary_latitude: Optional[float] = None
    destinatary_longitude: Optional[float] = None

    approx_length: Optional[int] = None

    source_type_id: Optional[int] = Field(default=None, foreign_key="sourcetype.id")
    subtype_id: Optional[int] = Field(default=None, foreign_key="subtype.id")
    prose_verse_id: Optional[int] = Field(default=None, foreign_key="proseverse.id")

    is_reecriture: Optional[bool] = None
    ocr_status: Optional[str] = None
    notes: Optional[str] = None

    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    # Relationships
    author: Optional[Author] = Relationship(back_populates="texts")
    dating_rough: Optional[DatingRough] = Relationship(back_populates="texts")
    origin: Optional[Origin] = Relationship(back_populates="texts")
    primary_destinatary: Optional[Destinatary] = Relationship(back_populates="texts")
    source_type: Optional[SourceType] = Relationship(back_populates="texts")
    subtype: Optional[Subtype] = Relationship(back_populates="texts")
    prose_verse: Optional[ProseVerse] = Relationship(back_populates="texts")

    archbishopric: Optional[Archbishopric] = Relationship(back_populates="texts")
    bishopric: Optional[Bishopric] = Relationship(back_populates="texts")
    witnesses: List["Witness"] = Relationship(back_populates="text")
    editions: List["Edition"] = Relationship(back_populates="text")


class Manuscript(Table, table=True):
    """A physical manuscript codex held at a specific Location."""
    unique_id: Optional[str] = Field(default=None, index=True, unique=True)
    title: Optional[str] = None
    location_id: int = Field(foreign_key="location.id")

    preservation_status_id: Optional[int] = Field(default=None, foreign_key="preservationstatus.id")
    vernacular_region_id: Optional[int] = Field(default=None, foreign_key="vernacularregion.id")
    manuscript_type_id: Optional[int] = Field(default=None, foreign_key="manuscripttype.id")
    image_availability_id: Optional[int] = Field(default=None, foreign_key="imageavailability.id")

    height: Optional[float] = None
    width: Optional[float] = None

    # Boolean flags
    leg: Optional[bool] = None
    dg: Optional[bool] = None
    naso: Optional[bool] = None
    ed_sec: Optional[bool] = None
    notes: Optional[str] = None

    # Relationships
    location: Location = Relationship(back_populates="manuscripts")
    preservation_status: Optional[PreservationStatus] = Relationship(back_populates="manuscripts")
    vernacular_region: Optional[VernacularRegion] = Relationship(back_populates="manuscripts")
    manuscript_type: Optional[ManuscriptType] = Relationship(back_populates="manuscripts")
    image_availability: Optional[ImageAvailability] = Relationship(back_populates="manuscripts")

    witnesses: List["Witness"] = Relationship(back_populates="manuscript")
    editions: List["Edition"] = Relationship(back_populates="manuscripts", link_model=EditionManuscriptLink)


class ManuscriptRelation(Table, table=True):
    """Directed relationship between manuscripts. A is a copy of B."""
    __table_args__ = (
        UniqueConstraint("source_manuscript_id", "target_manuscript_id", "relation_type", name="uq_ms_relation"),
    )
    source_manuscript_id: int = Field(foreign_key="manuscript.id", index=True)
    target_manuscript_id: int = Field(foreign_key="manuscript.id", index=True)
    
    relation_type: str = Field(default="copy_of", description="Standard relation is 'copy_of' (source copied target)")
    certainty: str = Field(default="uncertain", description="certain, probable, uncertain")
    
    notes: Optional[str] = None
    source_reference: Optional[str] = Field(default=None, description="Where did we learn this relation?")


class ExternalResource(Table, table=True):
    """Links to external resources (catalogues, Bollandists, etc.)."""
    __table_args__ = (
        UniqueConstraint("manuscript_id", "url", name="uq_ms_resource_url"),
    )
    manuscript_id: int = Field(foreign_key="manuscript.id", index=True)
    resource_type: str = Field(description="catalog_link, bollandist_catalog, other")
    url: str
    comment: Optional[str] = None
    alive: bool = Field(default=True)


class ManuscriptImage(Table, table=True):
    """Links to specific images or scans (IIIF, iPhone, etc.)."""
    __table_args__ = (
        UniqueConstraint("manuscript_id", "url", name="uq_ms_image_url"),
    )
    manuscript_id: int = Field(foreign_key="manuscript.id", index=True)
    image_type: str = Field(description="IIIF, Scan, iPhone Photo, etc.")
    url: str
    comments: Optional[str] = None


class Provenance(Table, table=True):
    """Composite provenance tracking general region, institution, and jurisdiction."""
    __table_args__ = (
        UniqueConstraint("name", "archdiocese", "diocese", "institution", name="uq_provenance"),
    )
    name: Optional[str] = Field(default=None, index=True)
    archdiocese: Optional[str] = None
    diocese: Optional[str] = None
    institution: Optional[str] = None

    witnesses: List["Witness"] = Relationship(back_populates="provenance")


class Witness(Table, table=True):
    """A single occurrence of a text within a manuscript."""
    text_id: int = Field(foreign_key="text.id")
    manuscript_id: int = Field(foreign_key="manuscript.id")

    ms_number_per_bhl: Optional[str] = None
    page_range: Optional[str] = None

    # Dating
    dating_century: Optional[str] = None
    dating_raw: Optional[str] = None
    dating_start: Optional[int] = None
    dating_end: Optional[int] = None
    dating_comment: Optional[str] = None

    # Provenance
    provenance_id: Optional[int] = Field(default=None, foreign_key="provenance.id")
    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    text: Text = Relationship(back_populates="witnesses")
    manuscript: Manuscript = Relationship(back_populates="witnesses")
    provenance: Optional[Provenance] = Relationship(back_populates="witnesses")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="witnesses")
    bishopric: Optional[Bishopric] = Relationship(back_populates="witnesses")


# ---------------------------------------------------------------------------
# Editorial
# ---------------------------------------------------------------------------

class Reference(Table, table=True):
    title: str = Field(index=True, unique=True)
    editions: List["Edition"] = Relationship(back_populates="reference")


class Edition(Table, table=True):
    """A printed or digital edition of one or more hagiographical texts."""
    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    title: Optional[str] = None
    reference_id: Optional[int] = Field(default=None, foreign_key="reference.id")

    unique_ed_id: Optional[str] = None
    unique_id_per_volume: Optional[str] = None

    year: Optional[int] = None
    pages: Optional[str] = None

    # Corpus membership flags
    dg: Optional[bool] = None
    naso: Optional[bool] = None
    isb: Optional[bool] = None
    ed_sec: Optional[bool] = None

    # Reprint fields
    is_reprint: Optional[bool] = None
    reprint_identically_typeset: Optional[bool] = None
    reprint_newly_typeset: Optional[bool] = None
    reprint_of: Optional[str] = None

    # Online access
    link_format: Optional[str] = None
    online_scan_link: Optional[str] = None

    # Scholarly use tracking
    transcribed: Optional[bool] = None
    our_transcribed_ed: Optional[bool] = None
    collation_done: Optional[bool] = None
    notes: Optional[str] = None

    text: Optional[Text] = Relationship(back_populates="editions")
    reference: Optional[Reference] = Relationship(back_populates="editions")
    manuscripts: List[Manuscript] = Relationship(
        back_populates="editions",
        link_model=EditionManuscriptLink,
    )