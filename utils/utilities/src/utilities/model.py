# utilities/model.py
# ---------------------------------------------------------------------------
# SQLModel models for the Hagiographies project.
#
# Three core entities map to the three Excel tabs:
#   Text          -> Tab 3 "Corpus hagio"   (one row per BHL text)
#   Manuscript    -> Tab 1 "Manuscripts"     (one row per material witness)
#   Edition       -> Tab 2 "Editions"        (one row per edition)
#
# Normalised satellite tables:
#   Image                      -> col AB (image URLs) + col AA (type)
#   ExternalResource           -> cols X, Y, Z (catalogue/Bollandist links)
#   ManuscriptExternalResource -> M2M join Manuscript <-> ExternalResource
#   EditionExternalResource    -> M2M join Edition    <-> ExternalResource
#   ManuscriptRelation         -> copy/exemplar relations (replaces 10 flat cols)
#   EditionManuscript          -> M2M join Edition <-> Manuscript (cols W-AL)
#
# SQLite STRICT mode throughout. BOOLEAN -> INTEGER (0/1).
# TEXT instead of VARCHAR, REAL instead of FLOAT (STRICT compatibility).
# ---------------------------------------------------------------------------

from datetime import datetime
from typing import Optional, List

from sqlalchemy import Integer
from sqlalchemy import Text as SAText
from sqlalchemy import REAL, UniqueConstraint, func
from sqlmodel import Field, SQLModel, Relationship

_STRICT = {"sqlite_strict": True}


def _text(**kwargs):
    """TEXT column — VARCHAR is not STRICT-compatible."""
    return Field(sa_type=SAText(), **kwargs)


def _real(**kwargs):
    """REAL column — FLOAT is not STRICT-compatible."""
    return Field(sa_type=REAL(), **kwargs)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Table(SQLModel):
    """Base class: auto PK + audit timestamps."""
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default=None,
        sa_type=SAText(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default=None,
        sa_type=SAText(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )


# ---------------------------------------------------------------------------
# Normalized "Class" Tables
# ---------------------------------------------------------------------------

class Place(Table, table=True):
    """Normalized location/place."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)

    # Reverse relationships for map exporter
    texts: List["Text"] = Relationship(
        back_populates="origin_location",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_location_id]"}
    )


class Institution(Table, table=True):
    """Normalized institution (heritage, provenance, etc.)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    place: Optional[Place] = Relationship()


class Author(Table, table=True):
    """Normalized author."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    
    texts: List["Text"] = Relationship(back_populates="author_obj")


class Typology(Table, table=True):
    """Normalized source type and subtype."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="typology.id")


class ManuscriptType(Table, table=True):
    """Normalized manuscript type."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class Milieu(Table, table=True):
    """Normalized milieu (Monastic, Clerical, etc.)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ChurchEntity(Table, table=True):
    """Normalized Archbishopric/Bishopric."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    is_archdiocese: int = Field(default=0, sa_type=Integer())

    # Reverse relationships
    texts_as_archdiocese: List["Text"] = Relationship(
        back_populates="origin_archdiocese",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_archdiocese_id]"}
    )
    texts_as_diocese: List["Text"] = Relationship(
        back_populates="origin_diocese",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_diocese_id]"}
    )


# ---------------------------------------------------------------------------
# Text  (Tab 3 — Corpus hagio)
# ---------------------------------------------------------------------------

class Text(Table, table=True):
    """
    One row per hagiographical text identified by a BHL number (or BHL vacat).
    Maps to Tab 3 "Corpus hagio" of the Excel file.
    """
    __table_args__ = _STRICT

    bhl_number: Optional[str] = _text(default=None, index=True)
    title: Optional[str] = _text(default=None)
    word_count: Optional[int] = Field(default=None, sa_type=Integer())

    # Repertory checks
    checked_bhl: Optional[int] = Field(default=None, sa_type=Integer())
    checked_isb: Optional[int] = Field(default=None, sa_type=Integer())
    checked_naso: Optional[int] = Field(default=None, sa_type=Integer())
    checked_dg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_philippart: Optional[int] = Field(default=None, sa_type=Integer())
    checked_secondary: Optional[int] = Field(default=None, sa_type=Integer())
    checked_leg: Optional[int] = Field(default=None, sa_type=Integer())

    # Chronology
    dating_quarter_century: Optional[str] = _text(default=None)
    dating_rough: Optional[str] = _text(default=None)  # maps to "Rough chronology"
    dating_precise: Optional[str] = _text(default=None)

    # Provenance of creation (Normalized)
    origin_archdiocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    origin_diocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    origin_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    origin_known: Optional[int] = Field(default=None, sa_type=Integer())

    # Primary destinatary (Normalized)
    primary_destinatary_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    destinatary_known: Optional[int] = Field(default=None, sa_type=Integer())

    # Author (Normalized)
    author_id: Optional[int] = Field(default=None, foreign_key="author.id")
    author_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    author_education_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    author_earlier_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    author_milieu_id: Optional[int] = Field(default=None, foreign_key="milieu.id")

    # Typology (Normalized)
    source_type_id: Optional[int] = Field(default=None, foreign_key="typology.id")
    subtype_id: Optional[int] = Field(default=None, foreign_key="typology.id")
    prose_or_verse: Optional[str] = _text(default=None)
    
    reecriture: Optional[int] = Field(default=None, sa_type=Integer())
    reecriture_of: Optional[str] = _text(default=None)
    based_on_pre880: Optional[int] = Field(default=None, sa_type=Integer())

    # New fields from tab audit
    code: Optional[str] = _text(default=None)
    origin_precise: Optional[int] = Field(default=None, sa_type=Integer())
    destinatary_precise: Optional[int] = Field(default=None, sa_type=Integer())
    author_locally_based: Optional[int] = Field(default=None, sa_type=Integer())

    # Edition / OCR
    preferred_edition: Optional[str] = _text(default=None)
    edition_link_aass: Optional[str] = _text(default=None)
    edition_link_other: Optional[str] = _text(default=None)
    edition_link_mgh: Optional[str] = _text(default=None)
    
    ocr_pre_1800: Optional[int] = Field(default=None, sa_type=Integer())
    ocr_post_1800: Optional[int] = Field(default=None, sa_type=Integer())
    
    has_full_ocr: Optional[int] = Field(default=None, sa_type=Integer())
    ocr_cleaned: Optional[int] = Field(default=None, sa_type=Integer())
    ocr_comments: Optional[str] = _text(default=None)
    
    edition_link_1: Optional[str] = _text(default=None)
    edition_link_2: Optional[str] = _text(default=None)

    key_bibliography: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    # Relationships
    manuscripts: List["Manuscript"] = Relationship(back_populates="text")
    editions: List["Edition"] = Relationship(back_populates="text")
    
    # Normalized relationships
    origin_archdiocese: Optional[ChurchEntity] = Relationship(
        back_populates="texts_as_archdiocese",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_archdiocese_id]"}
    )
    origin_diocese: Optional[ChurchEntity] = Relationship(
        back_populates="texts_as_diocese",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_diocese_id]"}
    )
    origin_location: Optional[Place] = Relationship(
        back_populates="texts",
        sa_relationship_kwargs={"foreign_keys": "[Text.origin_location_id]"}
    )
    primary_destinatary_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.primary_destinatary_location_id]"}
    )
    author_obj: Optional[Author] = Relationship(back_populates="texts")
    author_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.author_location_id]"}
    )
    author_education_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.author_education_location_id]"}
    )
    author_earlier_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.author_earlier_location_id]"}
    )
    milieu: Optional[Milieu] = Relationship()
    source_type: Optional[Typology] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.source_type_id]"}
    )
    subtype: Optional[Typology] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Text.subtype_id]"}
    )


# ---------------------------------------------------------------------------
# Manuscript  (Tab 1)
# ---------------------------------------------------------------------------

class Manuscript(Table, table=True):
    """
    One row per material witness (= one text in one physical book).
    Maps to Tab 1 "Manuscripts" of the Excel file.
    """
    __table_args__ = _STRICT

    ms_number_per_bhl: Optional[str] = _text(default=None)
    unique_id: Optional[int] = Field(default=None, unique=True, index=True)
    
    # New fields from tab audit
    bhl_number: Optional[str] = _text(default=None, index=True) # Unnamed first column
    title: Optional[str] = _text(default=None)
    
    collection_identifier: Optional[str] = _text(default=None)

    # Localization info from text (Normalized)
    text_archdiocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    text_bishopric_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    text_origin_id: Optional[int] = Field(default=None, foreign_key="place.id")

    checked_leg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_dg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_naso: Optional[int] = Field(default=None, sa_type=Integer())
    checked_ed_sec: Optional[int] = Field(default=None, sa_type=Integer())

    collection_location_id: Optional[int] = Field(default=None, foreign_key="place.id")
    heritage_institution_id: Optional[int] = Field(default=None, foreign_key="institution.id")
    shelfmark: Optional[str] = _text(default=None)
    folio_pages: Optional[str] = _text(default=None)

    dating_century: Optional[int] = Field(default=None, sa_type=Integer())
    dating_precise: Optional[str] = _text(default=None)

    provenance_general: Optional[str] = _text(default=None)
    provenance_archdiocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    provenance_diocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    provenance_institution_id: Optional[int] = Field(default=None, foreign_key="institution.id")
    vernacular_region: Optional[str] = _text(default=None)

    image_availability: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)
    witness_relation_notes: Optional[str] = _text(default=None) # index 30
    manuscript_type_id: Optional[int] = Field(default=None, foreign_key="manuscripttype.id")

    dimension_width_cm: Optional[float] = _real(default=None)
    dimension_height_cm: Optional[float] = _real(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="manuscripts")
    
    # Normalized relationships
    text_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.text_archdiocese_id]"}
    )
    text_bishopric: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.text_bishopric_id]"}
    )
    text_origin: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.text_origin_id]"}
    )
    collection_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.collection_location_id]"}
    )
    heritage_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.heritage_institution_id]"}
    )
    provenance_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.provenance_archdiocese_id]"}
    )
    provenance_diocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.provenance_diocese_id]"}
    )
    provenance_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Manuscript.provenance_institution_id]"}
    )
    manuscript_type: Optional[ManuscriptType] = Relationship()

    images: List["Image"] = Relationship(back_populates="manuscript")
    external_links: List["ManuscriptExternalResource"] = Relationship(
        back_populates="manuscript"
    )
    edition_links: List["EditionManuscript"] = Relationship(
        back_populates="manuscript"
    )
    
    # Relationships with other manuscripts (Copies/Exemplars)
    outgoing_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="source_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.source_manuscript_id]",
            "primaryjoin": "Manuscript.id == ManuscriptRelation.source_manuscript_id",
        },
    )
    incoming_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="target_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.target_manuscript_id]",
            "primaryjoin": "Manuscript.id == ManuscriptRelation.target_manuscript_id",
        },
    )


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class Image(Table, table=True):
    """
    An image linked to a manuscript.
    """
    __table_args__ = (
        UniqueConstraint("manuscript_id", "url"),
        _STRICT,
    )

    url: str = _text()
    image_type: str = _text()  # scan | iphone_photo | iiif
    comment: Optional[str] = _text(default=None)

    manuscript_id: Optional[int] = Field(default=None, foreign_key="manuscript.id")
    manuscript: Optional[Manuscript] = Relationship(back_populates="images")


# ---------------------------------------------------------------------------
# ExternalResource
# ---------------------------------------------------------------------------

class ExternalResource(Table, table=True):
    """
    Normalised external URL.
    """
    __table_args__ = (
        UniqueConstraint("url"),
        _STRICT,
    )

    url: str = _text()
    resource_type: str = _text() # iiif_scan | bollandist_catalog | catalog_link | scan | other
    comment: Optional[str] = _text(default=None)
    alive: int = Field(default=1, sa_type=Integer())

    manuscript_links: List["ManuscriptExternalResource"] = Relationship(
        back_populates="resource"
    )
    edition_links: List["EditionExternalResource"] = Relationship(
        back_populates="resource"
    )


# ---------------------------------------------------------------------------
# ManuscriptExternalResource  (M2M join)
# ---------------------------------------------------------------------------

class ManuscriptExternalResource(SQLModel, table=True):
    """Many-to-many join: Manuscript <-> ExternalResource."""
    __table_args__ = _STRICT

    manuscript_id: int = Field(foreign_key="manuscript.id", primary_key=True)
    resource_id: int = Field(foreign_key="externalresource.id", primary_key=True)

    manuscript: Manuscript = Relationship(back_populates="external_links")
    resource: ExternalResource = Relationship(back_populates="manuscript_links")


# ---------------------------------------------------------------------------
# EditionExternalResource  (M2M join)
# ---------------------------------------------------------------------------

class EditionExternalResource(SQLModel, table=True):
    """Many-to-many join: Edition <-> ExternalResource."""
    __table_args__ = _STRICT

    edition_id: int = Field(foreign_key="edition.id", primary_key=True)
    resource_id: int = Field(foreign_key="externalresource.id", primary_key=True)

    edition: "Edition" = Relationship(back_populates="external_resources")
    resource: ExternalResource = Relationship(back_populates="edition_links")


# ---------------------------------------------------------------------------
# ManuscriptRelation
# ---------------------------------------------------------------------------

class ManuscriptRelation(Table, table=True):
    """
    Normalised relation between two manuscripts.
    """
    __table_args__ = (
        UniqueConstraint("source_manuscript_id", "target_manuscript_id", "relation_type"),
        _STRICT,
    )

    source_manuscript_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", index=True
    )
    target_manuscript_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", index=True
    )
    relation_type: str = _text() # copy_of | exemplar_of
    certainty: Optional[str] = _text(default=None) # certain | probable | uncertain
    notes: Optional[str] = _text(default=None)
    source_reference: Optional[str] = _text(default=None)

    source_manuscript: Manuscript = Relationship(
        back_populates="outgoing_relations",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.source_manuscript_id]",
            "primaryjoin": "ManuscriptRelation.source_manuscript_id == Manuscript.id",
        },
    )
    target_manuscript: Manuscript = Relationship(
        back_populates="incoming_relations",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.target_manuscript_id]",
            "primaryjoin": "ManuscriptRelation.target_manuscript_id == Manuscript.id",
        },
    )


# ---------------------------------------------------------------------------
# Edition  (Tab 2)
# ---------------------------------------------------------------------------

class Edition(Table, table=True):
    """
    One row per edition of a hagiographical text.
    Maps to Tab 2 "Editions" of the Excel file.
    """
    __table_args__ = _STRICT

    bhl_number: Optional[str] = _text(default=None, index=True)
    title: Optional[str] = _text(default=None)
    edition_identifier: Optional[str] = _text(default=None)
    edition_reference_per_text: Optional[str] = _text(default=None) # Col 2

    checked_leg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_dg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_naso: Optional[int] = Field(default=None, sa_type=Integer())
    checked_ed_sec: Optional[int] = Field(default=None, sa_type=Integer())

    unique_id_numeric: Optional[int] = Field(default=None, sa_type=Integer())
    unique_id_descriptive: Optional[str] = _text(default=None)

    year_of_publication: Optional[int] = Field(default=None, sa_type=Integer())
    bibliographic_reference: Optional[str] = _text(default=None)
    page_range: Optional[str] = _text(default=None)

    is_reprint: Optional[int] = Field(default=None, sa_type=Integer())
    reprint_of: Optional[str] = _text(default=None)
    reprint_notes: Optional[str] = _text(default=None)

    has_scan: Optional[int] = Field(default=None, sa_type=Integer())
    has_transcription: Optional[int] = Field(default=None, sa_type=Integer())
    transcription_notes: Optional[str] = _text(default=None)
    collated: Optional[int] = Field(default=None, sa_type=Integer())

    edition_refs: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="editions")
    
    manuscript_links: List["EditionManuscript"] = Relationship(back_populates="edition")
    external_resources: List["EditionExternalResource"] = Relationship(
        back_populates="edition"
    )


# ---------------------------------------------------------------------------
# EditionManuscript  (M2M join with inspection_status)
# ---------------------------------------------------------------------------

class EditionManuscript(SQLModel, table=True):
    """
    Many-to-many join: Edition <-> Manuscript.
    """
    __table_args__ = _STRICT

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    manuscript_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )
    inspection_status: Optional[str] = _text(default="unknown")

    edition: Edition = Relationship(back_populates="manuscript_links")
    manuscript: Manuscript = Relationship(back_populates="edition_links")
