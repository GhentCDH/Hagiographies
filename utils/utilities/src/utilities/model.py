# utilities/model.py
# ---------------------------------------------------------------------------
# SQLModel models for the Hagiographies project.
#
# Schema revision (refactor):
#   - All pseudo-boolean INT columns replaced with native Optional[bool].
#   - Boolean field names now consistently prefixed: is_*, has_*, checked_*.
#   - Author receives place/milieu metadata (place_id, education_place_id,
#     earlier_place_id, milieu_id) that previously lived on Text.
#   - ImageAvailability lookup table removed; image presence is derivable
#     from Image records directly.
#   - Text.origin_known and Text.destinatary_known removed (computable).
#   - Edition.checked_leg removed (unused).
#   - Edition.has_scan removed (derivable from ExternalResource).
#   - Edition.reprint_identically_typeset + reprint_newly_typeset collapsed
#     into Edition.reprint_type (ReprintType enum).
#   - Text.reecriture / reecriture_of renamed to is_rewrite / rewrite_of_bhl.
#   - All relationship suffixes cleaned up: _obj → plain name,
#     _links → _associations, _direct → plain plural.
#   - ManuscriptText M2M join table and its per-occurrence metadata unchanged.
# ---------------------------------------------------------------------------

from enum import Enum
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


def _bool(**kwargs):
    """INTEGER column — BOOLEAN is not STRICT-compatible."""
    return Field(sa_type=Integer(), **kwargs)


# ==============================================================================
# ENUMS
# ==============================================================================

class ExternalResourceType(str, Enum):
    """Supported external resource types for manuscripts and editions."""
    iiif_scan = "iiif_scan"
    bollandist_catalog = "bollandist_catalog"
    catalog_link = "catalog_link"
    scan = "scan"
    other = "other"


class RelationType(str, Enum):
    """Directed relationship types between manuscript witnesses.

    Relationships are stored unidirectionally (e.g. MS-A copy_of MS-B).
    """
    copy_of = "copy_of"
    exemplar_of = "exemplar_of"
    other = "other"


class Certainty(str, Enum):
    """Certainty level for a manuscript-to-manuscript relation."""
    certain = "certain"
    probable = "probable"
    uncertain = "uncertain"


class ReprintType(str, Enum):
    """How a reprint edition was set relative to the original."""
    identically_typeset = "identically_typeset"
    newly_typeset = "newly_typeset"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Table(SQLModel):
    """Base class: auto primary key + audit timestamps."""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )


# ---------------------------------------------------------------------------
# Normalized Lookup Tables
# ---------------------------------------------------------------------------

class Place(Table, table=True):
    """A geographic location, optionally enriched with GPS coordinates."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)


class Institution(Table, table=True):
    """A heritage or educational institution, optionally linked to a place."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    place: Optional[Place] = Relationship()


class Milieu(Table, table=True):
    """The intellectual or social milieu associated with an author or text."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class Author(Table, table=True):
    """A hagiographic text author with optional place and milieu metadata.

    The location fields capture the author's context: place of activity,
    place of education, earlier place, and intellectual milieu.  These fields
    were moved here from Text so that the same author is enriched once rather
    than repeated per text.
    """
    name: str = _text(index=True)

    place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    education_place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    earlier_place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    milieu_id: Optional[int] = Field(default=None, foreign_key="milieu.id")

    place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Author.place_id == Place.id",
            "uselist": False,
        }
    )
    education_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Author.education_place_id == Place.id",
            "uselist": False,
        }
    )
    earlier_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Author.earlier_place_id == Place.id",
            "uselist": False,
        }
    )
    milieu: Optional[Milieu] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Author.milieu_id == Milieu.id",
            "uselist": False,
        }
    )


class Typology(Table, table=True):
    """Hierarchical source typology (e.g. Vita > Passio)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="typology.id")

    parent: Optional["Typology"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Typology.id"}
    )
    children: List["Typology"] = Relationship(back_populates="parent")


class ManuscriptType(Table, table=True):
    """Type classification for a manuscript (e.g. legendarium, collectio)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ChurchEntity(Table, table=True):
    """Ecclesiastical entity: archdiocese, diocese, or bishopric."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ManuscriptIdentifier(Table, table=True):
    """A canonical title + BHL identifier combination for a manuscript group."""
    __table_args__ = (UniqueConstraint("title", "bhl_number"), _STRICT)
    title: str = _text(index=True)
    bhl_number: Optional[str] = _text(index=True)
    identifier: str = _text(index=True)
    manuscripts: List["Manuscript"] = Relationship(back_populates="ms_identifier")


class DatingCentury(Table, table=True):
    """A century used for manuscript dating (stored as integer, e.g. 10 for Xth c.)."""
    __table_args__ = (UniqueConstraint("century"), _STRICT)
    century: int = Field(index=True, sa_type=Integer())


class VernacularRegion(Table, table=True):
    """Vernacular region category (e.g. Romance, Germanic)."""
    __table_args__ = (UniqueConstraint("region"), _STRICT)
    region: str = _text(index=True)


class ProvenanceGeneral(Table, table=True):
    """General provenance description for a manuscript."""
    __table_args__ = (UniqueConstraint("description"), _STRICT)
    description: str = _text(index=True)


class TextType(Table, table=True):
    """Prose vs. verse classification for a hagiographic text."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


class ImageType(Table, table=True):
    """Image delivery type (e.g. iiif, scan, iphone_photo)."""
    __table_args__ = (UniqueConstraint("name"), _STRICT)
    name: str = _text(index=True)


# ---------------------------------------------------------------------------
# M2M Join Tables  (defined early — required by link_model= references)
# ---------------------------------------------------------------------------

class ManuscriptText(SQLModel, table=True):
    """Many-to-many join: Manuscript ↔ Text.

    Fields that are specific to *one text occurring inside one manuscript*
    (folio pages, per-BHL number, ecclesiastical context) live here rather
    than on Manuscript or Text.
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

    ms_number_per_bhl: Optional[str] = _text(default=None)
    folio_pages: Optional[str] = _text(default=None)

    text_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    text_bishopric_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    text_origin_place_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )

    manuscript: "Manuscript" = Relationship(
        back_populates="text_associations",
        sa_relationship_kwargs={
            "overlaps": "texts",
            "foreign_keys": "[ManuscriptText.ms_id]"
        }
    )
    text: "Text" = Relationship(
        back_populates="manuscript_associations",
        sa_relationship_kwargs={
            "overlaps": "manuscripts",
            "foreign_keys": "[ManuscriptText.text_id]"
        }
    )


class EditionManuscript(SQLModel, table=True):
    """Many-to-many join: Edition ↔ Manuscript, with inspection metadata."""
    __table_args__ = _STRICT

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )

    inspection_status: Optional[str] = _text(default="unknown")

    edition: "Edition" = Relationship(
        back_populates="manuscript_associations",
        sa_relationship_kwargs={
            "overlaps": "editions,manuscripts",
            "foreign_keys": "[EditionManuscript.edition_id]"
        }
    )
    manuscript: "Manuscript" = Relationship(
        back_populates="edition_associations",
        sa_relationship_kwargs={
            "overlaps": "editions,manuscripts",
            "foreign_keys": "[EditionManuscript.ms_id]"
        }
    )


class EditionExternalResource(SQLModel, table=True):
    """Many-to-many join: Edition ↔ ExternalResource (e.g. scan links)."""
    __table_args__ = _STRICT

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    resource_id: int = Field(
        sa_type=Integer(), foreign_key="external_resource.id", primary_key=True
    )

    edition: "Edition" = Relationship(back_populates="external_resources")
    resource: "ExternalResource" = Relationship(back_populates="edition_associations")


class ExternalResource(SQLModel, table=True):
    """An external hyperlink or resource associated with a manuscript or edition.

    The URL is extracted from the Excel hyperlink target; the display text is
    discarded.  Scan links for editions are linked via EditionExternalResource.
    """
    __tablename__ = "external_resource"
    __table_args__ = (
        UniqueConstraint("manuscript_id", "url", name="uix_manuscript_url"),
        _STRICT
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: Optional[int] = Field(
        default=None, foreign_key="manuscript.id"
    )
    url: str = _text(index=True)
    resource_type: ExternalResourceType = _text(default=ExternalResourceType.other)
    comment: Optional[str] = _text(default=None)
    is_alive: bool = _bool(default=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
    )

    manuscript: "Manuscript" = Relationship(back_populates="external_resources")
    edition_associations: List["EditionExternalResource"] = Relationship(
        back_populates="resource"
    )


class ManuscriptRelation(SQLModel, table=True):
    """A directed relationship (copy, exemplar) between two manuscript witnesses.

    Relationships are stored unidirectionally: the source is the dependent
    manuscript and the target is the archetype.
    """
    __tablename__ = "manuscript_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_manuscript_id",
            "target_manuscript_id",
            "relation_type",
            name="uix_source_target_relation"
        ),
        _STRICT
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_manuscript_id: int = Field(foreign_key="manuscript.id")
    target_manuscript_id: int = Field(foreign_key="manuscript.id")
    relation_type: RelationType = _text(default=RelationType.other)
    certainty: Certainty = _text(default=Certainty.uncertain)
    notes: Optional[str] = _text(default=None)
    source_reference: Optional[str] = _text(default=None)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_type=SAText(),
    )

    source_manuscript: "Manuscript" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "ManuscriptRelation.source_manuscript_id==Manuscript.id",
            "back_populates": "outgoing_relations"
        }
    )
    target_manuscript: "Manuscript" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "ManuscriptRelation.target_manuscript_id==Manuscript.id",
            "back_populates": "incoming_relations"
        }
    )


# ---------------------------------------------------------------------------
# Text  (Tab 3 — Corpus hagio)
# ---------------------------------------------------------------------------

class Text(Table, table=True):
    """A hagiographic text entry identified by its BHL number.

    Author location and milieu data now live on Author; origin_known and
    destinatary_known are computable from the presence of origin/destinatary
    place FKs and are therefore omitted.
    """
    __table_args__ = _STRICT

    bhl_number: Optional[str] = _text(default=None, index=True)
    title: Optional[str] = _text(default=None)
    word_count: Optional[int] = Field(default=None, sa_type=Integer())

    # Repertory checks
    checked_bhl: Optional[bool] = _bool(default=None)
    checked_isb: Optional[bool] = _bool(default=None)
    checked_naso: Optional[bool] = _bool(default=None)
    checked_dg: Optional[bool] = _bool(default=None)
    checked_philippart: Optional[bool] = _bool(default=None)
    checked_secondary: Optional[bool] = _bool(default=None)
    checked_leg: Optional[bool] = _bool(default=None)

    # Chronology
    dating_rough: Optional[str] = _text(default=None)
    dating_precise: Optional[str] = _text(default=None)

    # Provenance of creation
    origin_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_diocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_place_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )

    # Primary destinatary
    primary_destinatary_place_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )

    # Author (FK only; location/milieu now on Author)
    author_id: Optional[int] = Field(default=None, foreign_key="author.id")

    # Typology
    source_type_id: Optional[int] = Field(
        default=None, foreign_key="typology.id"
    )
    subtype_id: Optional[int] = Field(default=None, foreign_key="typology.id")

    # Text type (Prose / Verse)
    text_type_id: Optional[int] = Field(
        default=None, foreign_key="texttype.id"
    )

    is_rewrite: Optional[bool] = _bool(default=None)
    rewrite_of_bhl: Optional[str] = _text(default=None)
    is_based_on_pre880: Optional[bool] = _bool(default=None)

    # Precision flags
    code: Optional[str] = _text(default=None)
    is_origin_precise: Optional[bool] = _bool(default=None)
    is_destinatary_precise: Optional[bool] = _bool(default=None)
    is_author_locally_based: Optional[bool] = _bool(default=None)

    # Edition / OCR
    preferred_edition: Optional[str] = _text(default=None)
    edition_link_aass: Optional[str] = _text(default=None)
    edition_link_other: Optional[str] = _text(default=None)
    edition_link_mgh: Optional[str] = _text(default=None)

    is_ocr_pre_1800: Optional[bool] = _bool(default=None)
    is_ocr_post_1800: Optional[bool] = _bool(default=None)
    has_full_ocr: Optional[bool] = _bool(default=None)
    is_ocr_cleaned: Optional[bool] = _bool(default=None)
    ocr_comments: Optional[str] = _text(default=None)

    edition_link_1: Optional[str] = _text(default=None)
    edition_link_2: Optional[str] = _text(default=None)

    key_bibliography: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    # --- Relationships ---

    manuscript_associations: List["ManuscriptText"] = Relationship(
        back_populates="text",
        sa_relationship_kwargs={
            "overlaps": "manuscripts",
            "primaryjoin": "Text.id == ManuscriptText.text_id"
        }
    )
    manuscripts: List["Manuscript"] = Relationship(
        link_model=ManuscriptText,
        sa_relationship_kwargs={
            "overlaps": "manuscript_associations,text,manuscript,text_associations,manuscripts",
            "primaryjoin": "Text.id == ManuscriptText.text_id",
            "secondaryjoin": "Manuscript.id == ManuscriptText.ms_id"
        }
    )

    editions: List["Edition"] = Relationship(back_populates="text")

    author: Optional[Author] = Relationship()

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
    origin_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.origin_place_id == Place.id",
            "uselist": False,
        }
    )
    primary_destinatary_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Text.primary_destinatary_place_id == Place.id",
            "uselist": False,
        }
    )


# ---------------------------------------------------------------------------
# Manuscript  (Tab 1)
# ---------------------------------------------------------------------------

class Manuscript(Table, table=True):
    """A physical manuscript witness.

    Text-specific metadata (archdiocese, bishopric, text origin, folio pages,
    ms_number_per_bhl) lives on ManuscriptText — the M2M join table — because
    those values belong to *one text in one manuscript*, not to the manuscript
    itself.

    Image availability is no longer stored as a lookup FK; it is derivable
    from the presence of Image records.
    """
    __table_args__ = _STRICT

    unique_id: Optional[int] = Field(default=None, unique=True, index=True)

    ms_identifier_id: Optional[int] = Field(
        default=None, foreign_key="manuscriptidentifier.id"
    )
    ms_identifier: Optional[ManuscriptIdentifier] = Relationship(
        back_populates="manuscripts"
    )

    collection_identifier: Optional[str] = _text(default=None)

    # Repertory check flags
    checked_leg: Optional[bool] = _bool(default=None)
    checked_dg: Optional[bool] = _bool(default=None)
    checked_naso: Optional[bool] = _bool(default=None)
    checked_ed_sec: Optional[bool] = _bool(default=None)

    collection_place_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )
    text_origin_place_id: Optional[int] = Field(default=None, foreign_key="place.id")
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

    notes: Optional[str] = _text(default=None)
    witness_relation_notes: Optional[str] = _text(default=None)
    manuscript_type_id: Optional[int] = Field(
        default=None, foreign_key="manuscripttype.id"
    )

    dimension_width_cm: Optional[float] = _real(default=None)
    dimension_height_cm: Optional[float] = _real(default=None)

    # --- Relationships ---

    text_associations: List["ManuscriptText"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={
            "overlaps": "texts,manuscripts",
            "primaryjoin": "Manuscript.id == ManuscriptText.ms_id"
        }
    )
    texts: List["Text"] = Relationship(
        link_model=ManuscriptText,
        sa_relationship_kwargs={
            "overlaps": "text_associations,manuscript,text,manuscript_associations,texts",
            "primaryjoin": "Manuscript.id == ManuscriptText.ms_id",
            "secondaryjoin": "Text.id == ManuscriptText.text_id"
        }
    )

    external_resources: List["ExternalResource"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    images: List["Image"] = Relationship(back_populates="manuscript")

    edition_associations: List["EditionManuscript"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"overlaps": "editions,manuscripts"}
    )
    editions: List["Edition"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={"overlaps": "edition_associations,manuscript"}
    )

    outgoing_relations: List["ManuscriptRelation"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.id==ManuscriptRelation.source_manuscript_id",
            "back_populates": "source_manuscript",
            "cascade": "all, delete-orphan",
        }
    )
    incoming_relations: List["ManuscriptRelation"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.id==ManuscriptRelation.target_manuscript_id",
            "back_populates": "target_manuscript",
            "cascade": "all, delete-orphan",
        }
    )

    collection_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.collection_place_id == Place.id",
            "uselist": False,
        }
    )
    text_origin_place: Optional["Place"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Manuscript.text_origin_place_id == Place.id",
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


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class Image(Table, table=True):
    """A digitized image URL associated with a manuscript."""
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
# Edition  (Tab 2)
# ---------------------------------------------------------------------------

class Edition(Table, table=True):
    """A printed or digital edition of a hagiographic text.

    has_scan is removed: scan presence is derivable from ExternalResource
    records linked via EditionExternalResource.  checked_leg is removed as
    it was not populated.  The mutual exclusive reprint type flags are
    collapsed into a single reprint_type enum field.
    """
    __table_args__ = (UniqueConstraint("unique_id_numeric"), _STRICT)

    bhl_number: Optional[str] = _text(default=None, index=True)
    title: Optional[str] = _text(default=None)
    edition_identifier: Optional[str] = _text(default=None)
    edition_reference_per_text: Optional[str] = _text(default=None)

    checked_dg: Optional[bool] = _bool(default=None)
    checked_naso: Optional[bool] = _bool(default=None)
    checked_ed_sec: Optional[bool] = _bool(default=None)

    unique_id_numeric: Optional[int] = Field(default=None, sa_type=Integer())
    unique_id_descriptive: Optional[str] = _text(default=None)

    year_of_publication: Optional[int] = Field(default=None, sa_type=Integer())
    bibliographic_reference: Optional[str] = _text(default=None)
    page_range: Optional[str] = _text(default=None)

    is_reprint: Optional[bool] = _bool(default=None)
    reprint_type: Optional[ReprintType] = _text(default=None)
    reprint_of: Optional[str] = _text(default=None)
    reprint_notes: Optional[str] = _text(default=None)

    has_transcription: Optional[bool] = _bool(default=None)
    is_our_transcription: Optional[bool] = _bool(default=None)
    transcription_notes: Optional[str] = _text(default=None)
    is_collated: Optional[bool] = _bool(default=None)

    edition_refs: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="editions")

    manuscript_associations: List["EditionManuscript"] = Relationship(
        back_populates="edition",
        sa_relationship_kwargs={"overlaps": "editions,manuscripts"}
    )

    external_resources: List["EditionExternalResource"] = Relationship(
        back_populates="edition"
    )

    manuscripts: List["Manuscript"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={
            "overlaps": "edition_associations,manuscript,manuscripts,manuscript_associations,edition"
        }
    )