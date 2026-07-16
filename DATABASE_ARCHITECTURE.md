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
| `reecriture` | boolean | `Réécriture?` |
| `reecriture_text_id` | FK → `text` (self) | `Réécriture of which text(s)?`, resolved (strip `BHL `, match uid) |
| `reecriture_note` | varchar | `Réécriture of which text(s)?`, raw (`N/A` → NULL) |
| `dating_range_start` / `dating_range_stop` | integer | `Dating range (beginning)` / `(end)` |
| `dating_range` | varchar | `Quarter century chronology` |
| `dating_confidence_id` | FK → `dating_confidence` | `Dating confidence rating` (A–D) |
| `dating_note` | varchar | `Dating notes` |
| `author_id` | FK → `author` | `Author of the text` (see author rules) |
| `author_in_destinary_institution` | boolean (tri-state) | `Is author based in destinatary institution?` |
| `creation_archdiocese_id` / `creation_diocese_id` / `creation_institution_id` | FKs | `Text creation - location by archdiocese/diocese/institution` |
| `creation_note` | varchar | — (manual) |
| `destinary_archdiocese_id` / `destinary_diocese_id` | FKs | — (no source column yet; manual) |
| `destinary_institution_id` | FK → `institution` | `Primary institutional destinatary` |
| `destinary_note` | varchar | — (manual) |
| `reference` | varchar | `Selected reference` |
| `general_note` | varchar | `Notes` |

The `'Precise institutional origin?'`/`'Precise destinatary?'` flags are not
stored. `'Unknown'`/`'N/A'` in geo/milieu columns → NULL.

### Geography and authors

| Table | Columns | Notes |
| :--- | :--- | :--- |
| `location` | `location_id` PK, `name`, `latitude`, `longitude` | Deduped by coordinates; name = first entity at the point. **The workbook GPS headers are swapped**: '… GPS Longitude' holds lat ×10⁶, '… GPS Latitude' holds lon ×10⁶; read swapped/unscaled, must be in W-Europe (lat 44–56, lon −2–10) else warning. |
| `archdiocese`, `diocese` | `<t>_id` PK, `name` unique, `location_id` FK (NULL for now), `note` | No coordinates in TEXTS yet. |
| `institution` | `institution_id` PK, `name` unique, `location_id` FK, `note` | Location from the institution's GPS pair (first occurrence wins). |
| `dating_confidence` | `dating_confidence_id` PK, `label` unique, `notes` | A/B/C/D. |
| `author_milieu` | `author_milieu_id` PK, `label` unique, `note` | Monastic, Clerical ('Unknown' → NULL). |
| `author` | `author_id` PK, `name` unique, `institutional_training_ground`, `regional_antecedents`, `author_milieu_id` FK, `note` | Deduped by name. Anonymous (`Anon…`) = one row per text, `name` = `Anonymous <text.identifier>`, raw cell in `note`. |

### manuscript

One row per MANUSCRIPTS data row (one manuscript copy of a text).

| Column | Type | Excel source (MANUSCRIPTS) |
| :--- | :--- | :--- |
| `manuscript_id` | integer PK | — |
| `identifier` | varchar, unique, not null | `'BHL or NO BHL'` + `_` + `'Manuscript copy unique identifier per text'` (e.g. `BHL_29-4`) |
| `text_id` | FK → `text`, not null | `Unique text identifier` (prefix + uid must match a `text.identifier`; no match rejects the row) |
| `manuscript_preservation_status_id` | FK → `manuscript_preservation_status` | `Preservation status of manuscript copy` |
| `manuscript_holding_institution_id` | FK → `manuscript_holding_institution` | `Manuscript holding institution` (`N/A` → NULL) |

No `title` column — the title lives on `text`.

### edition

One row per EDITIONS data row. An edition whose `Unique identifier` matches
no text is rejected.

| Column | Type | Excel source (EDITIONS) |
| :--- | :--- | :--- |
| `edition_id` | integer PK | — |
| `text_id` | FK → `text`, not null | `Unique identifier` (matches the TEXTS identifier suffix) |
| `identifier_per_text` | varchar, not null | text's prefix + `_` + `Edition unique identifier per individual text` (e.g. `BHL_29-A`; not unique in the workbook) |
| `publication_year` | integer | `Publication year` |
| `reference` | varchar | `Edition reference` |
| `page_numbers` | varchar | `Page numbers` |
| `reprint` | boolean | `Reprint ?` (YES/NO) |
| `reprint_identical` | boolean | `If reprint, identically typeset?` (YES/NO, `N/A` → NULL) |
| `reprint_of_edition_id` | FK → `edition` (self) | `If reprint, of what?`, resolved |
| `reprint_of` | varchar | `If reprint, of what?`, raw (`N/A` → NULL) |

### Link tables

| Table | Columns | Excel source (EDITIONS) |
| :--- | :--- | :--- |
| `edition__manuscripts` | `edition__manuscripts_id` PK, `edition_id` FK, `manuscript_id` FK, `likely_use_of_a_copy` (tri-state boolean, NULL = unknown), `notes` (no Excel source) | `Manuscript used 1`–`16` + `Likely use of a copy of Manuscript 1`–`16?` |
| `edition__edition` | `edition__edition_id` PK, `edition_id` FK, `consulted_edition_id` FK, `notes` (no Excel source) | `Edition used or consulted 1`–`5` |

Reference resolution: manuscript refs are tried as a copy identifier
(`29-1`), then as a codex identifier within the edition's text
(`Cologne HA 6`); edition refs (consulted, reprint-of) as a per-text edition
identifier (`618-A`, when globally unique), then as an `(inc. volume)`
identifier within the same text (`Surius 5 (1574)`). `N/A` means no link;
unresolvable or ambiguous refs are reported and skipped.

### Hand-curated tables (not populated by the importer)

| Table | Columns |
| :--- | :--- |
| `repertory` | `repertory_id` PK, `name` (unique, not null), `note` |
| `repertory_link` | `repertory_link_id` PK, `text_id` FK, `repertory_id` FK, `url`, `note` |

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
