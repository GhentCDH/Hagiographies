# utilities/model.py
# ---------------------------------------------------------------------------
# SQLModel models for the Hagiographies project.
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
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)


class Institution(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    place: Optional[Place] = Relationship()


class Author(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    texts: List["Text"] = Relationship(back_populates="author_obj")


class Typology(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="typology.id")
    
    # Self-referential relationship fix
    parent: Optional["Typology"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Typology.id"}
    )
    children: List["Typology"] = Relationship(back_populates="parent")


class ManuscriptType(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class Milieu(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ChurchEntity(Table, table=True):
    __table_args__ = (UniqueConstraint("name", "is_archdiocese"), _STRICT)
    name: str = _text(index=True)
    is_archdiocese: int = Field(default=0, sa_type=Integer())


class ManuscriptIdentifier(Table, table=True):
    __table_args__ = (UniqueConstraint("title", "bhl_number"), _STRICT)
    title: str = _text(index=True)
    bhl_number: Optional[str] = _text(index=True)
    identifier: str = _text(index=True) 
    manuscripts: List["Manuscript"] = Relationship(back_populates="ms_identifier_obj")


class DatingCentury(Table, table=True):
    __table_args__ = (UniqueConstraint("century"), _STRICT)
    century: int = Field(index=True, sa_type=Integer())
    manuscripts: List["Manuscript"] = Relationship(back_populates="dating_century_rel")


class ImageAvailability(Table, table=True):
    __table_args__ = (UniqueConstraint("availability"), _STRICT)
    availability: str = _text(index=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="image_availability_rel")


class VernacularRegion(Table, table=True):
    __table_args__ = (UniqueConstraint("region"), _STRICT)
    region: str = _text(index=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="vernacular_region_rel")


class ProvenanceGeneral(Table, table=True):
    __table_args__ = (UniqueConstraint("description"), _STRICT)
    description: str = _text(index=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="provenance_general_rel")


class TextType(Table, table=True):
    """Normalized text type (e.g., Prose or Verse)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ImageType(Table, table=True):
    """Normalized image type (e.g., scan, iiif, iphone_photo)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


# ---------------------------------------------------------------------------
# M2M Join Tables (Defined EARLY for link_model compatibility)
# ---------------------------------------------------------------------------

class EditionManuscript(SQLModel, table=True):
    """Many-to-many join: Edition <-> Manuscript."""
    __table_args__ = _STRICT

    edition_id: int = Field(sa_type=Integer(), foreign_key="edition.id", primary_key=True)
    manuscript_id: int = Field(sa_type=Integer(), foreign_key="manuscript.id", primary_key=True)
    inspection_status: Optional[str] = _text(default="unknown")

    # Using strings for forward references to classes defined later
    edition: "Edition" = Relationship(back_populates="manuscript_links")
    manuscript: "Manuscript" = Relationship(back_populates="edition_links")


class ManuscriptExternalResource(SQLModel, table=True):
    """Many-to-many join: Manuscript <-> ExternalResource."""
    __table_args__ = _STRICT

    manuscript_id: int = Field(sa_type=Integer(), foreign_key="manuscript.id", primary_key=True)
    resource_id: int = Field(sa_type=Integer(), foreign_key="externalresource.id", primary_key=True)

    manuscript: "Manuscript" = Relationship(back_populates="external_links")
    resource: "ExternalResource" = Relationship(back_populates="manuscript_links")


class EditionExternalResource(SQLModel, table=True):
    """Many-to-many join: Edition <-> ExternalResource."""
    __table_args__ = _STRICT

    edition_id: int = Field(sa_type=Integer(), foreign_key="edition.id", primary_key=True)
    resource_id: int = Field(sa_type=Integer(), foreign_key="externalresource.id", primary_key=True)

    edition: "Edition" = Relationship(back_populates="external_resources")
    resource: "ExternalResource" = Relationship(back_populates="edition_links")


# ---------------------------------------------------------------------------
# Text  (Tab 3 — Corpus hagio)
# ---------------------------------------------------------------------------

class Text(Table, table=True):
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
    dating_rough: Optional[str] = _text(default=None)
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
    
    # TextType (Normalized from Prose or Verse)
    text_type_id: Optional[int] = Field(default=None, foreign_key="texttype.id")
    
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

    # Core Relationships
    manuscripts: List["Manuscript"] = Relationship(back_populates="text")
    editions: List["Edition"] = Relationship(back_populates="text")
    author_obj: Optional[Author] = Relationship(back_populates="texts")
    milieu: Optional[Milieu] = Relationship()
    
    # Typology & TextType Relationships (Fixed for uniqueness/admin UI)
    source_type: Optional[Typology] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.source_type_id == Typology.id", "uselist": False}
    )
    subtype: Optional[Typology] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.subtype_id == Typology.id", "uselist": False}
    )
    text_type: Optional[TextType] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.text_type_id == TextType.id", "uselist": False}
    )

    # Normalized relationships fixed with strict primaryjoin and uselist=False
    origin_archdiocese_rel: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.origin_archdiocese_id == ChurchEntity.id", "uselist": False}
    )
    origin_diocese_rel: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.origin_diocese_id == ChurchEntity.id", "uselist": False}
    )
    origin_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.origin_location_id == Place.id", "uselist": False}
    )
    primary_destinatary_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.primary_destinatary_location_id == Place.id", "uselist": False}
    )
    author_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.author_location_id == Place.id", "uselist": False}
    )
    author_education_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.author_education_location_id == Place.id", "uselist": False}
    )
    author_earlier_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Text.author_earlier_location_id == Place.id", "uselist": False}
    )


# ---------------------------------------------------------------------------
# Manuscript  (Tab 1)
# ---------------------------------------------------------------------------

class Manuscript(Table, table=True):
    __table_args__ = _STRICT

    ms_number_per_bhl: Optional[str] = _text(default=None)
    unique_id: Optional[int] = Field(default=None, unique=True, index=True)
    
    ms_identifier_id: Optional[int] = Field(default=None, foreign_key="manuscriptidentifier.id")
    ms_identifier_obj: Optional[ManuscriptIdentifier] = Relationship(back_populates="manuscripts")

    collection_identifier: Optional[str] = _text(default=None)

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

    dating_century_id: Optional[int] = Field(default=None, foreign_key="datingcentury.id")
    dating_century_rel: Optional[DatingCentury] = Relationship(back_populates="manuscripts")
    dating_precise: Optional[str] = _text(default=None)

    provenance_general_id: Optional[int] = Field(default=None, foreign_key="provenancegeneral.id")
    provenance_general_rel: Optional[ProvenanceGeneral] = Relationship(back_populates="manuscripts")
    provenance_archdiocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    provenance_diocese_id: Optional[int] = Field(default=None, foreign_key="churchentity.id")
    provenance_institution_id: Optional[int] = Field(default=None, foreign_key="institution.id")
    vernacular_region_id: Optional[int] = Field(default=None, foreign_key="vernacularregion.id")
    vernacular_region_rel: Optional[VernacularRegion] = Relationship(back_populates="manuscripts")

    image_availability_id: Optional[int] = Field(default=None, foreign_key="imageavailability.id")
    image_availability_rel: Optional[ImageAvailability] = Relationship(back_populates="manuscripts")
    notes: Optional[str] = _text(default=None)
    witness_relation_notes: Optional[str] = _text(default=None)
    manuscript_type_id: Optional[int] = Field(default=None, foreign_key="manuscripttype.id")

    dimension_width_cm: Optional[float] = _real(default=None)
    dimension_height_cm: Optional[float] = _real(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="manuscripts")
    
    # Link table relations
    images: List["Image"] = Relationship(back_populates="manuscript")
    external_links: List["ManuscriptExternalResource"] = Relationship(back_populates="manuscript")
    edition_links: List["EditionManuscript"] = Relationship(back_populates="manuscript")
    
    # Handig voor uitlezen in Python, nu met de direct meegegeven Class
    editions_direct: List["Edition"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={"overlaps": "edition_links,manuscript"}
    )

    # Relationships with explicit uselist=False to fix admin panels
    text_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.text_archdiocese_id == ChurchEntity.id", "uselist": False}
    )
    text_bishopric: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.text_bishopric_id == ChurchEntity.id", "uselist": False}
    )
    text_origin: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.text_origin_id == Place.id", "uselist": False}
    )
    collection_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.collection_location_id == Place.id", "uselist": False}
    )
    heritage_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.heritage_institution_id == Institution.id", "uselist": False}
    )
    provenance_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.provenance_archdiocese_id == ChurchEntity.id", "uselist": False}
    )
    provenance_diocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.provenance_diocese_id == ChurchEntity.id", "uselist": False}
    )
    provenance_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.provenance_institution_id == Institution.id", "uselist": False}
    )
    manuscript_type: Optional[ManuscriptType] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Manuscript.manuscript_type_id == ManuscriptType.id", "uselist": False}
    )

    # Best-practice relations to other manuscripts (no double primaryjoin)
    outgoing_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="source_manuscript",
        sa_relationship_kwargs={"foreign_keys": "[ManuscriptRelation.source_manuscript_id]"}
    )
    incoming_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="target_manuscript",
        sa_relationship_kwargs={"foreign_keys": "[ManuscriptRelation.target_manuscript_id]"}
    )


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class Image(Table, table=True):
    __table_args__ = (
        UniqueConstraint("manuscript_id", "url"),
        _STRICT,
    )

    url: str = _text()
    comment: Optional[str] = _text(default=None)

    # Normalized ImageType
    image_type_id: Optional[int] = Field(default=None, foreign_key="imagetype.id")
    image_type: Optional[ImageType] = Relationship(
        sa_relationship_kwargs={"primaryjoin": "Image.image_type_id == ImageType.id", "uselist": False}
    )

    manuscript_id: Optional[int] = Field(default=None, foreign_key="manuscript.id")
    manuscript: Optional[Manuscript] = Relationship(back_populates="images")


# ---------------------------------------------------------------------------
# ExternalResource
# ---------------------------------------------------------------------------

class ExternalResource(Table, table=True):
    __table_args__ = (UniqueConstraint("url"), _STRICT)

    url: str = _text()
    resource_type: str = _text()
    comment: Optional[str] = _text(default=None)
    alive: int = Field(default=1, sa_type=Integer())

    manuscript_links: List["ManuscriptExternalResource"] = Relationship(back_populates="resource")
    edition_links: List["EditionExternalResource"] = Relationship(back_populates="resource")


# ---------------------------------------------------------------------------
# ManuscriptRelation
# ---------------------------------------------------------------------------

class ManuscriptRelation(Table, table=True):
    __table_args__ = (
        UniqueConstraint("source_manuscript_id", "target_manuscript_id", "relation_type"),
        _STRICT,
    )

    source_manuscript_id: int = Field(sa_type=Integer(), foreign_key="manuscript.id", index=True)
    target_manuscript_id: int = Field(sa_type=Integer(), foreign_key="manuscript.id", index=True)
    relation_type: str = _text()
    certainty: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)
    source_reference: Optional[str] = _text(default=None)

    source_manuscript: Manuscript = Relationship(
        back_populates="outgoing_relations",
        sa_relationship_kwargs={"foreign_keys": "[ManuscriptRelation.source_manuscript_id]"}
    )
    target_manuscript: Manuscript = Relationship(
        back_populates="incoming_relations",
        sa_relationship_kwargs={"foreign_keys": "[ManuscriptRelation.target_manuscript_id]"}
    )


# ---------------------------------------------------------------------------
# Edition  (Tab 2)
# ---------------------------------------------------------------------------

class Edition(Table, table=True):
    __table_args__ = _STRICT

    bhl_number: Optional[str] = _text(default=None, index=True)
    title: Optional[str] = _text(default=None)
    edition_identifier: Optional[str] = _text(default=None)
    edition_reference_per_text: Optional[str] = _text(default=None)

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
    reprint_identically_typeset: Optional[int] = Field(default=None, sa_type=Integer())
    reprint_newly_typeset: Optional[int] = Field(default=None, sa_type=Integer())
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
    external_resources: List["EditionExternalResource"] = Relationship(back_populates="edition")
    
    # Handig voor uitlezen in Python, nu met de direct meegegeven Class
    manuscripts_direct: List["Manuscript"] = Relationship(link_model=EditionManuscript)