# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its comprehensive database models.

## 1 Project Structure

The project is organized into modular directories, separating the Python import/export logic from the administrative interface.

```text
.
├── caddy/                  # Reverse proxy configuration (Caddyfile)
├── data/                   # Gitignored: databases and Excel sources
├── dataflow/               # Dataflow config for the SQLite export
├── utils/                  # Python backend utilities (UV-managed)
│   ├── importer/           # Excel-to-PostgreSQL pipeline
│   ├── documenter/         # Schema diagram generator
│   ├── mathesar/           # Mathesar record-summary config (JSON-RPC)
│   ├── utilities/          # Core: SQLModel definitions and DB configuration
│   └── Dockerfile          # Python utilities container
├── compose.yml             # System orchestration
└── justfile                # Project command runner
```

## 2 Database Engine

The application targets **PostgreSQL** as its single source of truth. The models in `utilities/model.py` use custom field helpers for column types:
*   `_text`: Maps to `TEXT`.
*   `_real`: Maps to `REAL`.
*   `_bool`: Maps to `BOOLEAN`.

Operational details (lifecycle commands, backups, connectivity) are documented in `MIGRATION_POSTGRESQL.md`.

## 3 Enums

The following Python enumerations are used for constrained text columns:

| Enum | Values | Used on |
| :--- | :--- | :--- |
| `ExternalResourceType` | `iiif_scan`, `bollandist_catalog`, `catalog_link`, `scan`, `other` | `ExternalResource.resource_type` |
| `RelationType` | `copy_of`, `exemplar_of`, `other` | `ManuscriptRelation.relation_type` |
| `Certainty` | `certain`, `probable`, `uncertain` | `ManuscriptRelation.certainty` |
| `ChurchEntityType` | `archdiocese`, `diocese` | `ChurchEntity.entity_type` |

## 4 Database Models

All primary models inherit from `Table`, which provides:
*   `id` — auto-incrementing integer primary key.

Models categorized below based on their visibility in the admin UI (Mathesar) and their structural role.

### 4.1 Primary Entities (Exposed in Admin UI)

These models are the main data management effort, surfaced in the Mathesar admin UI.

#### Text
Central hagiographic work entry. Column names mirror the TEXTS sheet headers.
*   **Identifiers**: `bhl_or_no_bhl` ('BHL or NO BHL'), `unique_identifier` (the key other sheets join on)
*   **Fields**: `title`, `approximate_token_count`, `prose_or_verse`
*   **Chronology**: `quarter_century_chronology`, `dating_range_start`, `dating_range_end`, `dating_notes`, `dating_confidence_rating`
*   **Precision flags**: `is_origin_precise`, `is_destinatary_precise`
*   **Rewrite**: `is_rewrite` ('Réécriture?'), `rewrite_notes` (free text — not a FK)
*   **Other**: `author_locally_based` ('Is author based in destinatary institution?' — attribute of the text, not the author), `authorship_confidence_rating` (uncertain attributions, from '?' in the source), `selected_reference`, `notes`
*   **Relationships**: Links to `Author`, `Place` (origin + primary destinatary), `ChurchEntity` (origin archdiocese + diocese), `Typology` (source type + subtype).

#### Codex
Physical codex (book), one row per 'Codex unique identifier' (e.g. "Montpellier 2"). Holds everything belonging to the physical object.
*   **Identifiers**: `codex_unique_identifier`, `codex_number_in_database`
*   **Codex**: `codex_with_multiple_copies`, `codex_copies_count`, `is_composite_codex`
*   **Fields**: `shelfmark`, `dimension_width_cm`, `dimension_height_cm`, dating fields, Légendiers fields, origin/provenance fields
*   **Relationships**: Links to `Place` (location + origin), `Institution` (holding + provenance), `ChurchEntity` (origin archdiocese + diocese), `DatingCentury`, `VernacularRegion`, `ManuscriptType`. Has `Manuscript` copies, `Image` records and `ExternalResource` records (catalogue links).

#### Manuscript
A manuscript copy: one text as witnessed in one codex — one row per MANUSCRIPTS sheet row.
*   **Identifier**: `manuscript_copy_identifier_per_text` ('Manuscript copy unique identifier per text', e.g. "29-3" — referenced by editions and exemplar relations; unique)
*   **Fields**: `preservation_status`, `folio_or_page_range`, `notes`
*   **Relationships**: Belongs to a `Codex` and a `Text`. Has edition associations (via `EditionManuscript`) and directed `ManuscriptRelation`s (`copy_of` / `exemplar_of`).

#### Edition
Printed or digital edition of a hagiographic text. Column names mirror the EDITIONS sheet headers.
*   **Identifiers**: `edition_unique_identifier_per_text` ('Edition unique identifier per individual text', e.g. "693-B" — the per-edition key), `text_unique_identifier` (the shared text key)
*   **Volume**: `volume_id` → `EditionVolume` ('Edition unique identifier (inc. volume)', e.g. "AASS Jul. 4 (3rd.)") — all editions in the same book share a volume row
*   **Fields**: `title`, `publication_year`, `edition_reference`, `page_numbers`, `editions_consulted` (raw), `notes`
*   **Reprint**: `is_reprint`, `reprint_identically_typeset`, `reprint_newly_typeset`, `reprint_of`
*   **Images & transcription**: `images_of_edition`, `edition_images_link`, `transcription_available`, `collation_done`
*   **Relationships**: Links to `Text` and `EditionVolume`. Has associations with `Manuscript` copies (via `EditionManuscript`, incl. `likely_copy`), consulted volumes (via `EditionConsultedVolume`), and `ExternalResource` (via `EditionExternalResource`).

#### Author
Hagiographic author. Column names mirror the TEXTS sheet columns Q–S. Anonymous authors are kept distinct as `Anon.-1`, `Anon.-2`, … so their per-text metadata is not merged.
*   **Fields**: `name`, `institutional_training_ground`, `regional_antecedents`, `milieu`

#### Place
Geographic lookup, optionally enriched with GPS coordinates. '?' markers in source names are stripped into `confidence_rating`.
*   **Fields**: `name`, `lat`, `lon`, `confidence_rating`
*   **Unique constraint**: `name`
*   **Relationships**: Bidirectional links to `Institution`, `Text` (origin + destinatary).

#### Institution
Libraries, archives, monasteries and heritage centers, optionally linked to a place. Covers both modern holding institutions and medieval provenance owners. '?' markers in source names are stripped into `confidence_rating`.
*   **Fields**: `name`, `lat`, `lon`, `confidence_rating`
*   **Unique constraint**: `name`
*   **Relationships**: Linked to a `Place`.

### 4.2 Supporting Models (Managed via Links)

These models define taxonomy or context and are typically managed within the record view of primary entities.

#### ChurchEntity
An ecclesiastical entity: archdiocese or diocese. The `entity_type` field allows the same place-name (e.g. "Trier") to exist as both an archdiocese and a diocese record without violating the unique constraint on `(name, entity_type)`.
*   **Fields**: `name`, `entity_type` (`ChurchEntityType` enum: `archdiocese` / `diocese`), `confidence_rating`, `lat`/`lon` (fallback GPS used when a text/codex has no origin institution)

#### Typology
Hierarchical source categories (e.g. Vita > Passio). Self-referential via `parent_id`.
*   **Fields**: `name`, `parent_id` (FK → `Typology.id`)

#### EditionVolume
A physical book/volume containing one or more editions ('Edition unique identifier (inc. volume)').
*   **Fields**: `identifier` (unique)

#### VernacularRegion
Vernacular region category (e.g. Romance, Germanic).
*   **Fields**: `region`

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

These models define the "glue" of the database and are largely transparent in the UI. They do **not** inherit from `Table`; `ExternalResource` and `ManuscriptRelation` define their own `id` column.

#### ManuscriptRelation
A directed relationship between two manuscript copies, stored exactly as the source records it: `copy_of` ('Based on exemplar' — source is a copy of target) and `exemplar_of` ('Exemplar of which manuscript(s)' — source was used to make target).
*   **Fields**: `relation_type` (`RelationType` enum), `certainty` (`Certainty` enum), `notes`, `source_reference`
*   **Unique constraint**: `(source_manuscript_id, target_manuscript_id, relation_type)`

#### ExternalResource
An external hyperlink (scan, catalogue) associated with a codex or edition.
*   **Fields**: `url`, `resource_type` (`ExternalResourceType` enum), `comment`, `is_alive`
*   **Unique constraint**: `(codex_id, url)`
*   **Relationships**: Directly linked to `Codex`; also linked to `Edition` via `EditionExternalResource`.

#### EditionManuscript
M2M join for Edition ↔ Manuscript copy, with inspection metadata.
*   **Composite PK**: `(edition_id, ms_id)`
*   **Fields**: `inspection_status`, `likely_copy` ('Likely use of a copy of Manuscript N?')

#### EditionConsultedVolume
Join: Edition → volume(s) consulted while preparing it ('Edition used or consulted 1..5').
*   **Composite PK**: `(edition_id, volume_id)`

#### EditionExternalResource
M2M join for Edition ↔ ExternalResource (e.g. scan links).
*   **Composite PK**: `(edition_id, resource_id)`

#### Image
A digitized image URL associated with a codex. `url` is the source link as recorded in the workbook (often a viewer/landing page); `iiif_manifest_url` is the validated IIIF manifest link maintained by `just check-iiif` / `just fix-iiif` — renderable in any IIIF viewer, e.g. `https://tify.rocks/?manifest=<iiif_manifest_url>`.
*   **Fields**: `url`, `iiif_manifest_url`, `comment`
*   **Relationships**: Links to `Codex` and `ImageType`.
*   **Unique constraint**: `(codex_id, url)`

## 5 Entity Relationship Matrix

| Source Model | Destination Model | Relationship Type | UI Visibility |
| :--- | :--- | :--- | :--- |
| **Text** | Author | Many-to-One | Main dropdown |
| **Text** | Typology (×2) | Many-to-One | Category lookups (type + subtype) |
| **Text** | ChurchEntity (×2) | Many-to-One | Origin archdiocese + diocese |
| **Text** | Place (×2) | Many-to-One | Origin + primary destinatary |
| **Edition** | Text | Many-to-One | Record link |
| **Edition** | EditionVolume | Many-to-One | Containing book/volume |
| **Edition** | Manuscript | Many-to-Many (EditionManuscript) | Evidence link (with likely_copy) |
| **Edition** | EditionVolume | Many-to-Many (EditionConsultedVolume) | Consulted volumes |
| **Edition** | ExternalResource | Many-to-Many (EditionExternalResource) | Scan links |
| **Manuscript** | Codex | Many-to-One | Physical carrier |
| **Manuscript** | Text | Many-to-One | Witnessed text |
| **Codex** | Image | One-to-Many | Image records |
| **Codex** | ExternalResource | One-to-Many | Catalogue links |
| **ManuscriptRelation** | Manuscript (×2) | Many-to-Many | Directed copy/exemplar relation |
| **Institution** | Place | Many-to-One | Geographic anchor |

---
*Last Updated: 6 July 2026*
