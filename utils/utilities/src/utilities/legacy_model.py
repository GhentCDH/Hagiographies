# utilities/legacy_model.py
# ---------------------------------------------------------------------------
# PARKED — reference only. Superseded by utilities/model.py (schema restart,
# July 2026). Kept importable for the parked legacy importer
# (importer/legacy/); do not build new code against these models.
# ---------------------------------------------------------------------------
# SQLModel models for the Hagiographies project.
#
# Aligned with the TEXTS / MANUSCRIPTS / EDITIONS worksheets of the June 2026
# corpus workbook.  Column names mirror the sheet headers (snake_cased,
# sensibly shortened) so data entry and consultation map 1:1 to the Excel —
# see the class docstrings for the exact header ↔ field correspondence.
#
#   - Text.rewrite_notes: the 'Réécriture of which text(s)?' column contains
#     free-text titles, literature references and partial BHL strings — never
#     plain FK-resolvable BHL numbers — so a FK to Text.id is not feasible.
#   - Anonymous authors are stored as distinct rows (Anon.-1, Anon.-2, …).
# ---------------------------------------------------------------------------

from enum import Enum
from typing import Optional, List

from sqlalchemy import Integer
from sqlalchemy import Text as SAText
from sqlalchemy import REAL, UniqueConstraint
import sqlalchemy
from sqlmodel import Field, SQLModel, Relationship

def _text(**kwargs):
    """TEXT column."""
    return Field(sa_type=SAText(), **kwargs)


def _real(**kwargs):
    """REAL column."""
    return Field(sa_type=REAL(), **kwargs)


def _bool(**kwargs):
    """BOOLEAN column."""
    return Field(sa_type=sqlalchemy.Boolean(), **kwargs)


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


class ChurchEntityType(str, Enum):
    """Type of an ecclesiastical entity.

    Distinguishes archdioceses from dioceses so that the same place-name
    (e.g. 'Trier') can exist as two separate ChurchEntity records — one per
    level — without violating the unique constraint.  This also prevents the
    'Trier Trier' visual duplicate in the admin UI where both
    provenance_archdiocese and provenance_diocese columns are displayed.
    """
    archdiocese = "archdiocese"
    diocese = "diocese"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Table(SQLModel):
    """Base class: auto-incrementing primary key."""
    id: Optional[int] = Field(default=None, primary_key=True)


# ---------------------------------------------------------------------------
# Normalized Lookup Tables
# ---------------------------------------------------------------------------

class Place(Table, table=True):
    """A geographic location, optionally enriched with GPS coordinates."""
    __table_args__ = (UniqueConstraint("name"),)
    name: str = _text(index=True)
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)
    # Confidence rating for uncertain identifications — replaces '?' suffixes
    # in the source names (importer strips them and sets 'uncertain').
    confidence_rating: Optional[str] = _text(default=None)

    # Back-references — all use forward refs resolved after all classes load.
    institutions: List["Institution"] = Relationship(
        back_populates="place",
        sa_relationship_kwargs={
            "primaryjoin": "Place.id == Institution.place_id",
            "uselist": True,
        },
    )
    origin_texts: List["Text"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Place.id == Text.origin_place_id",
            "foreign_keys": "[Text.origin_place_id]",
            "uselist": True,
            "viewonly": True,
        },
    )
    destinatary_texts: List["Text"] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Place.id == Text.primary_destinatary_place_id",
            "foreign_keys": "[Text.primary_destinatary_place_id]",
            "uselist": True,
            "viewonly": True,
        },
    )


class Institution(Table, table=True):
    """A heritage or monastic institution, optionally linked to a place.

    lat/lon come from the provenance-owner GPS columns of the MANUSCRIPTS
    sheet; '?' markers in source names are stripped into confidence_rating.
    """
    __table_args__ = (UniqueConstraint("name"),)
    name: str = _text(index=True)
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)
    confidence_rating: Optional[str] = _text(default=None)
    place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    place: Optional[Place] = Relationship(back_populates="institutions")


class Author(Table, table=True):
    """A hagiographic text author.

    Field names mirror the TEXTS sheet columns Q–S so data entry maps 1:1:
    'Institutional training ground of the author', 'Regional or local
    antecedents of the author', 'Author milieu'.

    'Is author based in destinatary institution?' is NOT stored here — it is
    a property of the Text/author relationship and lives on
    Text.author_locally_based.

    Anonymous authors are kept distinct: the importer names them
    'Anon.-1', 'Anon.-2', … so their per-text metadata is not merged.
    """
    name: str = _text(index=True)

    # 'Institutional training ground of the author' (free text, e.g. "Monastic")
    institutional_training_ground: Optional[str] = _text(default=None)
    # 'Regional or local antecedents of the author'
    regional_antecedents: Optional[str] = _text(default=None)
    # 'Author milieu' (e.g. "Monastic", "Episcopal")
    milieu: Optional[str] = _text(default=None)


class Typology(Table, table=True):
    """Hierarchical source typology (e.g. Vita > Passio)."""
    __table_args__ = (UniqueConstraint("name"),)
    name: str = _text(index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="typology.id")

    parent: Optional["Typology"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Typology.id"},
    )
    children: List["Typology"] = Relationship(back_populates="parent")


class ManuscriptType(Table, table=True):
    """Type classification for a manuscript (e.g. legendarium, collectio)."""
    __table_args__ = (UniqueConstraint("name"),)
    name: str = _text(index=True)


class ChurchEntity(Table, table=True):
    """An ecclesiastical entity: archdiocese or diocese.

    entity_type distinguishes archdioceses from dioceses so that the same
    place-name (e.g. 'Trier') can exist as separate records for each
    ecclesiastical level.  The unique constraint covers (name, entity_type)
    so 'Trier' + 'archdiocese' and 'Trier' + 'diocese' are distinct rows.
    """
    __table_args__ = (UniqueConstraint("name", "entity_type"),)
    name: str = _text(index=True)
    entity_type: str = _text(default=ChurchEntityType.diocese, index=True)
    # Confidence rating for uncertain identifications — replaces '?' suffixes
    # in the source names (importer strips them and sets 'uncertain').
    confidence_rating: Optional[str] = _text(default=None)
    # Fallback GPS: when a text/manuscript has no origin institution, the
    # sheet's GPS belongs to the origin diocese and is stored here.
    lat: Optional[float] = _real(default=None)
    lon: Optional[float] = _real(default=None)


class DatingCentury(Table, table=True):
    """A century used for manuscript dating (integer, e.g. 10 for Xth c.)."""
    __table_args__ = (UniqueConstraint("century"),)
    century: int = Field(index=True, sa_type=Integer())


class VernacularRegion(Table, table=True):
    """Vernacular region category (e.g. Romance, Germanic)."""
    __table_args__ = (UniqueConstraint("region"),)
    region: str = _text(index=True)


class ImageType(Table, table=True):
    """Image delivery type (e.g. iiif, iiif_mf, scan, iphone_photo)."""
    __table_args__ = (UniqueConstraint("name"),)
    name: str = _text(index=True)


# ---------------------------------------------------------------------------
# M2M Join Tables  (defined early — required by link_model= references)
# ---------------------------------------------------------------------------

class EditionManuscript(SQLModel, table=True):
    """Many-to-many join: Edition ↔ Manuscript copy, with inspection metadata.

    likely_copy mirrors the 'Likely use of a copy of Manuscript N?' columns:
    True when the edition probably used a (lost) copy of the manuscript
    rather than the manuscript itself.
    """

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    ms_id: int = Field(
        sa_type=Integer(), foreign_key="manuscript.id", primary_key=True
    )

    inspection_status: Optional[str] = _text(default="unknown")
    likely_copy: Optional[bool] = _bool(default=None)

    edition: "Edition" = Relationship(
        back_populates="manuscript_associations",
        sa_relationship_kwargs={
            "overlaps": "editions,manuscripts",
            "foreign_keys": "[EditionManuscript.edition_id]",
        }
    )
    manuscript: "Manuscript" = Relationship(
        back_populates="edition_associations",
        sa_relationship_kwargs={
            "overlaps": "editions,manuscripts",
            "foreign_keys": "[EditionManuscript.ms_id]",
        }
    )


class EditionVolume(Table, table=True):
    """A physical book/volume containing one or more editions.

    Identified by the 'Edition unique identifier (inc. volume)' value
    (e.g. "AASS Jul. 4 (3rd.)", "Surius 5 (1574)").  Editions link here via
    Edition.volume_id; the 'Edition used or consulted N' columns link here
    via EditionConsultedVolume.
    """
    __tablename__ = "edition_volume"
    __table_args__ = (UniqueConstraint("identifier"),)
    identifier: str = _text(index=True)

    editions: List["Edition"] = Relationship(back_populates="volume")
    consulted_by: List["EditionConsultedVolume"] = Relationship(
        back_populates="volume"
    )


class EditionConsultedVolume(SQLModel, table=True):
    """Join: Edition → volume(s) consulted while preparing it.

    Relational form of the 'Edition used or consulted 1..5' columns;
    unresolvable values ('to be verified', 'Unpublished') stay in
    Edition.editions_consulted as free text.
    """
    __tablename__ = "edition_consulted_volume"

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    volume_id: int = Field(
        sa_type=Integer(), foreign_key="edition_volume.id", primary_key=True
    )

    edition: "Edition" = Relationship(back_populates="consulted_volume_links")
    volume: "EditionVolume" = Relationship(back_populates="consulted_by")


class EditionExternalResource(SQLModel, table=True):
    """Many-to-many join: Edition ↔ ExternalResource (e.g. scan links)."""

    edition_id: int = Field(
        sa_type=Integer(), foreign_key="edition.id", primary_key=True
    )
    resource_id: int = Field(
        sa_type=Integer(), foreign_key="external_resource.id", primary_key=True
    )

    edition: "Edition" = Relationship(back_populates="external_resources")
    resource: "ExternalResource" = Relationship(back_populates="edition_associations")


class ExternalResource(SQLModel, table=True):
    """An external hyperlink or resource for a codex or edition.

    The URL is extracted from the Excel hyperlink target; display text is
    discarded.  Catalogue links attach to the codex; scan links for editions
    are linked via EditionExternalResource.
    """
    __tablename__ = "external_resource"
    __table_args__ = (
        UniqueConstraint("codex_id", "url", name="uix_codex_url"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    codex_id: Optional[int] = Field(default=None, foreign_key="codex.id")
    url: str = _text(index=True)
    resource_type: ExternalResourceType = _text(default=ExternalResourceType.other)
    comment: Optional[str] = _text(default=None)
    is_alive: bool = _bool(default=True)

    codex: "Codex" = Relationship(back_populates="external_resources")
    edition_associations: List["EditionExternalResource"] = Relationship(
        back_populates="resource"
    )


class ManuscriptRelation(SQLModel, table=True):
    """A directed relationship between two manuscript copies.

    Two relation types, stored exactly as the source records them:
      copy_of     — source manuscript is a copy of target ('Based on exemplar')
      exemplar_of — source manuscript was used to make target
                    ('Exemplar of which manuscript(s)')
    """
    __tablename__ = "manuscript_relation"
    __table_args__ = (
        UniqueConstraint(
            "source_manuscript_id",
            "target_manuscript_id",
            "relation_type",
            name="uix_source_target_relation",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_manuscript_id: int = Field(foreign_key="manuscript.id")
    target_manuscript_id: int = Field(foreign_key="manuscript.id")
    relation_type: RelationType = _text(default=RelationType.other)
    certainty: Certainty = _text(default=Certainty.uncertain)
    notes: Optional[str] = _text(default=None)
    source_reference: Optional[str] = _text(default=None)

    source_manuscript: "Manuscript" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "ManuscriptRelation.source_manuscript_id==Manuscript.id",
            "back_populates": "outgoing_relations",
        }
    )
    target_manuscript: "Manuscript" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "ManuscriptRelation.target_manuscript_id==Manuscript.id",
            "back_populates": "incoming_relations",
        }
    )


# ---------------------------------------------------------------------------
# Text  (Tab 3 — Corpus hagio)
# ---------------------------------------------------------------------------

class Text(Table, table=True):
    """A hagiographic text entry identified by its unique identifier.

    Aligned with the 'TEXTS' worksheet of the June 2026 corpus; column names
    mirror the sheet headers so data entry maps 1:1.

    rewrite_notes: the source column 'Réécriture of which text(s)?' contains
    free-text titles, literature references and partial BHL strings — never
    plain resolvable BHL IDs — so a FK to Text.id is not feasible.
    """

    # 'BHL or NO BHL' — distinguishes BHL vs non-BHL identifiers.
    bhl_or_no_bhl: Optional[str] = _text(default=None)
    # 'Unique identifier' — the text key all other sheets join on.
    unique_identifier: Optional[int] = Field(default=None, sa_type=Integer(), index=True)
    # 'Title of the work'
    title: Optional[str] = _text(default=None)
    # 'Approximate token count'
    approximate_token_count: Optional[int] = Field(default=None, sa_type=Integer())
    # 'Prose or verse'
    prose_or_verse: Optional[str] = _text(default=None)

    # Chronology
    # 'Quarter century chronology' (e.g. "0975-1000")
    quarter_century_chronology: Optional[str] = _text(default=None)
    dating_range_start: Optional[int] = Field(default=None, sa_type=Integer())
    dating_range_end: Optional[int] = Field(default=None, sa_type=Integer())
    # 'Dating notes'
    dating_notes: Optional[str] = _text(default=None)
    # 'Dating confidence rating'
    dating_confidence_rating: Optional[str] = _text(default=None)

    # Provenance of creation
    origin_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_diocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_place_id: Optional[int] = Field(default=None, foreign_key="place.id")

    # Precision flags
    is_origin_precise: Optional[bool] = _bool(default=None)
    is_destinatary_precise: Optional[bool] = _bool(default=None)

    # Primary destinatary
    primary_destinatary_place_id: Optional[int] = Field(
        default=None, foreign_key="place.id"
    )

    # Author FK; training ground / antecedents / milieu live on Author
    author_id: Optional[int] = Field(default=None, foreign_key="author.id")
    # Confidence rating for the author attribution — replaces '?' suffixes in
    # the source author names (importer strips them and sets 'uncertain').
    authorship_confidence_rating: Optional[str] = _text(default=None)
    # 'Is author based in destinatary institution?' — attribute of the text,
    # not of the author (free text: Yes / No / Unknown …).
    author_locally_based: Optional[str] = _text(default=None)

    # Typology
    source_type_id: Optional[int] = Field(default=None, foreign_key="typology.id")
    subtype_id: Optional[int] = Field(default=None, foreign_key="typology.id")

    # Rewrite
    is_rewrite: Optional[bool] = _bool(default=None)
    rewrite_notes: Optional[str] = _text(default=None)   # free-text, not a FK

    # 'Selected reference'
    selected_reference: Optional[str] = _text(default=None)
    notes: Optional[str] = _text(default=None)

    # --- Relationships ---

    # Manuscript copies of this text (one copy belongs to exactly one text).
    manuscripts: List["Manuscript"] = Relationship(back_populates="text")

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
# Codex & Manuscript copy  (Tab 1)
# ---------------------------------------------------------------------------

class Codex(Table, table=True):
    """A physical codex (book), identified by its 'Codex unique identifier'.

    Holds everything that belongs to the physical object: location, holding
    institution, shelfmark, dating, origin/provenance, catalogue links and
    images.  The manuscript copies it contains are Manuscript rows.
    """
    __tablename__ = "codex"
    __table_args__ = (UniqueConstraint("codex_unique_identifier"),)

    # 'Codex unique identifier' (e.g. "Montpellier 2", "Bern 2")
    codex_unique_identifier: str = _text(index=True)
    # 'Codex number in database'
    codex_number_in_database: Optional[int] = Field(default=None, sa_type=Integer())

    # 'Codex with multiple manuscript copies of texts from corpus' (Y/N)
    codex_with_multiple_copies: Optional[bool] = _bool(default=None)
    # 'Codex features n manuscript copies of texts from corpus'
    codex_copies_count: Optional[int] = Field(default=None, sa_type=Integer())
    # 'Composite?'
    is_composite_codex: Optional[bool] = _bool(default=None)

    # 'Manuscript location' / 'Manuscript holding institution' / shelfmark
    location_place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    holding_institution_id: Optional[int] = Field(
        default=None, foreign_key="institution.id"
    )
    shelfmark: Optional[str] = _text(default=None)

    # Dating
    dating_century_id: Optional[int] = Field(
        default=None, foreign_key="datingcentury.id"
    )
    dating_century: Optional[DatingCentury] = Relationship()
    dating_range_start: Optional[int] = Field(default=None, sa_type=Integer())
    dating_range_end: Optional[int] = Field(default=None, sa_type=Integer())
    dating_reference: Optional[str] = _text(default=None)
    dating_confidence: Optional[str] = _text(default=None)

    # Légendiers (codex contents repertory)
    legendiers_usable: Optional[bool] = _bool(default=None)
    legendiers_link: Optional[str] = _text(default=None)
    legendiers_code: Optional[str] = _text(default=None)
    legendiers_alternative: Optional[str] = _text(default=None)
    legendiers_notes: Optional[str] = _text(default=None)

    # Codex origin (distinct from provenance below)
    origin_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_diocese_id: Optional[int] = Field(
        default=None, foreign_key="churchentity.id"
    )
    origin_diocese_confidence: Optional[str] = _text(default=None)
    origin_place_id: Optional[int] = Field(default=None, foreign_key="place.id")
    origin_confidence: Optional[str] = _text(default=None)

    # Provenance
    provenance_institution_id: Optional[int] = Field(
        default=None, foreign_key="institution.id"
    )
    provenance_institution_confidence: Optional[str] = _text(default=None)
    provenance_later_institution_id: Optional[int] = Field(
        default=None, foreign_key="institution.id"
    )
    provenance_reference: Optional[str] = _text(default=None)

    vernacular_region_id: Optional[int] = Field(
        default=None, foreign_key="vernacularregion.id"
    )
    vernacular_region: Optional[VernacularRegion] = Relationship()

    manuscript_type_id: Optional[int] = Field(
        default=None, foreign_key="manuscripttype.id"
    )

    dimension_width_cm: Optional[float] = _real(default=None)
    dimension_height_cm: Optional[float] = _real(default=None)

    # --- Relationships ---

    manuscripts: List["Manuscript"] = Relationship(back_populates="codex")

    external_resources: List["ExternalResource"] = Relationship(
        back_populates="codex",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    images: List["Image"] = Relationship(back_populates="codex")

    location_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.location_place_id == Place.id",
            "uselist": False,
            "overlaps": "origin_place",
        }
    )
    holding_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.holding_institution_id == Institution.id",
            "uselist": False,
            "overlaps": "provenance_institution,provenance_later_institution",
        }
    )
    provenance_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.provenance_institution_id == Institution.id",
            "uselist": False,
            "overlaps": "holding_institution,provenance_later_institution",
        }
    )
    provenance_later_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.provenance_later_institution_id == Institution.id",
            "uselist": False,
            "overlaps": "holding_institution,provenance_institution",
        }
    )
    origin_archdiocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.origin_archdiocese_id == ChurchEntity.id",
            "uselist": False,
            "overlaps": "origin_diocese",
        }
    )
    origin_diocese: Optional[ChurchEntity] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.origin_diocese_id == ChurchEntity.id",
            "uselist": False,
            "overlaps": "origin_archdiocese",
        }
    )
    origin_place: Optional[Place] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.origin_place_id == Place.id",
            "uselist": False,
            "overlaps": "location_place",
        }
    )
    manuscript_type: Optional[ManuscriptType] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Codex.manuscript_type_id == ManuscriptType.id",
            "uselist": False,
        }
    )


class Manuscript(Table, table=True):
    """A manuscript copy: one text as witnessed in one codex.

    One row per MANUSCRIPTS sheet row, keyed on the 'Manuscript copy unique
    identifier per text' value (e.g. "29-1") — the identifier that editions
    ('Manuscript used N') and exemplar relations reference.  Codex-level
    attributes (location, dating, catalogue links, …) live on Codex.
    """
    __table_args__ = (UniqueConstraint("manuscript_copy_identifier_per_text"),)

    # 'Manuscript copy unique identifier per text' (e.g. "29-3")
    manuscript_copy_identifier_per_text: str = _text(index=True)

    codex_id: Optional[int] = Field(default=None, foreign_key="codex.id")
    codex: Optional[Codex] = Relationship(back_populates="manuscripts")

    # The text this copy witnesses ('Unique text identifier').
    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional["Text"] = Relationship(back_populates="manuscripts")

    # 'Preservation status of manuscript copy'
    preservation_status: Optional[str] = _text(default=None)
    # 'Folio or page range'
    folio_or_page_range: Optional[str] = _text(default=None)

    notes: Optional[str] = _text(default=None)

    # --- Relationships ---

    edition_associations: List["EditionManuscript"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"overlaps": "editions,manuscripts"},
    )
    editions: List["Edition"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={"overlaps": "edition_associations,manuscript"},
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


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class Image(Table, table=True):
    """A digitized image URL associated with a codex.

    url is the source link as recorded in the workbook (often a viewer or
    landing page).  iiif_manifest_url is the validated IIIF manifest link
    (JSON, renderable in a viewer) maintained by the check-iiif script.
    """
    __table_args__ = (
        UniqueConstraint("codex_id", "url"),
    )

    url: str = _text()
    iiif_manifest_url: Optional[str] = _text(default=None)
    comment: Optional[str] = _text(default=None)

    image_type_id: Optional[int] = Field(default=None, foreign_key="imagetype.id")
    image_type: Optional[ImageType] = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "Image.image_type_id == ImageType.id",
            "uselist": False,
        }
    )

    codex_id: Optional[int] = Field(default=None, foreign_key="codex.id")
    codex: Optional[Codex] = Relationship(back_populates="images")


# ---------------------------------------------------------------------------
# Edition  (Tab 2)
# ---------------------------------------------------------------------------

class Edition(Table, table=True):
    """A printed or digital edition of a hagiographic text.

    Aligned with the 'EDITIONS' worksheet of the June 2026 corpus; column
    names mirror the sheet headers so data entry maps 1:1.

    The per-edition key is `edition_unique_identifier_per_text` ('Edition
    unique identifier per individual text', e.g. "693-B"); the containing
    book/volume is relational via `volume_id` → EditionVolume.
    Scan/edition-image links are also stored as ExternalResource via
    EditionExternalResource.
    """

    title: Optional[str] = _text(default=None)
    # 'Edition unique identifier per individual text' (e.g. "693-B")
    edition_unique_identifier_per_text: Optional[str] = _text(default=None, index=True)
    # 'Unique identifier' — the shared text key.
    text_unique_identifier: Optional[int] = Field(
        default=None, sa_type=Integer(), index=True
    )
    # 'Edition unique identifier (inc. volume)' (e.g. "Labbe 1") — per-edition key.
    # 'Edition unique identifier (inc. volume)' — relational: the containing
    # book/volume, shared by all editions printed in it.
    volume_id: Optional[int] = Field(default=None, foreign_key="edition_volume.id")
    volume: Optional[EditionVolume] = Relationship(back_populates="editions")

    # 'Publication year'
    publication_year: Optional[int] = Field(default=None, sa_type=Integer())
    # 'Edition reference'
    edition_reference: Optional[str] = _text(default=None)
    # 'Page numbers'
    page_numbers: Optional[str] = _text(default=None)

    # Reprint block ('Reprint ?' … 'Collation done?')
    is_reprint: Optional[bool] = _bool(default=None)
    reprint_identically_typeset: Optional[bool] = _bool(default=None)
    reprint_newly_typeset: Optional[bool] = _bool(default=None)
    # 'If reprint, of what?' — free text reference to the reprinted edition.
    reprint_of: Optional[str] = _text(default=None)
    # 'Images of edition?' (e.g. "SCAN", "Y")
    images_of_edition: Optional[str] = _text(default=None)
    # 'Edition images link' — extracted hyperlink URL.
    edition_images_link: Optional[str] = _text(default=None)
    transcription_available: Optional[bool] = _bool(default=None)
    collation_done: Optional[bool] = _bool(default=None)

    # 'Edition used or consulted 1..5' — raw free-text list; resolvable values
    # are additionally linked to EditionVolume via EditionConsultedVolume.
    editions_consulted: Optional[str] = _text(default=None)

    notes: Optional[str] = _text(default=None)

    text_id: Optional[int] = Field(default=None, foreign_key="text.id")
    text: Optional[Text] = Relationship(back_populates="editions")

    consulted_volume_links: List["EditionConsultedVolume"] = Relationship(
        back_populates="edition"
    )

    manuscript_associations: List["EditionManuscript"] = Relationship(
        back_populates="edition",
        sa_relationship_kwargs={"overlaps": "editions,manuscripts"},
    )
    external_resources: List["EditionExternalResource"] = Relationship(
        back_populates="edition"
    )
    manuscripts: List["Manuscript"] = Relationship(
        link_model=EditionManuscript,
        sa_relationship_kwargs={
            "overlaps": "edition_associations,manuscript,manuscripts,manuscript_associations,edition,editions",
        }
    )