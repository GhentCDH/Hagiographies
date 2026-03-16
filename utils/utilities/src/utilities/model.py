"""
model.py — SQLAlchemy/SQLModel ORM definitions for the Hagiographies database.

Table hierarchy
---------------
  Jurisdiction : Archbishopric, Bishopric
  Geography    : Origin, City, Library, Location
  Core content : CorpusHagio, Manuscript, Witness
  Editorial    : Provenance, Reference, Edition, EditionManuscriptLink

Table-name convention
---------------------
SQLModel derives the DB table name as the lowercased class name, e.g.
  CorpusHagio           -> "corpushagio"
  EditionManuscriptLink -> "editionmanuscriptlink"

GPS coordinates (CorpusHagio / Origin)
---------------------------------------
The "GPS Latitude OR" and "GPS Longitude OR" column headers are *swapped* in
the source Excel file.  The import layer (cli.py) corrects this before
persisting.  Do NOT fix the swap here.

Witness — dating fields
-----------------------
The Manuscripts sheet already provides pre-parsed numeric columns:
  "Dating by (earliest) century"  -> dating_century  (string label, e.g. "11")
  "Dating "                       -> dating_raw       (verbatim, e.g. "11(2)-12(1)")
  "Dating range start"            -> dating_start     (integer year, e.g. 1051)
  "Dating range end"              -> dating_end       (integer year, e.g. 1150)

dating_comment is a free-text field populated during import (echoes dating_raw)
and can be extended manually with source evidence.

For edge cases where start/end are absent but dating_raw is present, cli.py
calls parse_dating() as a fallback.  Full conversion rules are in cli.py.

Witness — provenance fields
----------------------------
The sheet distinguishes four levels:
  "Provenance general"     -> provenance_id (FK to Provenance.name)
  "Provenance archdiocese" -> provenance_archdiocese
  "Provenance diocese"     -> provenance_diocese
  "Provenance institution" -> provenance_institution

Note that Archbishopric/Bishopric on the Witness row represent the *textual*
jurisdiction of the BHL text itself, NOT the provenance jurisdiction.

Manuscript — exemplar / copy fields
-------------------------------------
The sheet tracks stemmatic relationships:
  "Copy of which first/second/third exemplar?" -> copy_of_exemplar_1/2/3
  " Certain?"                                  -> exemplar_certain
  "Notes on exemplar"                          -> notes_on_exemplar
  "Exemplar of which manuscript (1-4)?"        -> exemplar_of_ms_1/2/3/4
  "Notes on copies"                            -> notes_on_copies
These are stored as plain strings (manuscript identifiers or free text).

Manuscript — boolean flags
---------------------------
  leg     : "LEG"    — included in the Legendarium Flandrense corpus
  dg      : "DG"     — included in the DG corpus
  naso    : "NASO"   — included in the NASO corpus
  ed_sec  : "ED/SEC" — secondary edition available

EditionManuscriptLink — join table
-----------------------------------
This class has NO Relationship() attributes.  SQLAlchemy resolves forward
references lazily; adding back-references on the join table itself causes
"failed to locate a name" errors when the mapper is configured before Edition
or Manuscript are fully registered.  All traversal is done via the
Relationship() definitions on Edition and Manuscript instead.

Python 3.13 / from __future__ import annotations
-------------------------------------------------
Do NOT use "from __future__ import annotations" in this file.  Under PEP 563
all annotations become strings and SQLAlchemy/SQLModel can no longer resolve
generic aliases such as List["Origin"] at mapper configuration time, which
raises InvalidRequestError.  Concrete class references (no quotes, no forward
references) are used throughout instead.  Classes are ordered so that every
referenced class is defined before it is used.
"""

# NOTE: "from __future__ import annotations" is intentionally absent.
# See module docstring for the reason.

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Table(SQLModel):
    """Abstract base that adds a surrogate PK and audit timestamps.

    created_at is set server-side on INSERT.
    updated_at is refreshed on every UPDATE via a trigger created in
    db.py -> create_updated_at_trigger.
    """

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
# Junction / link table  (defined first — no Relationship attrs)
# ---------------------------------------------------------------------------

class EditionManuscriptLink(SQLModel, table=True):
    """Many-to-many join between Edition and Manuscript.

    Uses a composite primary key (edition_id, manuscript_id) to prevent
    duplicate links at DB level.

    IMPORTANT: This class intentionally has NO Relationship() attributes.
    Adding Relationship() here causes SQLAlchemy mapper errors ("failed to
    locate a name") because Edition and Manuscript are defined later in this
    file.  Traverse the M2M link via Edition.manuscripts and
    Manuscript.editions instead.
    """

    edition_id: int = Field(foreign_key="edition.id", primary_key=True)
    manuscript_id: int = Field(foreign_key="manuscript.id", primary_key=True)


# ---------------------------------------------------------------------------
# Jurisdiction
# ---------------------------------------------------------------------------

class Archbishopric(Table, table=True):
    """Ecclesiastical province headed by an archbishop.

    Used as jurisdiction qualifier on Origin, CorpusHagio, and Witness.
    Unique by name so that get_or_create is safe under concurrent use.
    """

    name: str = Field(index=True, unique=True)

    origins: List["Origin"] = Relationship(back_populates="archbishopric")
    corpus_hagios: List["CorpusHagio"] = Relationship(back_populates="archbishopric")
    witnesses: List["Witness"] = Relationship(back_populates="archbishopric")


class Bishopric(Table, table=True):
    """Diocese headed by a bishop.

    Used as jurisdiction qualifier on Origin, CorpusHagio, and Witness.
    Unique by name so that get_or_create is safe under concurrent use.
    """

    name: str = Field(index=True, unique=True)

    origins: List["Origin"] = Relationship(back_populates="bishopric")
    corpus_hagios: List["CorpusHagio"] = Relationship(back_populates="bishopric")
    witnesses: List["Witness"] = Relationship(back_populates="bishopric")


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------

class Origin(Table, table=True):
    """Named place of origin for a hagiographical text.

    Coordinates are in decimal degrees (WGS-84).  The source Excel has the
    Latitude/Longitude column headers swapped; correction is applied in cli.py.
    """

    name: str = Field(index=True, unique=True)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    texts: List["CorpusHagio"] = Relationship(back_populates="origin")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="origins")
    bishopric: Optional[Bishopric] = Relationship(back_populates="origins")


class City(Table, table=True):
    """City in which a library (and hence manuscript) is located.

    Unique by name to avoid duplicate rows when the same city appears on
    multiple manuscript rows.
    """

    name: str = Field(index=True, unique=True)

    locations: List["Location"] = Relationship(back_populates="city")


class Library(Table, table=True):
    """Heritage institution / library that holds manuscripts.

    Unique by name for the same reason as City.
    """

    name: str = Field(index=True, unique=True)

    locations: List["Location"] = Relationship(back_populates="library")


class Location(Table, table=True):
    """Combination of City, Library, and shelfmark identifying a holding.

    The triple (city_id, library_id, shelfmark) is unique to prevent
    duplicate Location rows for the same physical holding.
    """

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

class CorpusHagio(Table, table=True):
    """A hagiographical text identified by its BHL number.

    One BHL number = one text.  A text can have multiple physical witnesses
    (manuscripts) and multiple modern editions.

    Archbishopric / Bishopric represent the textual jurisdiction context
    (the ecclesiastical province in which the text was produced / circulated).
    """

    bhl_number: str = Field(index=True, unique=True)
    title: Optional[str] = None
    author: Optional[str] = None
    dating_rough: Optional[str] = None

    origin_id: Optional[int] = Field(default=None, foreign_key="origin.id")

    primary_destinatary: Optional[str] = None
    destinatary_latitude: Optional[float] = None
    destinatary_longitude: Optional[float] = None

    approx_length: Optional[int] = None
    source_type: Optional[str] = None
    subtype: Optional[str] = None
    prose_verse: Optional[str] = None
    is_reecriture: Optional[bool] = None
    ocr_status: Optional[str] = None
    notes: Optional[str] = None

    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    origin: Optional[Origin] = Relationship(back_populates="texts")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="corpus_hagios")
    bishopric: Optional[Bishopric] = Relationship(back_populates="corpus_hagios")
    witnesses: List["Witness"] = Relationship(back_populates="text")
    editions: List["Edition"] = Relationship(back_populates="text")


class Manuscript(Table, table=True):
    """A physical manuscript codex held at a specific Location.

    unique_id is the identifier used across sheets in the source Excel to
    cross-reference manuscripts (e.g. "MS USED 1" to "MS USED 16" in Editions).

    Physical dimensions (height x width) are in millimetres when available.

    Boolean flags
    -------------
    leg    : "LEG"    — included in the Legendarium Flandrense corpus
    dg     : "DG"     — included in the DG corpus
    naso   : "NASO"   — included in the NASO corpus
    ed_sec : "ED/SEC" — secondary edition available

    Catalogue / image links
    -----------------------
    catalog_link            : "Online catalogue link"
    bollandist_catalog_link : "Bollandist catalogue link"
    other_catalog_link      : "Other relevant catalogue link"
    image_availability      : "IIIF, scan, or no images" — status string
                              (e.g. "IIIF MF", "SCAN", "NO")
    image_link              : "Link to images"

    Stemmatic fields
    ----------------
    copy_of_exemplar_1/2/3 : manuscript(s) this codex was copied from
    exemplar_certain       : certainty of exemplar identification
    notes_on_exemplar      : free-text notes on the exemplar relationship
    exemplar_of_ms_1/2/3/4 : manuscript(s) copied from this codex (inverse)
    notes_on_copies        : free-text notes on copies made from this codex
    """

    unique_id: Optional[str] = Field(default=None, index=True, unique=True)
    location_id: int = Field(foreign_key="location.id")

    preservation_status: Optional[str] = None
    vernacular_region: Optional[str] = None
    manuscript_type: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None

    # Boolean flags
    leg: Optional[bool] = None
    dg: Optional[bool] = None
    naso: Optional[bool] = None
    ed_sec: Optional[bool] = None

    # Catalogue / image links
    catalog_link: Optional[str] = None
    bollandist_catalog_link: Optional[str] = None
    other_catalog_link: Optional[str] = None
    image_availability: Optional[str] = None
    image_link: Optional[str] = None

    # Stemmatic / exemplar relationships
    copy_of_exemplar_1: Optional[str] = None
    copy_of_exemplar_2: Optional[str] = None
    copy_of_exemplar_3: Optional[str] = None
    exemplar_certain: Optional[bool] = None
    notes_on_exemplar: Optional[str] = None
    exemplar_of_ms_1: Optional[str] = None
    exemplar_of_ms_2: Optional[str] = None
    exemplar_of_ms_3: Optional[str] = None
    exemplar_of_ms_4: Optional[str] = None
    notes_on_copies: Optional[str] = None

    location: Location = Relationship(back_populates="manuscripts")
    witnesses: List["Witness"] = Relationship(back_populates="manuscript")
    editions: List["Edition"] = Relationship(
        back_populates="manuscripts",
        link_model=EditionManuscriptLink,
    )


class Provenance(Table, table=True):
    """General provenance label for a witness (e.g. a region or monastery).

    Unique by name so the same label is reused across witnesses.
    """

    name: str = Field(index=True, unique=True)

    witnesses: List["Witness"] = Relationship(back_populates="provenance")


class Witness(Table, table=True):
    """A single occurrence of a text (CorpusHagio) within a manuscript.

    One manuscript can contain many texts; one text can survive in many
    manuscripts.  Witness is the join enriched with per-occurrence metadata.

    ms_number_per_bhl
    -----------------
    "MS N per BHL number" — e.g. "29-1"; identifies this witness within the
    set of witnesses for one BHL text.

    Dating
    ------
    dating_century : "Dating by (earliest) century" — string label, e.g. "11"
    dating_raw     : "Dating " — verbatim source string (NOTE trailing space!)
    dating_start   : "Dating range start" — normalised start year
    dating_end     : "Dating range end"   — normalised end year
    dating_comment : free-text; echoes dating_raw on import, extendable manually

    parse_dating() in cli.py is used as fallback when start/end are absent.

    Provenance
    ----------
    provenance_id          : FK to Provenance ("Provenance general")
    provenance_archdiocese : "Provenance archdiocese"
    provenance_diocese     : "Provenance diocese"
    provenance_institution : "Provenance institution"

    Textual jurisdiction (NOT provenance jurisdiction)
    ---------------------------------------------------
    archbishopric_id / bishopric_id — the ecclesiastical province of the
    BHL text (column "Archbishopric"/"Bishopric" on the Manuscripts sheet).
    """

    text_id: int = Field(foreign_key="corpushagio.id")
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
    provenance_archdiocese: Optional[str] = None
    provenance_diocese: Optional[str] = None
    provenance_institution: Optional[str] = None

    # Textual jurisdiction
    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    text: CorpusHagio = Relationship(back_populates="witnesses")
    manuscript: Manuscript = Relationship(back_populates="witnesses")
    provenance: Optional[Provenance] = Relationship(back_populates="witnesses")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="witnesses")
    bishopric: Optional[Bishopric] = Relationship(back_populates="witnesses")


# ---------------------------------------------------------------------------
# Editorial
# ---------------------------------------------------------------------------

class Reference(Table, table=True):
    """Bibliographic reference for a modern edition of a text.

    Unique by title so the same reference is reused across editions.
    """

    title: str = Field(index=True, unique=True)

    editions: List["Edition"] = Relationship(back_populates="reference")


class Edition(Table, table=True):
    """A published (modern) edition of a hagiographical text.

    One text can have multiple editions.  An edition may have been produced
    using several manuscripts, modelled via EditionManuscriptLink.
    """

    text_id: Optional[int] = Field(default=None, foreign_key="corpushagio.id")
    title: str
    year: Optional[int] = None
    reference_id: Optional[int] = Field(default=None, foreign_key="reference.id")

    text: Optional[CorpusHagio] = Relationship(back_populates="editions")
    reference: Optional[Reference] = Relationship(back_populates="editions")
    manuscripts: List[Manuscript] = Relationship(
        back_populates="editions",
        link_model=EditionManuscriptLink,
    )


# ---------------------------------------------------------------------------
# cli.py must insert EditionManuscriptLink rows directly via session.add():
#
#   session.add(EditionManuscriptLink(
#       edition_id=edition.id,
#       manuscript_id=ms.id,
#   ))
#
# Do NOT use edition.manuscripts.append() or manuscript.editions.append()
# within the same transaction as the flush — this causes duplicate-insert
# conflicts on the composite PK.
# ---------------------------------------------------------------------------