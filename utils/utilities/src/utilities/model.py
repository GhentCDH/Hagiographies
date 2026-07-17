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


class Location(SQLModel, table=True):
    """A geographic point (Western Europe), deduplicated by coordinates.

    Coordinates come from the TEXTS GPS columns, whose headers are SWAPPED
    in the workbook: the 'GPS Longitude' column holds latitude ×10⁶ and the
    'GPS Latitude' column holds longitude ×10⁶. The importer reads them
    swapped and unscaled (documented workbook defect); values outside
    Western Europe (lat 44–56, lon −2–10) are rejected with a warning.
    name is the first entity name seen at these coordinates.
    """

    __tablename__ = "location"

    location_id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = Field(default=None)
    # Optional: manuscript locations (MANUSCRIPTS 'Manuscript location') are
    # bare place names created without coordinates.
    latitude: Optional[float] = excel_field(
        "… GPS Longitude (sic, swapped) / 1e6", default=None
    )
    longitude: Optional[float] = excel_field(
        "… GPS Latitude (sic, swapped) / 1e6", default=None
    )

    archdioceses: List["Archdiocese"] = Relationship(back_populates="location")
    dioceses: List["Diocese"] = Relationship(back_populates="location")
    institutions: List["Institution"] = Relationship(back_populates="location")
    manuscripts: List["Manuscript"] = Relationship(back_populates="location")


class Archdiocese(SQLModel, table=True):
    """Lookup: archdioceses (no coordinates in the TEXTS sheet yet)."""

    __tablename__ = "archdiocese"

    archdiocese_id: Optional[int] = Field(default=None, primary_key=True)
    name: str = excel_field("Text creation - location by archdiocese", unique=True)
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="archdioceses")
    origin_manuscripts: List["Manuscript"] = Relationship(
        back_populates="origin_archdiocese"
    )


class Diocese(SQLModel, table=True):
    """Lookup: dioceses (no coordinates in the TEXTS sheet yet)."""

    __tablename__ = "diocese"

    diocese_id: Optional[int] = Field(default=None, primary_key=True)
    name: str = excel_field("Text creation - location by diocese", unique=True)
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="dioceses")
    origin_manuscripts: List["Manuscript"] = Relationship(
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
    name: str = excel_field(
        "'Text creation - location by institution' / 'Primary institutional destinatary'",
        unique=True,
    )
    location_id: Optional[int] = Field(
        default=None, foreign_key="location.location_id"
    )
    note: Optional[str] = Field(default=None)

    location: Optional[Location] = Relationship(back_populates="institutions")
    origin_manuscripts: List["Manuscript"] = Relationship(
        back_populates="origin_institution",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.origin_institution_id"},
    )
    provenance_early_manuscripts: List["Manuscript"] = Relationship(
        back_populates="provenance_early_institute",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.provenance_early_institute_id"
        },
    )
    provenance_later_manuscripts: List["Manuscript"] = Relationship(
        back_populates="provenance_later_institute",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.provenance_later_institute_id"
        },
    )


class DatingConfidence(SQLModel, table=True):
    """Lookup: dating confidence rating (A/B/C/D)."""

    __tablename__ = "dating_confidence"

    dating_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field("Dating confidence rating", unique=True)
    notes: Optional[str] = Field(default=None)

    texts: List["Text"] = Relationship(back_populates="dating_confidence")
    manuscripts: List["Manuscript"] = Relationship(back_populates="dating_confidence")


class AuthorMilieu(SQLModel, table=True):
    """Lookup: author milieu (Monastic, Clerical; 'Unknown' becomes NULL)."""

    __tablename__ = "author_milieu"

    author_milieu_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field("Author milieu", unique=True)
    note: Optional[str] = Field(default=None)

    authors: List["Author"] = Relationship(back_populates="milieu")


class Author(SQLModel, table=True):
    """An author, deduplicated by name.

    Anonymous authors ('Anon…' in the workbook) get one row per text, named
    'Anonymous ' + text.identifier (e.g. 'Anonymous BHL_767'), with the raw
    workbook value kept in note (e.g. 'Anon. (same author as BHL 1290)').
    """

    __tablename__ = "author"

    author_id: Optional[int] = Field(default=None, primary_key=True)
    name: str = excel_field("Author of the text", unique=True)
    institutional_training_ground: Optional[str] = excel_field(
        "Institutional training ground of the author", default=None
    )
    regional_antecedents: Optional[str] = excel_field(
        "Regional or local antecedents of the author", default=None
    )
    author_milieu_id: Optional[int] = excel_field(
        "Author milieu", default=None, foreign_key="author_milieu.author_milieu_id"
    )
    note: Optional[str] = Field(default=None)

    milieu: Optional[AuthorMilieu] = Relationship(back_populates="authors")
    texts: List["Text"] = Relationship(back_populates="author")


class Text(SQLModel, table=True):
    """One row per TEXTS-sheet data row.

    identifier is the given, stable identifier: the 'BHL or NO BHL' prefix
    (spaces → '_') joined with '_' to the stringified 'Unique identifier'
    value, e.g. BHL_29, BHL_1055-1056, NO_BHL_ALPER.

    The 'Precise institutional origin?' / 'Precise destinatary?' workbook
    flags are not stored: institution presence implies precision.
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
    reecriture: Optional[bool] = excel_field("Réécriture?", default=None)
    reecriture_text_id: Optional[int] = excel_field(
        "Réécriture of which text(s)? (resolved)",
        default=None,
        foreign_key="text.text_id",
    )
    reecriture_note: Optional[str] = excel_field(
        "Réécriture of which text(s)?", default=None
    )
    dating_range_start: Optional[int] = excel_field(
        "Dating range (beginning)", default=None
    )
    dating_range_stop: Optional[int] = excel_field("Dating range (end)", default=None)
    dating_range: Optional[str] = excel_field(
        "Quarter century chronology", default=None
    )
    dating_confidence_id: Optional[int] = excel_field(
        "Dating confidence rating",
        default=None,
        foreign_key="dating_confidence.dating_confidence_id",
    )
    dating_note: Optional[str] = excel_field("Dating notes", default=None)
    author_id: Optional[int] = excel_field(
        "Author of the text", default=None, foreign_key="author.author_id"
    )
    author_in_destinary_institution: Optional[bool] = excel_field(
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
    creation_note: Optional[str] = Field(default=None)
    destinary_archdiocese_id: Optional[int] = Field(
        default=None, foreign_key="archdiocese.archdiocese_id"
    )
    destinary_diocese_id: Optional[int] = Field(
        default=None, foreign_key="diocese.diocese_id"
    )
    destinary_institution_id: Optional[int] = excel_field(
        "Primary institutional destinatary",
        default=None,
        foreign_key="institution.institution_id",
    )
    destinary_note: Optional[str] = Field(default=None)
    reference: Optional[str] = excel_field("Selected reference", default=None)
    general_note: Optional[str] = excel_field("Notes", default=None)

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
        sa_relationship_kwargs={"foreign_keys": "Text.destinary_archdiocese_id"}
    )
    destinary_diocese: Optional[Diocese] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.destinary_diocese_id"}
    )
    destinary_institution: Optional[Institution] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "Text.destinary_institution_id"}
    )
    editions: List["Edition"] = Relationship(back_populates="text")
    manuscripts: List["Manuscript"] = Relationship(back_populates="text")
    repertory_links: List["RepertoryLink"] = Relationship(back_populates="text")


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
    identifier per text' value, e.g. BHL_29-4. text_id links the copy to
    its text via prefix + 'Unique text identifier'; when that reference does
    not resolve to a text, the manuscript is still imported with text_id
    NULL and the raw reference kept in general_notes.

    Column order follows the MANUSCRIPTS sheet. The codex_* fields describe
    the codex the copy is part of (denormalized onto every copy, as in the
    workbook). location_id resolves 'Manuscript location' to a location row
    by name, created without coordinates when new. dating_range_start/_end
    are 0 when the workbook value is not an integer (e.g. 'Unknown'); the
    raw values are then kept in dating_note. dating_reference stores the
    cell's hyperlink URL when present (display text is often just 'Link').
    URLs (catalogues, Légendiers, images) live in manuscript_link rows.
    """

    __tablename__ = "manuscript"

    manuscript_id: Optional[int] = Field(default=None, primary_key=True)
    identifier: str = excel_field(
        "'BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text'",
        sheet="MANUSCRIPTS",
        unique=True,
        index=True,
    )
    text_id: Optional[int] = excel_field(
        "Unique text identifier (NULL when the reference is unresolvable; "
        "see general_notes)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="text.text_id",
        index=True,
    )
    codex_number: Optional[int] = excel_field(
        "Codex number in database", sheet="MANUSCRIPTS", default=None
    )
    codex_identifier: Optional[str] = excel_field(
        "Codex unique identifier", sheet="MANUSCRIPTS", default=None, index=True
    )
    codex_multiple_copies: Optional[bool] = excel_field(
        "Codex with multiple manuscript copies of texts from corpus",
        sheet="MANUSCRIPTS",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    codex_copy_amount: Optional[int] = excel_field(
        "Codex features n manuscript copies of texts from corpus",
        sheet="MANUSCRIPTS",
        default=None,
    )
    manuscript_preservation_status_id: Optional[int] = excel_field(
        "Preservation status of manuscript copy",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="manuscript_preservation_status.manuscript_preservation_status_id",
    )
    location_id: Optional[int] = excel_field(
        "Manuscript location",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="location.location_id",
    )
    manuscript_holding_institution_id: Optional[int] = excel_field(
        "Manuscript holding institution",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="manuscript_holding_institution.manuscript_holding_institution_id",
    )
    height: Optional[str] = excel_field(
        "Manuscript height", sheet="MANUSCRIPTS", default=None
    )
    width: Optional[str] = excel_field(
        "Manuscript width", sheet="MANUSCRIPTS", default=None
    )
    dating_century: Optional[int] = excel_field(
        "Manuscript dating by (earliest) century", sheet="MANUSCRIPTS", default=None
    )
    dating_range_start: Optional[int] = excel_field(
        "Manuscript dating range start (0 when not an integer in the workbook)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    dating_range_end: Optional[int] = excel_field(
        "Manuscript dating range end (0 when not an integer in the workbook)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    dating_reference: Optional[str] = excel_field(
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
    dating_note: Optional[str] = excel_field(
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
    codex_notes: Optional[str] = excel_field(
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
    origin_diocese_confidence_rating_id: Optional[int] = excel_field(
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
    origin_institution_confidence_rating_id: Optional[int] = excel_field(
        "Manuscript origin confidence rating",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="origin_confidence.origin_confidence_id",
    )
    provenance_early_institute_id: Optional[int] = excel_field(
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
    provenance_later_institute_id: Optional[int] = excel_field(
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
    origin_or_provenance_secondary_reference: Optional[str] = excel_field(
        "Manuscript origin and provenance preferred secondary reference "
        "(hyperlink URL when the cell is hyperlinked)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    manuscript_type_id: Optional[int] = excel_field(
        "Manuscript type (whitespace-normalized label)",
        sheet="MANUSCRIPTS",
        default=None,
        foreign_key="manuscript_type.manuscript_type_id",
    )
    manuscript_type_note: Optional[str] = excel_field(
        "Manuscript type (raw cell, incl. notes on type selection)",
        sheet="MANUSCRIPTS",
        default=None,
    )
    general_notes: Optional[str] = excel_field(
        "'Notes', prefixed with the raw 'Unique text identifier' when it "
        "resolves to no text",
        sheet="MANUSCRIPTS",
        default=None,
    )

    text: Optional["Text"] = Relationship(back_populates="manuscripts")
    preservation_status: Optional[ManuscriptPreservationStatus] = Relationship(
        back_populates="manuscripts"
    )
    location: Optional[Location] = Relationship(back_populates="manuscripts")
    holding_institution: Optional[ManuscriptHoldingInstitution] = Relationship(
        back_populates="manuscripts"
    )
    dating_confidence: Optional[DatingConfidence] = Relationship(
        back_populates="manuscripts"
    )
    vernacular_region: Optional["VernacularRegion"] = Relationship(
        back_populates="manuscripts"
    )
    origin_archdiocese: Optional[Archdiocese] = Relationship(
        back_populates="origin_manuscripts"
    )
    origin_diocese: Optional[Diocese] = Relationship(
        back_populates="origin_manuscripts"
    )
    origin_diocese_confidence: Optional["OriginConfidence"] = Relationship(
        back_populates="diocese_rated_manuscripts",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.origin_diocese_confidence_rating_id"
        },
    )
    origin_institution: Optional[Institution] = Relationship(
        back_populates="origin_manuscripts",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.origin_institution_id"},
    )
    origin_institution_confidence: Optional["OriginConfidence"] = Relationship(
        back_populates="institution_rated_manuscripts",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.origin_institution_confidence_rating_id"
        },
    )
    provenance_early_institute: Optional[Institution] = Relationship(
        back_populates="provenance_early_manuscripts",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.provenance_early_institute_id"
        },
    )
    provenance_early_confidence: Optional["ProvenanceConfidence"] = Relationship(
        back_populates="early_manuscripts",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.provenance_early_confidence_id"},
    )
    provenance_later_institute: Optional[Institution] = Relationship(
        back_populates="provenance_later_manuscripts",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.provenance_later_institute_id"
        },
    )
    provenance_later_confidence: Optional["ProvenanceConfidence"] = Relationship(
        back_populates="later_manuscripts",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.provenance_later_confidence_id"},
    )
    manuscript_type: Optional["ManuscriptType"] = Relationship(
        back_populates="manuscripts"
    )
    links: List["ManuscriptLink"] = Relationship(back_populates="manuscript")
    relations: List["ManuscriptRelation"] = Relationship(
        back_populates="manuscript",
        sa_relationship_kwargs={"foreign_keys": "ManuscriptRelation.manuscript_id"},
    )
    related_by: List["ManuscriptRelation"] = Relationship(
        back_populates="related_manuscript",
        sa_relationship_kwargs={
            "foreign_keys": "ManuscriptRelation.related_manuscript_id"
        },
    )
    edition_links: List["EditionManuscript"] = Relationship(back_populates="manuscript")


class ManuscriptLinkType(SQLModel, table=True):
    """Lookup: what a manuscript URL points at.

    Seeded by the importer with: Images Scan, Images IIIF, Images IIIF MF,
    Images Photos, Catalogue online, Catalogue Bollandist, Catalogue other,
    Legendiers entry, Legendiers alternative.
    """

    __tablename__ = "manuscript_link_type"

    manuscript_link_type_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = Field(unique=True)
    note: Optional[str] = Field(default=None)

    links: List["ManuscriptLink"] = Relationship(back_populates="link_type")


class ManuscriptLink(SQLModel, table=True):
    """A URL attached to a manuscript, typed via manuscript_link_type.

    From the MANUSCRIPTS link columns ('Légendiers entry link', 'Viable
    alternative for Légendiers entry on codex contents', 'Online catalogue
    link', 'Bollandist catalogue link', 'Other relevant catalogue link',
    'Online manuscript images' routed by 'Type of online images'). url is
    the cell's hyperlink target, never its display text ('Link'). notes has
    no Excel source (manual annotation).
    """

    __tablename__ = "manuscript_link"

    manuscript_link_id: Optional[int] = Field(default=None, primary_key=True)
    manuscript_id: int = excel_field(
        "link columns (row)",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript.manuscript_id",
        index=True,
    )
    manuscript_link_type_id: int = excel_field(
        "link column → type",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript_link_type.manuscript_link_type_id",
    )
    url: str = excel_field("link cell hyperlink target", sheet="MANUSCRIPTS")
    note: Optional[str] = Field(default=None)

    manuscript: Optional[Manuscript] = Relationship(back_populates="links")
    link_type: Optional[ManuscriptLinkType] = Relationship(back_populates="links")


class ProvenanceConfidence(SQLModel, table=True):
    """Lookup: A/B/C/D confidence rating for manuscript provenance owners.

    Populated from the early/earliest-owner confidence column (the second
    occurrence of its duplicated header). The undetermined/later owner has
    no confidence column in the workbook yet, so later_manuscripts links
    stay empty for now.
    """

    __tablename__ = "provenance_confidence"

    provenance_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field(
        "Manuscript provenance by early/earliest institutional owner "
        "confidence rating",
        sheet="MANUSCRIPTS",
        unique=True,
    )
    note: Optional[str] = Field(default=None)

    early_manuscripts: List["Manuscript"] = Relationship(
        back_populates="provenance_early_confidence",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.provenance_early_confidence_id"},
    )
    later_manuscripts: List["Manuscript"] = Relationship(
        back_populates="provenance_later_confidence",
        sa_relationship_kwargs={"foreign_keys": "Manuscript.provenance_later_confidence_id"},
    )


class OriginConfidence(SQLModel, table=True):
    """Lookup: A/B/C/D confidence rating for manuscript origin columns."""

    __tablename__ = "origin_confidence"

    origin_confidence_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field(
        "'Manuscript origin by diocese confidence rating' / "
        "'Manuscript origin confidence rating'",
        sheet="MANUSCRIPTS",
        unique=True,
    )
    note: Optional[str] = Field(default=None)

    diocese_rated_manuscripts: List["Manuscript"] = Relationship(
        back_populates="origin_diocese_confidence",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.origin_diocese_confidence_rating_id"
        },
    )
    institution_rated_manuscripts: List["Manuscript"] = Relationship(
        back_populates="origin_institution_confidence",
        sa_relationship_kwargs={
            "foreign_keys": "Manuscript.origin_institution_confidence_rating_id"
        },
    )


class VernacularRegion(SQLModel, table=True):
    """Lookup: vernacular region (distinct values: G, R, F).

    From MANUSCRIPTS 'Vernacular region (Romance/Germanic)'; 'Unknown' and
    'N/A' mean NULL, anything else is reported and skipped.
    """

    __tablename__ = "vernacular_region"

    vernacular_region_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field(
        "Vernacular region (Romance/Germanic)", sheet="MANUSCRIPTS", unique=True
    )
    note: Optional[str] = Field(default=None)

    manuscripts: List["Manuscript"] = Relationship(back_populates="vernacular_region")


class ManuscriptType(SQLModel, table=True):
    """Lookup: manuscript type, one row per distinct whitespace-normalized
    'Manuscript type' value (the raw cell text, which may carry notes on
    type selection, is kept per manuscript in manuscript_type_note).
    """

    __tablename__ = "manuscript_type"

    manuscript_type_id: Optional[int] = Field(default=None, primary_key=True)
    label: str = excel_field(
        "Manuscript type (whitespace-normalized)", sheet="MANUSCRIPTS", unique=True
    )
    note: Optional[str] = Field(default=None)

    manuscripts: List["Manuscript"] = Relationship(back_populates="manuscript_type")


class ManuscriptRelationshipType(SQLModel, table=True):
    """Lookup: how two manuscripts relate.

    Seeded by the importer with 'Based on exemplar' and 'Exemplar of'.
    """

    __tablename__ = "manuscript_relationship_type"

    manuscript_relationship_type_id: Optional[int] = Field(
        default=None, primary_key=True
    )
    label: str = Field(unique=True)
    note: Optional[str] = Field(default=None)

    relations: List["ManuscriptRelation"] = Relationship(
        back_populates="relationship_type"
    )


class ManuscriptRelation(SQLModel, table=True):
    """Link: a manuscript related to another manuscript, typed.

    From the MANUSCRIPTS 'Based on exemplar' and 'Exemplar of which
    manuscript(s)' columns (the latter comma-split); references are resolved
    like the EDITIONS manuscript refs — copy identifier first, then codex
    identifier within the row's own text. note has no Excel source.
    """

    __tablename__ = "manuscript_relation"

    manuscript_relation_id: Optional[int] = Field(default=None, primary_key=True)
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
    manuscript_relationship_type_id: int = excel_field(
        "source column → type",
        sheet="MANUSCRIPTS",
        foreign_key="manuscript_relationship_type.manuscript_relationship_type_id",
    )
    note: Optional[str] = Field(default=None)

    manuscript: Optional[Manuscript] = Relationship(
        back_populates="relations",
        sa_relationship_kwargs={"foreign_keys": "ManuscriptRelation.manuscript_id"},
    )
    related_manuscript: Optional[Manuscript] = Relationship(
        back_populates="related_by",
        sa_relationship_kwargs={
            "foreign_keys": "ManuscriptRelation.related_manuscript_id"
        },
    )
    relationship_type: Optional[ManuscriptRelationshipType] = Relationship(
        back_populates="relations"
    )


class Edition(SQLModel, table=True):
    """One row per EDITIONS-sheet data row.

    text_id links the edition to its text: the EDITIONS 'Unique identifier'
    value is the part of text.identifier after the BHL/NO-BHL prefix.
    identifier_per_text carries that text's prefix (e.g. BHL_29-A), matching
    the text and manuscript identifier convention.
    reprint_of_edition_id resolves 'If reprint, of what?' to another edition
    of the same text (the raw Excel value is kept in reprint_of); references
    are matched first as a per-text edition identifier (e.g. '616-B'), then
    as an '(inc. volume)' identifier within the same text.
    The 'Edition images link' hyperlink URL lives in edition_link, typed by
    the 'Images of edition?' value (SCAN vs Transcription).
    """

    __tablename__ = "edition"

    edition_id: Optional[int] = Field(default=None, primary_key=True)
    text_id: int = excel_field(
        "Unique identifier",
        sheet="EDITIONS",
        foreign_key="text.text_id",
        index=True,
    )
    identifier_per_text: str = excel_field(
        "'BHL or NO BHL' prefix + '_' + 'Edition unique identifier per individual text'",
        sheet="EDITIONS",
        index=True,
    )
    publication_year: Optional[int] = excel_field(
        "Publication year", sheet="EDITIONS", default=None
    )
    reference: Optional[str] = excel_field(
        "Edition reference", sheet="EDITIONS", default=None
    )
    page_numbers: Optional[str] = excel_field(
        "Page numbers", sheet="EDITIONS", default=None
    )
    reprint: Optional[bool] = excel_field("Reprint ?", sheet="EDITIONS", default=None)
    reprint_identical: Optional[bool] = excel_field(
        "If reprint, identically typeset?", sheet="EDITIONS", default=None
    )
    reprint_of_edition_id: Optional[int] = excel_field(
        "If reprint, of what? (resolved)",
        sheet="EDITIONS",
        default=None,
        foreign_key="edition.edition_id",
    )
    reprint_of: Optional[str] = excel_field(
        "If reprint, of what?", sheet="EDITIONS", default=None
    )
    collation_done: Optional[bool] = excel_field(
        "Collation done?",
        sheet="EDITIONS",
        default=None,
        description="Tri-state: true/false/NULL (unknown; a non-tristate "
        "workbook value warns and stays NULL).",
    )
    general_notes: Optional[str] = excel_field("Notes", sheet="EDITIONS", default=None)

    text: Optional["Text"] = Relationship(back_populates="editions")
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
    label: str = Field(unique=True)
    note: Optional[str] = Field(default=None)

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
    url: str = excel_field("'Edition images link' hyperlink target", sheet="EDITIONS")
    note: Optional[str] = Field(default=None)

    edition: Optional[Edition] = Relationship(back_populates="links")
    link_type: Optional[EditionLinkType] = Relationship(back_populates="links")


class EditionManuscript(SQLModel, table=True):
    """Link: a manuscript used by an edition.

    From the EDITIONS 'Manuscript used 1'–'Manuscript used 16' columns; the
    cell references a manuscript either by its per-text copy identifier
    (e.g. '29-1') or by its codex identifier within the edition's text
    (e.g. 'Cologne HA 6'). notes has no Excel source (manual annotation).
    """

    __tablename__ = "edition__manuscripts"

    edition__manuscripts_id: Optional[int] = Field(default=None, primary_key=True)
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
    likely_use_of_a_copy: Optional[bool] = excel_field(
        "Likely use of a copy of Manuscript 1–16?",
        sheet="EDITIONS",
        default=None,
        description="Tri-state: true/false/NULL (unknown).",
    )
    notes: Optional[str] = Field(default=None)

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
    notes: Optional[str] = Field(default=None)

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
    name: str = Field(unique=True)
    note: Optional[str] = Field(default=None)

    links: List["RepertoryLink"] = Relationship(back_populates="repertory")


class RepertoryLink(SQLModel, table=True):
    """Link: a text's entry in a repertory, curated by hand."""

    __tablename__ = "repertory_link"

    repertory_link_id: Optional[int] = Field(default=None, primary_key=True)
    text_id: int = Field(foreign_key="text.text_id", index=True)
    repertory_id: int = Field(foreign_key="repertory.repertory_id", index=True)
    url: Optional[str] = Field(default=None)
    note: Optional[str] = Field(default=None)

    text: Optional["Text"] = Relationship(back_populates="repertory_links")
    repertory: Optional[Repertory] = Relationship(back_populates="links")
