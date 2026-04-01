# utilities/model.py
# ---------------------------------------------------------------------------
# SQLModel models for the Hagiographies project.
#
# Changelog vs. previous version:
#   - Introduced ManuscriptText as a proper M2M join table between Manuscript
#     and Text.  The old Manuscript.text_id FK (1:N) is gone.
#   - Fields that are specific to a *particular text inside a particular
#     manuscript* (ms_number_per_bhl, folio_pages, text_archdiocese_id,
#     text_bishopric_id, text_origin_id) have been moved onto ManuscriptText,
#     where they semantically belong.
#   - Manuscript no longer has any FK pointing at Text, which eliminates the
#     duplicate-row problem caused by SQLAlchemy joining the same ChurchEntity
#     table via multiple FK paths on the same parent table.
#   - All other M2M join tables (EditionManuscript, ManuscriptExternalResource,
#     EditionExternalResource) are unchanged.
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
    name: str = _text(index=True)


class Typology(Table, table=True):
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="typology.id")

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
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ManuscriptIdentifier(Table, table=True):
    __table_args__ = (UniqueConstraint("title", "bhl_number"), _STRICT)
    title: str = _text(index=True)
    bhl_number: Optional[str] = _text(index=True)
    identifier: str = _text(index=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="ms_identifier_obj")


class DatingCentury(Table, table=True):
    __table_args__ = (UniqueConstraint("century"), _STRICT)
    century: int = Field(index=True, sa_type=Integer())


class ImageAvailability(Table, table=True):
    __table_args__ = (UniqueConstraint("availability"), _STRICT)
    availability: str = _text(index=True)


class VernacularRegion(Table, table=True):
    __table_args__ = (UniqueConstraint("region"), _STRICT)
    region: str = _text(index=True)


class ProvenanceGeneral(Table, table=True):
    __table_args__ = (UniqueConstraint("description"), _STRICT)
    description: str = _text(index=True)


class TextType(Table, table=True):
    """Normalized text type (e.g., Prose or Verse)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ImageType(Table, table=True):
    """Normalized image type (e.g., scan, iiif, iphone_photo)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


# ---------------------------------------------------------------------------
# M2M Join Tables  (defined early — required by link_model= references)
# ---------------------------------------------------------------------------

class ManuscriptText(SQLModel, table=True):
    """Many-to-many: Manuscript <-> Text.

    Fields that are specific to *one text occurring inside one manuscript*
    live here rather than on Manuscript itself, which previously caused
    duplicate rows when SQLAlchemy followed multiple FK paths back to the
    same ChurchEntity / Place table.
    """
    __table_args__ = (
        UniqueConstraint("ms_id", "text_id"),
        _STRICT,
    )

    ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )
    text_id: int = Field(
        sa_type=Integer(), foreign_key="text.id", primary_key=True
    )

    # Per-occurrence metadata (was on Manuscript in the old schema)
    ms_number_per_bhl: Optional[str] = _text(default=None)
    folio_pages: Optional[str] = _text(default=None)

    # Ecclesiastical context of *this text* in *this manuscript*
    # (one ChurchEntity FK per role → no more multi-FK fan-out on Manuscript)
    text_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    text_bishopric_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    text_origin_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )

    # Relationships back to parent tables
    manuscript: "Manuscript" = Relationship(
        back_populates="text_links",
        sa_relationship_kwargs={
            "overlaps": "texts_direct",
            "foreign_keys": "[ManuscriptText.ms_id]"
        }
    )
    text: "Text" = Relationship(
        back_populates="manuscript_links",
        sa_relationship_kwargs={
            "overlaps": "manuscripts_direct",
            "foreign_keys": "[ManuscriptText.text_id]"
        }
    )


class EditionManuscript(SQLModel, table=True):
    """Many-to-many join: Edition <-> Manuscript."""
    __table_args__ = _STRICT

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )

    inspection_status: Optional[str] = _text(default="unknown")

    edition: "Edition" = Relationship(
        back_populates="manuscript_links",
        sa_relationship_kwargs={
            "overlaps": "editions_direct,manuscripts_direct",
            "foreign_keys": "[EditionManuscript.edition_id]"
        }
    )
    manuscript: "Manuscript" = Relationship(
        back_populates="edition_links",
        sa_relationship_kwargs={
            "overlaps": "editions_direct,manuscripts_direct",
            "foreign_keys": "[EditionManuscript.ms_id]"
        }
    )


class ManuscriptExternalResource(SQLModel, table=True):
    """Many-to-many join: Manuscript <-> ExternalResource."""
    __table_args__ = _STRICT

    ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )
    resource_id: int = Field(
        sa_type=Integer(), foreign_key="externalresource.id", primary_key=True
    )

    manuscript: "Manuscript" = Relationship(
        back_populates="external_links",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptExternalResource.ms_id]"
        }
    )

    resource: "ExternalResource" = Relationship(back_populates="manuscript_links")


class EditionExternalResource(SQLModel, table=True):
    """Many-to-many join: Edition <-> ExternalResource."""
    __table_args__ = _STRICT

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    resource_id: int = Field(
        sa_type=Integer(), foreign_key="externalresource.id", primary_key=True
    )

    edition: "Edition" = Relationship(back_populates="external_resources")
    resource: "ExternalResource" = Relationship(back_populates="edition_links")


# ---------------------------------------------------------------------------
# Text (Tab 3 — Corpus hagio)
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
    dating_rough: Optional[str] = _text(default=None)
    dating_precise: Optional[str] = _text(default=None)

    # Provenance of creation (Normalized)
    origin_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_diocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    origin_known: Optional[int] = Field(default=None, sa_type=Integer())

    # Primary destinatary (Normalized)
    primary_destinatary_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    destinatary_known: Optional[int] = Field(default=None, sa_type=Integer())

    # Author (Normalized)
    author_id: Optional[int] = Field(default=None, foreign_key="author.id")
    author_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    author_education_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    author_earlier_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    author_milieu_id: Optional[int] = Field(
        default=None, foreign_key="milieu.id"
    )

    # Typology (Normalized)
    source_type_id: Optional[int] = Field(
        default=None, foreign_key="typology.id"
    )
    subtype_id: Optional[int] = Field(default=None, foreign_key="typology.id")

    # TextType (Normalized — Prose or Verse)
    text_type_id: Optional[int] = Field(
        default=None, foreign_key="texttype.id"
    )

    reecriture: Optional[int] = Field(default=None, sa_type=Integer())
    reecriture_of: Optional[str] = _text(default=None)
    based_on_pre880: Optional[int] = Field(default=None, sa_type=Integer())

    # Additional fields
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

    # --- Relationships ---

    # M2M with Manuscript via ManuscriptText join table
    manuscript_links: List["ManuscriptText"] = Relationship(
        back_populates="text",
        sa_relationship_kwargs={
            "overlaps": "manuscripts_direct",
            "primaryjoin": "Text.id == ManuscriptText.text_id"
        }
    )
    manuscripts_direct: List["Manuscript"] = Relationship(
        link_model=ManuscriptText,
        sa_relationship_kwargs={
            "overlaps": "manuscript_links,text,manuscript,texts_direct",
            "primaryjoin": "Text.id == ManuscriptText.text_id",
            "secondaryjoin": "Manuscript.id == ManuscriptText.ms_id"
        }
    )

    # Direct Edition relationship (1:N — an Edition belongs to one Text)
    editions: List["Edition"] = Relationship(back_populates="text")

    # Relationship back to author
    author_obj: Optional[Author] = Relationship()
    milieu: Optional[Milieu] = Relationship()

    # Typology & TextType
    source_type: Optional[Typology] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.source_type_id == Typology.id",
            "uselist": False,
        }
    )
    subtype: Optional[Typology] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.subtype_id == Typology.id",
            "uselist": False,
        }
    )
    text_type: Optional[TextType] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.text_type_id == TextType.id",
            "uselist": False,
        }
    )

    # Origin / destinatary places
    origin_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.origin_archdiocese_id == ChurchEntity.id",
            "uselist": False,
            "overlaps": "origin_diocese",
        }
    )
    origin_diocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.origin_diocese_id == ChurchEntity.id",
            "uselist": False,
            "overlaps": "origin_archdiocese",
        }
    )
    origin_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.origin_location_id == Place.id",
            "uselist": False,
        }
    )
    primary_destinatary_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.primary_destinatary_location_id == Place.id",
            "uselist": False,
        }
    )
    author_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.author_location_id == Place.id",
            "uselist": False,
        }
    )
    author_education_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.author_education_location_id == Place.id",
            "uselist": False,
        }
    )
    author_earlier_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.author_earlier_location_id == Place.id",
            "uselist": False,
        }
    )


# ---------------------------------------------------------------------------
# Manuscript (Tab 1)
# ---------------------------------------------------------------------------

class Manuscript(Table, table=True):
    """A physical manuscript witness.

    Text-specific metadata (archdiocese, bishopric, text origin, folio pages,
    ms_number_per_bhl) now lives on ManuscriptText — the M2M join table —
    because those values are properties of *one text in one manuscript*, not
    of the manuscript itself.
    """
    __table_args__ = _STRICT

    unique_id: Optional[int] = Field(default=None, unique=True, index=True)

    ms_identifier_id: Optional[int] = Field(
        default=None, foreign_key="manuscriptidentifier.id"
    )
    ms_identifier_obj: Optional[ManuscriptIdentifier] = Relationship(
        back_populates="manuscripts"
    )

    collection_identifier: Optional[str] = _text(default=None)

    # Check flags
    checked_leg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_dg: Optional[int] = Field(default=None, sa_type=Integer())
    checked_naso: Optional[int] = Field(default=None, sa_type=Integer())
    checked_ed_sec: Optional[int] = Field(default=None, sa_type=Integer())

    # Physical location / holding institution
    collection_location_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    heritage_institution_id: Optional[int] = Field(
        default=None, foreign_key="institution.id"
    )
    shelfmark: Optional[str] = _text(default=None)


    # Dating
    dating_century_id: Optional[int] = Field(
        default=None, foreign_key="datingcentury.id"
    )
    dating_century: Optional[DatingCentury] = Relationship()
    dating_precise: Optional[str] = _text(default=None)

    # Provenance
    provenance_general_id: Optional[int] = Field(
        default=None, foreign_key="provenancegeneral.id"
    )
    provenance_general: Optional[ProvenanceGeneral] = Relationship()
    provenance_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    provenance_diocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    provenance_institution_id: Optional[int] = Field(
        default=None, foreign_key="institution.id"
    )

    vernacular_region_id: Optional[int] = Field(
        default=None, foreign_key="vernacularregion.id"
    )
    vernacular_region: Optional[VernacularRegion] = Relationship()

    image_availability_id: Optional[int] = Field(
        default=None, foreign_key="imageavailability.id"
    )
    image_availability: Optional[ImageAvailability] = Relationship()

    notes: Optional[str] = _text(default=None)
    witness_relation_notes: Optional[str] = _text(default=None)
    manuscript_type_id: Optional[int] = Field(
        default=None, foreign_key="manuscripttype.id"
    )

    dimension_width_cm: Optional[float] = _real(default=None)
    dimension_height_cm: Optional[float] = _real(default=None)

    # --- Relationships ---

    # M2M with Text via ManuscriptText join table
    text_links: List["ManuscriptText"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={
            "overlaps": "texts_direct,manuscripts_direct",
            "primaryjoin": "Manuscript.id == ManuscriptText.ms_id"
        }
    )
    texts_direct: List["Text"] = Relationship(
        link_model=ManuscriptText,
        sa_relationship_kwargs={
            "overlaps": "text_links,manuscript,manuscript_links,text,texts_direct",
            "primaryjoin": "Manuscript.id == ManuscriptText.ms_id",
            "secondaryjoin": "Text.id == ManuscriptText.text_id"
        }
    )

    external_links: List["ManuscriptExternalResource"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.id == ManuscriptExternalResource.ms_id"
        }
    )

    images: List["Image"] = Relationship(back_populates="manuscript")
    edition_links: List["EditionManuscript"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"overlaps": "editions_direct,manuscripts_direct"}
    )
    editions_direct: List["Edition"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={"overlaps": "edition_links,manuscript"}
    )

    # Single-value relationships (uselist=False prevents list confusion)
    collection_location: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.collection_location_id == Place.id",
            "uselist": False,
        }
    )
    heritage_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.heritage_institution_id == Institution.id",
            "uselist": False,
        }
    )
    provenance_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.provenance_archdiocese_id == ChurchEntity.id",
            "uselist": False,
        }
    )
    provenance_diocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.provenance_diocese_id == ChurchEntity.id",
            "uselist": False,
        }
    )
    provenance_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.provenance_institution_id == Institution.id",
            "uselist": False,
        }
    )
    manuscript_type: Optional[ManuscriptType] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.manuscript_type_id == ManuscriptType.id",
            "uselist": False,
        }
    )

    # Manuscript-to-manuscript relations
    outgoing_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="source_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.source_ms_id]"
        }
    )
    incoming_relations: List["ManuscriptRelation"] = Relationship(
        back_populates="target_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.target_ms_id]"
        }
    )


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class Image(Table, table=True):
    __table_args__ = (
        UniqueConstraint("ms_id", "url"),
        _STRICT,
    )

    url: str = _text()
    comment: Optional[str] = _text(default=None)

    image_type_id: Optional[int] = Field(
        default=None, foreign_key="imagetype.id"
    )
    image_type: Optional[ImageType] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Image.image_type_id == ImageType.id",
            "uselist": False,
        }
    )

    ms_id: Optional[int] = Field(
        default=None, foreign_key="manuscript.id"
    )
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

    manuscript_links: List["ManuscriptExternalResource"] = Relationship(
        back_populates="resource"
    )
    edition_links: List["EditionExternalResource"] = Relationship(
        back_populates="resource"
    )


# ---------------------------------------------------------------------------
# ManuscriptRelation
# ---------------------------------------------------------------------------

class ManuscriptRelation(Table, table=True):
    __table_args__ = (
        UniqueConstraint(
            "source_ms_id", "target_ms_id", "relation_type"
        ),
        _STRICT,
    )

    source_ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", index=True
    )
    target_ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", index=True
    )
    relation_type: str = _text()
    certainty: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)
    source_reference: Optional[str] = _text(default=None)

    source_manuscript: Manuscript = Relationship(
        back_populates="outgoing_relations",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.source_ms_id]"
        }
    )
    target_manuscript: Manuscript = Relationship(
        back_populates="incoming_relations",
        sa_relationship_kwargs={
            "foreign_keys": "[ManuscriptRelation.target_ms_id]"
        }
    )


# ---------------------------------------------------------------------------
# Edition  (Tab 2)
# ---------------------------------------------------------------------------

class Edition(Table, table=True):
    __table_args__ = (UniqueConstraint("unique_id_numeric"), _STRICT)

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
    reprint_identically_typeset: Optional[int] = Field(
        default=None, sa_type=Integer()
    )
    reprint_newly_typeset: Optional[int] = Field(
        default=None, sa_type=Integer()
    )
    reprint_of: Optional[str] = _text(default=None)

    has_scan: Optional[int] = Field(default=None, sa_type=Integer())
    has_transcription: Optional[int] = Field(default=None, sa_type=Integer())
    transcription_our_ed: Optional[int] = Field(default=None, sa_type=Integer())
    transcription_notes: Optional[str] = _text(default=None)
    collated: Optional[int] = Field(default=None, sa_type=Integer())
    reprint_notes: Optional[str] = _text(default=None)
    edition_refs: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="editions")

    manuscript_links: List["EditionManuscript"] = Relationship(
        back_populates="edition",
        sa_relationship_kwargs={"overlaps": "editions_direct,manuscripts_direct"}
    )

    external_resources: List["EditionExternalResource"] = Relationship(
        back_populates="edition"
    )

    manuscripts_direct: List["Manuscript"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={
            "overlaps": "edition_links,manuscript,editions_direct,manuscript_links,edition"
        }
    )
