from typing import Optional, List
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel, Relationship


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


class EditionManuscriptLink(Table, table=True):
    """Link between an Edition and a Manuscript (Manuscripts used in an edition)."""
    
    edition_id: int = Field(foreign_key="edition.id")
    manuscript_id: int = Field(foreign_key="manuscript.id")
    
    # Relationships - use string forward references
    edition: "Edition" = Relationship(back_populates="manuscripts_linked") # Keep structural link if needed, or remove
    manuscript: "Manuscript" = Relationship(back_populates="editions_linked")


class Archbishopric(Table, table=True):
    """Represents an archbishopric jurisdiction."""
    name: str = Field(index=True, unique=True)

    # Relationships
    origins: List["Origin"] = Relationship(back_populates="archbishopric")
    corpus_hagios: List["CorpusHagio"] = Relationship(back_populates="archbishopric")
    witnesses: List["Witness"] = Relationship(back_populates="archbishopric")


class Bishopric(Table, table=True):
    """Represents a bishopric jurisdiction."""
    name: str = Field(index=True, unique=True)

    # Relationships
    origins: List["Origin"] = Relationship(back_populates="bishopric")
    corpus_hagios: List["CorpusHagio"] = Relationship(back_populates="bishopric")
    witnesses: List["Witness"] = Relationship(back_populates="bishopric")


class Origin(Table, table=True):
    """Represents the origin of a text."""
    name: str

    # Coordinates
    latitude: Optional[float] = None # GPS Latitude OR
    longitude: Optional[float] = None # GPS Longitude OR
    
    # Jurisdiction
    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")

    # Relationships
    texts: List["CorpusHagio"] = Relationship(back_populates="origin")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="origins")
    bishopric: Optional[Bishopric] = Relationship(back_populates="origins")


class CorpusHagio(Table, table=True):
    """Represents a hagiographical text (from Corpus Hagio)."""
    
    bhl_number: str = Field(index=True)
    title: Optional[str] = None
    author: Optional[str] = None
    dating_rough: Optional[str] = None
    origin_id: Optional[int] = Field(default=None, foreign_key="origin.id")
    
    primary_destinatary: Optional[str] = None
    destinatary_latitude: Optional[float] = None # GPS Latitude DES
    destinatary_longitude: Optional[float] = None # GPS Longitude DES

    # New metadata fields
    approx_length: Optional[int] = None
    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")
    source_type: Optional[str] = None
    subtype: Optional[str] = None
    prose_verse: Optional[str] = None
    is_reecriture: Optional[bool] = None
    ocr_status: Optional[str] = None
    notes: Optional[str] = None

    # Relationships
    origin: Optional[Origin] = Relationship(back_populates="texts")
    archbishopric: Optional[Archbishopric] = Relationship(back_populates="corpus_hagios")
    bishopric: Optional[Bishopric] = Relationship(back_populates="corpus_hagios")
    witnesses: List["Witness"] = Relationship(back_populates="text")
    editions: List["Edition"] = Relationship(back_populates="text")


class City(Table, table=True):
    """Represents a city."""
    name: str

    # Relationships
    locations: List["Location"] = Relationship(back_populates="city")


class Library(Table, table=True):
    """Represents a library."""
    name: str

    # Relationships
    locations: List["Location"] = Relationship(back_populates="library")


class Location(Table, table=True):
    """Represents a location (City + Library)."""
    city_id: int = Field(foreign_key="city.id")
    library_id: int = Field(foreign_key="library.id")
    shelfmark: str
    
    # Relationships
    city: City = Relationship(back_populates="locations")
    library: Library = Relationship(back_populates="locations")
    manuscripts: List["Manuscript"] = Relationship(back_populates="location") 


class Manuscript(Table, table=True):
    """Represents a physical manuscript (from Manuscripts)."""
    
    iiif_url: Optional[str] = None
    
    location_id: int = Field(foreign_key="location.id")
    unique_id: Optional[str] = Field(default=None, index=True)
    
    # New metadata fields
    preservation_status: Optional[str] = None
    vernacular_region: Optional[str] = None
    catalog_link: Optional[str] = None
    manuscript_type: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None

    # Relationships
    location: Location = Relationship(back_populates="manuscripts")
    witnesses: List["Witness"] = Relationship(back_populates="manuscript")
    # Structural link back to link table (optional but good for completeness)
    editions_linked: List[EditionManuscriptLink] = Relationship(back_populates="manuscript")
    # Implicit link
    editions: List["Edition"] = Relationship(
        back_populates="manuscripts", 
        link_model=EditionManuscriptLink,
        sa_relationship_kwargs={"overlaps": "editions_linked,manuscript,edition,manuscripts_linked"}
    )


class Provenance(Table, table=True):
    """Represents the provenance of a witness."""
    name: str

    # Relationships
    witnesses: List["Witness"] = Relationship(back_populates="provenance")


class Witness(Table, table=True):
    """Link between a Text and a Manuscript (specific instance of a text)."""
    
    text_id: int = Field(foreign_key="corpushagio.id")
    manuscript_id: int = Field(foreign_key="manuscript.id")
    
    page_range: Optional[str] = None
    dating: Optional[str] = None
    provenance_id: Optional[int] = Field(default=None, foreign_key="provenance.id")
    
    # Relationships
    text: CorpusHagio = Relationship(back_populates="witnesses")
    manuscript: Manuscript = Relationship(back_populates="witnesses")
    provenance: Optional[Provenance] = Relationship(back_populates="witnesses")
    
    # Precise dating and jurisdiction
    archbishopric_id: Optional[int] = Field(default=None, foreign_key="archbishopric.id")
    bishopric_id: Optional[int] = Field(default=None, foreign_key="bishopric.id")
    dating_century: Optional[str] = None
    dating_range_start: Optional[int] = None
    dating_range_end: Optional[int] = None

    archbishopric: Optional[Archbishopric] = Relationship(back_populates="witnesses")
    bishopric: Optional[Bishopric] = Relationship(back_populates="witnesses")


class Reference(Table, table=True):
    """Represents a bibliographic reference."""
    title: str

    # Relationships
    editions: List["Edition"] = Relationship(back_populates="reference")


class Edition(Table, table=True):
    """Represents a published edition of a text."""
    
    text_id: Optional[int] = Field(default=None, foreign_key="corpushagio.id") 
    title: str
    year: Optional[int] = None
    reference_id: Optional[int] = Field(default=None, foreign_key="reference.id")
    
    # Relationships
    text: Optional[CorpusHagio] = Relationship(back_populates="editions")
    reference: Optional[Reference] = Relationship(back_populates="editions")
    # Structural link
    manuscripts_linked: List[EditionManuscriptLink] = Relationship(back_populates="edition")
    # Implicit link
    manuscripts: List[Manuscript] = Relationship(
        back_populates="editions", 
        link_model=EditionManuscriptLink,
        sa_relationship_kwargs={"overlaps": "manuscripts_linked,edition,manuscript,editions_linked"}
    ) 