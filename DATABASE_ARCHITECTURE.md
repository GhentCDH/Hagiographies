# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its database model.

> **Schema restart (July 2026).** The schema and importer were rebuilt from
> scratch, starting from the TEXTS worksheet. Entities are added back
> incrementally. The previous 20-table model is parked, reference only, in
> `utils/utilities/src/utilities/legacy_model.py` and
> `utils/importer/src/importer/legacy/`.

## 1 Project Structure

The project is organized into modular directories, separating the Python import/export logic from the administrative interface.

```text
.
├── caddy/                  # Reverse proxy configuration (Caddyfile)
├── data/                   # Gitignored: databases and Excel sources
├── dataflow/               # Dataflow config for the SQLite export
├── utils/                  # Python backend utilities (UV-managed)
│   ├── importer/           # Excel-to-PostgreSQL pipeline (typer CLI)
│   ├── documenter/         # Schema diagram generator
│   ├── mathesar/           # Mathesar config via JSON-RPC (summaries, display)
│   ├── utilities/          # Core: SQLModel definitions and DB configuration
│   └── Dockerfile          # Python utilities container
├── compose.yml             # System orchestration
└── justfile                # Project command runner
```

## 2 Database Engine and Conventions

The application targets **PostgreSQL** as its single source of truth. The
model lives in `utils/utilities/src/utilities/model.py` (SQLModel).

Conventions:

- Primary keys are `<table>_id` (autoincrement), never plain `id`.
- Every imported field records its source Excel column via the
  `excel_field()` helper — as a pydantic description **and** as a PostgreSQL
  column comment, so the Excel provenance is visible in `\d+` and in
  Mathesar.
- The importer never fixes Excel data: rows failing strict validation are
  skipped and reported (see `AGENTS.md`, "Import Policy"). Two documented,
  deliberate exceptions: manuscript preservation-status labels are matched
  case-insensitively to `Lost`/`Preserved`, and holding-institution names
  differing only in case/whitespace are merged into one row (most frequent
  spelling wins).

Operational details (lifecycle commands, backups, connectivity) are documented in `POSTGRESQL.md`.

## 3 Tables

Source worksheets: `TEXTS`, `MANUSCRIPTS` and `EDITIONS` of the corpus
workbook (`EXCEL_FILE` in `data/`).

### text

One row per TEXTS data row.

| Column | Type | Excel source (TEXTS) |
| :--- | :--- | :--- |
| `text_id` | integer PK | — |
| `identifier` | varchar, unique, not null | `'BHL or NO BHL'` + `_` + `'Unique identifier'` (e.g. `BHL_29`, `NO_BHL_ALPER`) |
| `title` | varchar | `Title of the work` |
| `approximate_token_count` | integer | `Approximate token count` |
| `text_form_id` | FK → `text_form` | `Prose or verse` |
| `text_source_type_id` | FK → `text_source_type` | `Source type` |
| `text_source_subtype_id` | FK → `text_source_subtype` | `Subtype` |

### manuscript

One row per MANUSCRIPTS data row (one manuscript copy of a text).

| Column | Type | Excel source (MANUSCRIPTS) |
| :--- | :--- | :--- |
| `manuscript_id` | integer PK | — |
| `identifier` | varchar, unique, not null | `'BHL or NO BHL'` + `_` + `'Manuscript copy unique identifier per text'` (e.g. `BHL_29-4`) |
| `title` | varchar | `Title` |
| `manuscript_preservation_status_id` | FK → `manuscript_preservation_status` | `Preservation status of manuscript copy` |
| `manuscript_holding_institution_id` | FK → `manuscript_holding_institution` | `Manuscript holding institution` (`N/A` → NULL) |

### edition

One row per EDITIONS data row (basic metadata only for now).

| Column | Type | Excel source (EDITIONS) |
| :--- | :--- | :--- |
| `edition_id` | integer PK | — |
| `title` | varchar, not null | `Title` |
| `publication_year` | integer | `Publication year` |
| `reprint` | boolean | `Reprint ?` (YES/NO) |

### Lookup tables

Each holds the distinct values of one worksheet column, get-or-created at
import time; all have a `<table>_id` PK and a unique label/name.

| Table | Excel source | Values (June 2026 corpus) |
| :--- | :--- | :--- |
| `text_form` | TEXTS `Prose or verse` | Prose, Verse |
| `text_source_type` | TEXTS `Source type` | Biography, Hagiography, Hagiography and Biography |
| `text_source_subtype` | TEXTS `Subtype` | Vita, Miracula, Sermon, Translatio/Elevatio, … (8) |
| `manuscript_preservation_status` | MANUSCRIPTS `Preservation status of manuscript copy` | Lost, Preserved (case-insensitive canonicalisation) |
| `manuscript_holding_institution` | MANUSCRIPTS `Manuscript holding institution` | ~134 deduplicated institutions (case/whitespace variants merged) |

## 4 Import Pipeline

`utils/importer/` — see `utils/importer/README.md` for the CLI. Metadata
(DDL) creation and data import are separate operations; validation is strict
and rejected rows are reported with their Excel row numbers to the console
and to `data/import_report.csv`.

## 5 Diagram

`just db_diagram` regenerates `data/hagiographies_model.svg` from the live
model classes.
