# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its database model.

> **Status (October 2026).** The PostgreSQL database is the single source of truth
> and is curated in Mathesar. Its schema is defined by `db/migrations/`; the
> tables below describe `public` after migrations 000–017, matching
> `utils/utilities/src/utilities/model.py` and `data/hagiographies_model.svg`.
> The `hagio_admin` schema (migration bookkeeping, file-explorer tables from
> 013–017) is not covered here. The one-off Excel import has been removed from
> the repo; the "Excel source" columns record only where the initial data
> came from.

## 1 Project Structure

The project is organized into modular directories.

```text
.
├── caddy/                  # Reverse proxy configuration (Caddyfile)
├── data/                   # Mostly gitignored: databases and Excel sources
├── dataflow/               # Dataflow config for the SQLite export
├── db/                     # Schema migrations (source of truth) + runner
├── file-explorer/          # File explorer over the image share (Rust + Svelte)
├── scripts/                # QAS/PRD backup and clone scripts
├── utils/                  # Python backend utilities (UV-managed)
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
- Provenance note: the initial load normalized only two things.
  Preservation-status labels were matched case-insensitively to
  `Lost`/`Preserved`, and holding-institution names differing only in
  case/whitespace were merged (most frequent spelling wins).

Operational details (lifecycle commands, backups, connectivity) are documented in `POSTGRESQL.md`.

## 3 Tables

The "Excel source" columns name the `TEXTS`, `MANUSCRIPTS` and `EDITIONS`
worksheet columns of the June 2026 corpus workbook the initial data came from.

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
| `archdiocese`, `diocese` | `<t>_id` PK, `name` unique, `location_id` FK, `note` | No coordinates in TEXTS; `location_id` filled from the MANUSCRIPTS diocese GPS pair (plain degrees, also swapped), or a name-keyed NULL-coordinate location. |
| `institution` | `institution_id` PK, `name` unique, `location_id` FK, `note` | Location from the institution's GPS pair (first occurrence wins). |
| `dating_confidence` | `dating_confidence_id` PK, `label` unique, `notes` | A/B/C/D. |
| `author_milieu` | `author_milieu_id` PK, `label` unique, `note` | Monastic, Clerical ('Unknown' → NULL). |
| `author` | `author_id` PK, `name` unique, `institutional_training_ground`, `regional_antecedents`, `author_milieu_id` FK, `note` | Deduped by name. Anonymous (`Anon…`) = one row per text, `name` = `Anonymous <text.identifier>`, raw cell in `note`. |

### codex

One physical codex (migration 002; the codex-level columns were hoisted from
`manuscript` in 009). `name` deduplicates MANUSCRIPTS `Codex unique identifier`
(whitespace-collapsed, `N/A` → no codex). Each column is commented with its
original Excel source in the DB.

| Column | Type | Excel source (MANUSCRIPTS) |
| :--- | :--- | :--- |
| `codex_id` | integer PK | — |
| `name` | varchar, unique, not null | `Codex unique identifier` |
| `shelfmark` | varchar | `Manuscript shelfmark` |
| `manuscript_holding_institution_id` | FK → `manuscript_holding_institution` | `Manuscript holding institution` (`N/A` → NULL) |
| `location_id` | FK → `location` | `Manuscript location` |
| `manuscript_preservation_status_id` | FK → `manuscript_preservation_status` | `Preservation status of manuscript copy` |
| `manuscript_type_id` / `manuscript_type_note` | FK → `manuscript_type` / varchar | `Manuscript type` (normalized / raw) |
| `height`, `width` | varchar | `Manuscript height` / `width` |
| `dating_century`, `dating_range_start`, `dating_range_end` | integer | manuscript dating (range 0 when non-integer; raw in `dating_note`) |
| `dating_confidence_id`, `dating_reference`, `dating_note` | FK → `dating_confidence`, varchar, varchar | dating confidence, reference (hyperlink URL), raw values |
| `origin_archdiocese_id`, `origin_diocese_id`, `origin_institution_id` | FKs → geography | `Manuscript origin by …` |
| `origin_diocese_confidence_rating_id`, `origin_institution_confidence_rating_id` | FK → `origin_confidence` | origin confidence ratings |
| `provenance_early_institute_id`, `provenance_later_institute_id` | FK → `institution` | provenance owners |
| `provenance_early_confidence_id`, `provenance_later_confidence_id` | FK → `provenance_confidence` | provenance confidence (later: no source column) |
| `origin_or_provenance_secondary_reference` | varchar | secondary reference (hyperlink URL) |
| `vernacular_region_id` | FK → `vernacular_region` | `Vernacular region (Romance/Germanic)` |
| `codex_legendiers_usable`, `codex_composite` | boolean (tri-state) | `Usable Légendiers entry…`, `Composite?` |
| `codex_legendiers_entry_code`, `codex_notes`, `general_notes` | varchar | `Légendiers entry code`, `Notes on codex contents`, `Notes` |

The number of corpus copies in a codex and whether it holds several are not
stored: they are `count(*)` over its manuscripts.

### manuscript

One manuscript copy of a text, bound in a codex. Since migrations 009–012 it
holds only the copy-level columns.

| Column | Type | Excel source (MANUSCRIPTS) |
| :--- | :--- | :--- |
| `manuscript_id` | integer PK | — |
| `identifier` | varchar, **not unique**, not null | `'BHL or NO BHL'` + `_` + `'Manuscript copy unique identifier per text'` (e.g. `BHL_29-4`; workbook duplicates kept) |
| `text_id` | FK → `text`, nullable | `Unique text identifier` (no match → NULL; raw reference in the codex's `general_notes`) |
| `codex_id` | FK → `codex`, nullable | resolved from `Codex unique identifier` |
| `folio_or_page_range` | varchar | `Folio or page range` |

No `title` column — the title lives on `text`.

### publication

One published volume (migration 003; columns hoisted from `edition` in 010).

| Column | Type | Excel source (EDITIONS) |
| :--- | :--- | :--- |
| `publication_id` | integer PK | — |
| `name` | varchar, unique, not null | `Edition unique identifier (inc. volume)`, deduplicated |
| `publication_year` | integer | `Publication year` |
| `reference` | varchar | `Edition reference` |

### edition

One row per EDITIONS data row. An edition whose `Unique identifier` matches
no text was kept with `text_id` NULL, an unprefixed identifier and the raw
reference in `general_notes`.

| Column | Type | Excel source (EDITIONS) |
| :--- | :--- | :--- |
| `edition_id` | integer PK | — |
| `text_id` | FK → `text`, nullable | `Unique identifier` (matches the TEXTS identifier suffix) |
| `identifier_per_text` | varchar, not null | text's prefix + `_` + `Edition unique identifier per individual text` (e.g. `BHL_29-A`; not unique in the workbook) |
| `publication_id` | FK → `publication`, nullable | resolved from `Edition unique identifier (inc. volume)` |
| `page_numbers` | varchar | `Page numbers` |
| `reprint` | boolean | `Reprint ?` (YES/NO) |
| `reprint_identical` | boolean | `If reprint, identically typeset?` (YES/NO, `N/A` → NULL) |
| `reprint_of_edition_id` | FK → `edition` (self) | `If reprint, of what?`, resolved |
| `reprint_of` | varchar | `If reprint, of what?`, raw (`N/A` → NULL) |
| `collation_done` | boolean (tri-state) | `Collation done?` |
| `general_notes` | varchar | `Notes` |

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

| Table | Columns | Excel source |
| :--- | :--- | :--- |
| `edition_link` | `edition_link_id` PK, `edition_id` FK, `edition_link_type_id` FK, `url`, `note` | EDITIONS `Edition images link` (hyperlink target), typed by `Images of edition?` |
| `manuscript_link` | `manuscript_link_id` PK, `manuscript_id` FK, `manuscript_link_type_id` FK, `url`, `note` | MANUSCRIPTS Légendiers/catalogue/images link columns (hyperlink target, never the display text) |
| `manuscript_relation` | `manuscript_relation_id` PK, `manuscript_id` FK, `related_manuscript_id` FK, `manuscript_relationship_type_id` FK, `note` | MANUSCRIPTS `Based on exemplar` / `Exemplar of` (comma-split, resolved like edition manuscript refs) |

### Hand-curated tables

| Table | Columns |
| :--- | :--- |
| `repertory` | `repertory_id` PK, `name` (unique, not null), `note` |
| `repertory_link` | `repertory_link_id` PK, `text_id` FK, `repertory_id` FK, `url` (text), `note` |

The `url` columns of `manuscript_link`, `edition_link` and `repertory_link` are the
`mathesar_types.uri` domain on QAS/PRD (migrations 004–006, which apply only
where Mathesar is installed).

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
| `manuscript_type` | MANUSCRIPTS manuscript type (whitespace-normalized) | ~205 labels |
| `vernacular_region` | MANUSCRIPTS vernacular region | G, R, F (`Unknown`/`N/A` → NULL) |
| `origin_confidence` / `provenance_confidence` | MANUSCRIPTS origin/provenance confidence ratings | 3 labels each |
| `manuscript_link_type` | seeded | 9 labels |
| `manuscript_relationship_type` | seeded | Based on exemplar, Exemplar of |
| `edition_link_type` | seeded | SCAN, Transcription |

## 4 Initial import (removed)

The one-off Excel import (July 2026, `utils/importer/`) was removed in October
2026 and remains in git history.

## 5 Diagram

`just db_diagram` regenerates `data/hagiographies_model.svg` from every table
model in `utilities.model`. Re-run it whenever a migration changes `public`
(and `model.py` with it).
