# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its comprehensive database models.

## 1 Project Structure

The project is organized into modular directories, separating the Python import/export logic from the administrative interface.

```text
.
├── caddy/                  # Reverse proxy configuration (Caddyfile)
├── data/                   # Gitignored: SQLite databases and Excel sources
├── kottster/               # Administrative interface (Node.js/React)
│   ├── app/                # Main app logic and UI definitions
│   │   └── pages/          # Individual page configurations (JSON)
│   └── Dockerfile          # Admin panel container
├── local-map/              # Static MapLibre GL JS frontend
├── utils/                  # Python backend utilities (UV-managed)
│   ├── importer/           # Excel-to-SQLite pipeline
│   ├── exporter/           # SQLite-to-GeoJSON pipeline
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

### Migration Path
Detailed instructions for transitioning the "Source of Truth" from SQLite to PostgreSQL can be found in `MIGRATION_POSTGRESQL.md`.

## 3 Database Models

Models are categorized below based on their visibility in the Kottster Admin UI and their structural role.

### 3.1 Primary Entities (Exposed in Admin UI)

These models have dedicated pages in the Kottster sidebar and constitute the main data management effort.

#### Text
Central bibliographic work entry.
*   **Fields**: `bhl_number`, `title`, `word_count`, `checked_bhl`, `checked_isb`, `checked_naso`, `checked_dg`, `checked_philippart`, `checked_secondary`, `dating_rough`, `dating_precise`, `is_rewrite`, `rewrite_notes`, `author_locally_based`, `full_ocr_bhl_refs`, `ocr_comments`.
*   **Relationships**: Links to `Author`, `Place` (Origin/Destinatary), `ChurchEntity` (Origin), and `Typology`.

#### Manuscript
Physical witness of one or more texts.
*   **Fields**: `unique_id`, `shelfmark`, `collection_identifier`, `dating_precise`, `dimension_width_cm`, `dimension_height_cm`, `notes`, `witness_relation_notes`.
*   **Relationships**: Links to `ManuscriptIdentifier`, `Place` (Collection), `Institution` (Owner/Provenance), `ChurchEntity` (Provenance), and `DatingCentury`.

#### Edition
Printed or digital editions of a Text.
*   **Fields**: `short_id`, `long_id`, `year`, `reprint_type`, `inspection_status`, `notes`.
*   **Relationships**: Links to `Text`. Has associations with `Manuscript` and `ExternalResource`.

#### Author
Hagiographic authors enriched with locality metadata.
*   **Fields**: `name`.
*   **Relationships**: Links to `Place` (Origin/Education/Antecedents) and `Milieu`.

#### Place
Geographic lookups with coordinates.
*   **Fields**: `name`, `lat`, `lon`.
*   **Relationships**: Bidirectional links to `Author`, `Institution`, and `Text`.

#### Institution
Libraries, archives, and heritage centers.
*   **Fields**: `name`.
*   **Relationships**: Linked to a `Place`.

### 3.2 Supporting Models (Managed via Links)

These models define taxonomy or context and are typically managed within the record view of primary entities.

#### ChurchEntity
Ecclesiastical hierarchy (Archdioceses and Dioceses).
*   **Fields**: `name`, `entity_type` (archdiocese/diocese).

#### Typology
Hierarchical source categories (e.g., Vita > Passio).
*   **Fields**: `name`, `parent_id` (Self-referential).

#### ManuscriptIdentifier
Canonical grouping of witnesses under a title and BHL number.
*   **Fields**: `title`, `bhl_number`, `identifier`.

#### Millieu / VernacularRegion / ProvenanceGeneral / TextType / ImageType
Simple categorization tables used as dropdown lookups in the UI.

### 3.3 Structural & Internal Tables (Join Tables)

These models define the "glue" of the database and are largely transparent in the UI.

#### ManuscriptText
Complex join table for Manuscript ↔ Text.
*   **Fields**: `folio_pages`, `ms_number_per_bhl`.
*   **Relationships**: Specific ecclesiastical and geographic context for a text witness.

#### ManuscriptRelation
Directed witness-to-witness links (e.g., "Manuscript A is a copy of Manuscript B").
*   **Fields**: `relation_type` (Enum), `certainty` (Enum), `notes`, `source_reference`.

#### ExternalResource
Hyperlinks to scans and catalogs.
*   **Fields**: `url`, `resource_type`, `is_alive`.

#### EditionManuscript / EditionExternalResource
Many-to-Many associations between Editions, Manuscripts, and Scans.

## 4 Entity Relationship Matrix

| Source Model | Destination Model | Relationship Type | UI Visibility |
| :--- | :--- | :--- | :--- |
| **Text** | Author | Many-to-One | Main Dropdown |
| **Text** | Typology | Many-to-One | Category Lookup |
| **Manuscript** | ManuscriptText | One-to-Many | Sub-table View |
| **ManuscriptText** | Text | Many-to-One | Record Link |
| **ManuscriptText** | ChurchEntity | Many-to-One | Context Selection |
| **ManuscriptRelation**| Manuscript | Many-to-Many | Relation Graph |
| **Author** | Place | Many-to-One | Metadata Pickup |
| **Edition** | Manuscript | Many-to-Many | Evidence Link |
| **ExternalResource** | Manuscript | Many-to-One | Hyperlink List |

---
*Last Updated: April 15, 2026*
