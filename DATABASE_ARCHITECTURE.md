# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its comprehensive database models.

## 1 Project Structure

The project is organized into modular directories, separating the Python import/export logic from the administrative interface.

```text
.
├── caddy/                  # Reverse proxy configuration (Caddyfile)
├── data/                   # Gitignored: databases and Excel sources
├── local-map/              # Static MapLibre GL JS frontend
├── utils/                  # Python backend utilities (UV-managed)
│   ├── importer/           # Excel-to-PostgreSQL pipeline
│   ├── exporter/           # PostgreSQL-to-SQLite + GeoJSON pipelines
│   ├── documenter/         # Schema diagram generator
│   ├── mathesar/           # Mathesar record-summary config (JSON-RPC)
│   ├── utilities/          # Core: SQLModel definitions and DB configuration
│   └── Dockerfile          # Python utilities container
├── compose.yml             # System orchestration
└── justfile                # Project command runner
```

## 2 Database Engine Compatibility

While the application currently defaults to **SQLite** (using STRICT mode) for local development and simplicity, the architecture is designed to be **PostgreSQL-ready**.

### Cross-Engine Abstractions
The models in `utilities/model.py` use custom field helpers to handle the differences between SQLite (STRICT) and PostgreSQL types:
*   `_text`: Maps to `TEXT` (SQLite) or `VARCHAR/TEXT` (Postgres).
*   `_real`: Maps to `REAL` (SQLite) or `FLOAT/DOUBLE` (Postgres).
*   `_bool`: Maps to `INTEGER` (0/1) in SQLite STRICT mode and standard `BOOLEAN` in PostgreSQL.

The `_STRICT` dict (`{"sqlite_strict": True}`) is applied conditionally — only when `DATABASE_URL` points to SQLite — so all models remain schema-compatible with PostgreSQL without modification.

### Migration Path
Detailed instructions for transitioning the "Source of Truth" from SQLite to PostgreSQL can be found in `MIGRATION_POSTGRESQL.md`.

## 3 Enums

The following Python enumerations are used for constrained text columns:

| Enum | Values | Used on |
| :--- | :--- | :--- |
| `ExternalResourceType` | `iiif_scan`, `bollandist_catalog`, `catalog_link`, `scan`, `other` | `ExternalResource.resource_type` |
| `RelationType` | `copy_of`, `exemplar_of`, `other` | `ManuscriptRelation.relation_type` |
| `Certainty` | `certain`, `probable`, `uncertain` | `ManuscriptRelation.certainty` |
| `ReprintType` | `identically_typeset`, `newly_typeset`, `to_be_verified` | `Edition.reprint_type` |
| `ChurchEntityType` | `archdiocese`, `diocese` | `ChurchEntity.entity_type` |

## 4 Database Models

All primary models inherit from `Table`, which provides:
*   `id` — auto-incrementing integer primary key.
*   `created_at` / `updated_at` — audit timestamps, re-ordered to appear last in each table.

Models categorized below based on their visibility in the admin UI (Mathesar) and their structural role.

### 4.1 Primary Entities (Exposed in Admin UI)

These models are the main data management effort, surfaced in the Mathesar admin UI.

#### Text
Central hagiographic work entry, identified by its BHL number. Author location and milieu live on `Author`, not here.
*   **Fields**: `bhl_number`, `title`, `word_count`, `code`
*   **Repertory checks**: `checked_bhl`, `checked_isb`, `checked_naso`, `checked_dg`, `checked_philippart`, `checked_secondary`
*   **Chronology**: `dating_rough`, `dating_precise`
*   **Precision flags**: `is_origin_precise`, `is_destinatary_precise`
*   **Rewrite**: `is_rewrite`, `rewrite_notes` (free text — not a FK), `is_based_on_pre880`
*   **Edition links**: `preferred_edition`, `edition_link_aass`, `edition_link_other`, `edition_link_mgh`, `edition_link_1`, `edition_link_2`
*   **OCR**: `is_ocr_pre_1800`, `is_ocr_post_1800`, `full_ocr_bhl_refs` (BHL ref list — not a bool), `is_ocr_cleaned`, `ocr_comments`
*   **Other**: `key_bibliography`, `notes`, `author_locally_based` (free text — not a bool)
*   **Relationships**: Links to `Author`, `Place` (origin + primary destinatary), `ChurchEntity` (origin archdiocese + diocese), `Typology` (source type + subtype), `TextType`.

#### Manuscript
Physical witness of one or more texts. Text-specific metadata (archdiocese, bishopric, folio pages) lives on `ManuscriptText`.
*   **Fields**: `unique_id`, `shelfmark`, `collection_identifier`, `dating_precise`, `dimension_width_cm`, `dimension_height_cm`, `notes`, `witness_relation_notes`
*   **Repertory checks**: `checked_leg`, `checked_dg`, `checked_naso`, `checked_ed_sec`
*   **Relationships**: Links to `ManuscriptIdentifier`, `Place` (collection), `Institution` (heritage + provenance), `ChurchEntity` (provenance archdiocese + diocese), `DatingCentury`, `ProvenanceGeneral`, `VernacularRegion`, `ManuscriptType`. Has `Image` records and `ExternalResource` records.

#### Edition
Printed or digital edition of a hagiographic text.
*   **Fields**: `bhl_number`, `title`, `edition_identifier`, `edition_reference_per_text`, `bibliographic_reference`, `page_range`, `notes`
*   **Identifiers**: `unique_id_numeric`, `unique_id_descriptive`
*   **Date**: `year_of_publication`
*   **Repertory checks**: `checked_dg`, `checked_naso`, `checked_ed_sec`
*   **Reprint**: `is_reprint`, `reprint_type` (`ReprintType` enum), `reprint_of`, `reprint_notes`
*   **Transcription**: `has_transcription`, `is_our_transcription`, `transcription_notes`, `is_collated`
*   **Other**: `edition_refs`
*   **Relationships**: Links to `Text`. Has associations with `Manuscript` (via `EditionManuscript`) and `ExternalResource` (via `EditionExternalResource`).

#### Author
Hagiographic author, enriched with locality and milieu metadata. Each author is enriched exactly once; fields were moved here from `Text` to avoid duplication across entries.
*   **Fields**: `name`
*   **Relationships**: Links to `Place` (origin via `place_id`, education via `education_place_id`, antecedents via `earlier_place_id`) and `Milieu`.

#### Place
Geographic lookup, optionally enriched with GPS coordinates.
*   **Fields**: `name`, `lat`, `lon`
*   **Unique constraint**: `name`
*   **Relationships**: Bidirectional links to `Author` (3 roles), `Institution`, `Text` (origin + destinatary).

#### Institution
Libraries, archives, and heritage centers, optionally linked to a place.
*   **Fields**: `name`
*   **Unique constraint**: `name`
*   **Relationships**: Linked to a `Place`.

### 4.2 Supporting Models (Managed via Links)

These models define taxonomy or context and are typically managed within the record view of primary entities.

#### ChurchEntity
An ecclesiastical entity: archdiocese or diocese. The `entity_type` field allows the same place-name (e.g. "Trier") to exist as both an archdiocese and a diocese record without violating the unique constraint on `(name, entity_type)`.
*   **Fields**: `name`, `entity_type` (`ChurchEntityType` enum: `archdiocese` / `diocese`)

#### Typology
Hierarchical source categories (e.g. Vita > Passio). Self-referential via `parent_id`.
*   **Fields**: `name`, `parent_id` (FK → `Typology.id`)

#### ManuscriptIdentifier
Canonical grouping of witnesses under a shared title and BHL number.
*   **Fields**: `title`, `bhl_number`, `identifier`
*   **Unique constraint**: `(title, bhl_number)`

#### Milieu
The intellectual or social milieu associated with an author.
*   **Fields**: `name`

#### VernacularRegion
Vernacular region category (e.g. Romance, Germanic).
*   **Fields**: `region`

#### ProvenanceGeneral
General provenance description for a manuscript.
*   **Fields**: `description`

#### TextType
Prose vs. verse classification for a hagiographic text.
*   **Fields**: `name`

#### ImageType
Image delivery type (e.g. `iiif`, `iiif_mf`, `scan`, `iphone_photo`).
*   **Fields**: `name`

#### DatingCentury
A century used for manuscript dating (stored as integer, e.g. `10` for the Xth century).
*   **Fields**: `century` (`INTEGER`)

#### ManuscriptType
Type classification for a manuscript (e.g. legendarium, collectio).
*   **Fields**: `name`

### 4.3 Structural & Internal Tables (Join Tables)

These models define the "glue" of the database and are largely transparent in the UI. They do **not** inherit from `Table`; `ExternalResource` and `ManuscriptRelation` define their own `id`, `created_at`, and `updated_at` columns.

#### ManuscriptText
Complex M2M join for Manuscript ↔ Text. Carries per-occurrence metadata.
*   **Composite PK**: `(ms_id, text_id)`
*   **Fields**: `folio_pages`, `ms_number_per_bhl`, `text_archdiocese_id` (FK → `ChurchEntity`), `text_bishopric_id` (FK → `ChurchEntity`), `text_origin_place_id` (FK → `Place`)

#### ManuscriptRelation
A directed relationship (copy, exemplar) between two manuscript witnesses.
*   **Fields**: `relation_type` (`RelationType` enum), `certainty` (`Certainty` enum), `notes`, `source_reference`
*   **Unique constraint**: `(source_manuscript_id, target_manuscript_id, relation_type)`

#### ExternalResource
An external hyperlink (scan, catalog) associated with a manuscript.
*   **Fields**: `url`, `resource_type` (`ExternalResourceType` enum), `comment`, `is_alive`
*   **Unique constraint**: `(manuscript_id, url)`
*   **Relationships**: Directly linked to `Manuscript`; also linked to `Edition` via `EditionExternalResource`.

#### EditionManuscript
M2M join for Edition ↔ Manuscript, with inspection metadata.
*   **Composite PK**: `(edition_id, ms_id)`
*   **Fields**: `inspection_status`

#### EditionExternalResource
M2M join for Edition ↔ ExternalResource (e.g. scan links).
*   **Composite PK**: `(edition_id, resource_id)`

#### Image
A digitized image URL associated with a manuscript.
*   **Fields**: `url`, `comment`
*   **Relationships**: Links to `Manuscript` and `ImageType`.
*   **Unique constraint**: `(ms_id, url)`

## 5 Entity Relationship Matrix

| Source Model | Destination Model | Relationship Type | UI Visibility |
| :--- | :--- | :--- | :--- |
| **Text** | Author | Many-to-One | Main dropdown |
| **Text** | Typology (×2) | Many-to-One | Category lookups (type + subtype) |
| **Text** | ChurchEntity (×2) | Many-to-One | Origin archdiocese + diocese |
| **Text** | Place (×2) | Many-to-One | Origin + primary destinatary |
| **Text** | TextType | Many-to-One | Prose/verse classification |
| **Edition** | Text | Many-to-One | Record link |
| **Edition** | Manuscript | Many-to-Many (EditionManuscript) | Evidence link |
| **Edition** | ExternalResource | Many-to-Many (EditionExternalResource) | Scan links |
| **Manuscript** | ManuscriptText | One-to-Many | Sub-table view |
| **Manuscript** | Image | One-to-Many | Image records |
| **Manuscript** | ExternalResource | One-to-Many | Hyperlink list |
| **ManuscriptText** | Text | Many-to-One | Record link |
| **ManuscriptText** | ChurchEntity (×2) | Many-to-One | Per-text archdiocese + bishopric |
| **ManuscriptText** | Place | Many-to-One | Per-text origin place |
| **ManuscriptRelation** | Manuscript (×2) | Many-to-Many | Directed witness relation |
| **Author** | Place (×3) | Many-to-One | Origin, education, antecedents |
| **Author** | Milieu | Many-to-One | Intellectual context |
| **Institution** | Place | Many-to-One | Geographic anchor |

---
*Last Updated: 22 April 2026*
