# Database Architecture and Project Structure

This document provides a technical overview of the Hagiographies project repository structure and its database model.

> **Status (October 2026).** The PostgreSQL database is the single source of truth
> and is curated in Mathesar. Its schema is defined by `db/migrations/`; the
> tables below describe `public` after migrations 000–059, matching
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

Generated from the schema (October 2026, after migrations 000–059). "Source" is
the column comment: the Excel column the initial data came from, or a description.
Naming and uniqueness rules: see AGENTS.md ("Naming rules", "Uniqueness").
"case-insensitive" = also unique on lower(value), with no leading/trailing spaces allowed.
The url columns are the `mathesar_types.uri` domain on QAS/PRD (migrations 004–006).

### Texts and authors

#### `text`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `text_id` | integer, not null | PK |  |
| `text_unique_identifier` | character varying, not null | unique, case-insensitive | Excel TEXTS → ''BHL or NO BHL' + '_' + 'Unique identifier'' |
| `text_title` | character varying |  | Excel TEXTS → 'Title of the work' |
| `text_approximate_token_count` | integer |  | Excel TEXTS → 'Approximate token count' |
| `text_form_id` | integer | FK → text_form | Excel TEXTS → 'Prose or verse' |
| `text_source_type_id` | integer | FK → text_source_type | Excel TEXTS → 'Source type' |
| `text_source_subtype_id` | integer | FK → text_source_subtype | Excel TEXTS → 'Subtype' |
| `text_reecriture` | boolean |  | Excel TEXTS → 'Réécriture?' |
| `reecriture_of_text_id` | integer | FK → text | Excel TEXTS → 'Réécriture of which text(s)? (resolved)' |
| `text_reecriture_note` | character varying |  | Excel TEXTS → 'Réécriture of which text(s)?' |
| `text_dating_range_start` | integer |  | Excel TEXTS → 'Dating range (beginning)' |
| `text_dating_range_end` | integer |  | Excel TEXTS → 'Dating range (end)' |
| `text_dating_quarter_century` | character varying |  | Excel TEXTS → 'Quarter century chronology' |
| `dating_confidence_id` | integer | FK → dating_confidence | Excel TEXTS → 'Dating confidence rating' |
| `text_dating_note` | character varying |  | Excel TEXTS → 'Dating notes' |
| `author_id` | integer | FK → author | Excel TEXTS → 'Author of the text' |
| `text_author_in_destinatary_institution` | boolean |  | Excel TEXTS → 'Is author based in destinatary institution?' |
| `creation_archdiocese_id` | integer | FK → archdiocese | Excel TEXTS → 'Text creation - location by archdiocese' |
| `creation_diocese_id` | integer | FK → diocese | Excel TEXTS → 'Text creation - location by diocese' |
| `creation_institution_id` | integer | FK → institution | Excel TEXTS → 'Text creation - location by institution' |
| `text_creation_note` | character varying |  |  |
| `destinatary_archdiocese_id` | integer | FK → archdiocese |  |
| `destinatary_diocese_id` | integer | FK → diocese |  |
| `destinatary_institution_id` | integer | FK → institution | Excel TEXTS → 'Primary institutional destinatary' |
| `text_destinatary_note` | character varying |  |  |
| `text_reference` | character varying |  | Excel TEXTS → 'Selected reference' |
| `text_general_note` | character varying |  | Excel TEXTS → 'Notes' |

#### `text_form`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `text_form_id` | integer, not null | PK |  |
| `text_form` | character varying, not null | unique | Excel TEXTS → 'Prose or verse' |

#### `text_source_type`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `text_source_type_id` | integer, not null | PK |  |
| `text_source_type` | character varying, not null | unique | Excel TEXTS → 'Source type' |

#### `text_source_subtype`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `text_source_subtype_id` | integer, not null | PK |  |
| `text_source_subtype` | character varying, not null | unique | Excel TEXTS → 'Subtype' |

#### `dating_confidence`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `dating_confidence_id` | integer, not null | PK |  |
| `dating_confidence` | character varying, not null | unique | Excel TEXTS → 'Dating confidence rating' |
| `dating_confidence_note` | character varying |  |  |

#### `author`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `author_id` | integer, not null | PK |  |
| `author_name` | character varying, not null | unique | Excel TEXTS → 'Author of the text' |
| `author_institutional_training_ground` | character varying |  | Excel TEXTS → 'Institutional training ground of the author' |
| `author_regional_antecedents` | character varying |  | Excel TEXTS → 'Regional or local antecedents of the author' |
| `author_milieu_id` | integer | FK → author_milieu | Excel TEXTS → 'Author milieu' |
| `author_note` | character varying |  |  |

#### `author_milieu`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `author_milieu_id` | integer, not null | PK |  |
| `author_milieu` | character varying, not null | unique | Excel TEXTS → 'Author milieu' |
| `author_milieu_note` | character varying |  |  |

### Geography

#### `location`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `location_id` | integer, not null | PK |  |
| `location_name` | character varying |  |  |
| `location_latitude` | double precision |  | Excel TEXTS → '… GPS Longitude (sic, swapped) / 1e6' |
| `location_longitude` | double precision |  | Excel TEXTS → '… GPS Latitude (sic, swapped) / 1e6' |

#### `archdiocese`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `archdiocese_id` | integer, not null | PK |  |
| `archdiocese_name` | character varying, not null | unique | Excel TEXTS → 'Text creation - location by archdiocese' |
| `location_id` | integer | FK → location |  |
| `archdiocese_note` | character varying |  |  |

#### `diocese`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `diocese_id` | integer, not null | PK |  |
| `diocese_name` | character varying, not null | unique | Excel TEXTS → 'Text creation - location by diocese' |
| `location_id` | integer | FK → location |  |
| `diocese_note` | character varying |  |  |

#### `institution`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `institution_id` | integer, not null | PK |  |
| `institution_name` | character varying, not null | unique | Excel TEXTS → ''Text creation - location by institution' / 'Primary institutional destinatary'' |
| `location_id` | integer | FK → location |  |
| `institution_note` | character varying |  |  |

### Codices and manuscripts

#### `codex`

One physical codex. Excel MANUSCRIPTS → 'Codex unique identifier', deduplicated.

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `codex_id` | integer, not null | PK |  |
| `codex_unique_identifier` | character varying, not null | unique, case-insensitive | Excel MANUSCRIPTS → 'Codex unique identifier' |
| `codex_preservation_status_id` | integer | FK → codex_preservation_status | Excel MANUSCRIPTS → 'Preservation status of manuscript copy' |
| `location_id` | integer | FK → location | Excel MANUSCRIPTS → 'Manuscript location' |
| `codex_holding_institution_id` | integer | FK → codex_holding_institution | Excel MANUSCRIPTS → 'Manuscript holding institution' |
| `codex_height` | character varying |  | Excel MANUSCRIPTS → 'Manuscript height' |
| `codex_width` | character varying |  | Excel MANUSCRIPTS → 'Manuscript width' |
| `codex_dating_by_century` | integer |  | Excel MANUSCRIPTS → 'Manuscript dating by (earliest) century' |
| `codex_dating_range_start` | integer |  | Excel MANUSCRIPTS → 'Manuscript dating range start (0 when not an integer in the workbook)' |
| `codex_dating_range_end` | integer |  | Excel MANUSCRIPTS → 'Manuscript dating range end (0 when not an integer in the workbook)' |
| `codex_dating_reference` | character varying |  | Excel MANUSCRIPTS → 'Preferred secondary reference for manuscript dating (hyperlink URL when the cell is hyperlinked)' |
| `dating_confidence_id` | integer | FK → dating_confidence | Excel MANUSCRIPTS → 'Confidence rating for manuscript dating' |
| `codex_dating_note` | character varying |  | Excel MANUSCRIPTS → 'raw 'Manuscript dating range start/end' when not integers' |
| `codex_legendiers_usable` | boolean |  | Excel MANUSCRIPTS → 'Usable Légendiers entry for codex contents' |
| `codex_composite` | boolean |  | Excel MANUSCRIPTS → 'Composite?' |
| `codex_legendiers_entry_code` | character varying |  | Excel MANUSCRIPTS → 'Légendiers entry code' |
| `codex_contents_note` | character varying |  | Excel MANUSCRIPTS → 'Notes on codex contents' |
| `vernacular_region_id` | integer | FK → vernacular_region | Excel MANUSCRIPTS → 'Vernacular region (Romance/Germanic)' |
| `origin_archdiocese_id` | integer | FK → archdiocese | Excel MANUSCRIPTS → 'Manuscript origin by archdiocese' |
| `origin_diocese_id` | integer | FK → diocese | Excel MANUSCRIPTS → 'Manuscript origin by diocese' |
| `origin_diocese_confidence_id` | integer | FK → origin_confidence | Excel MANUSCRIPTS → 'Manuscript origin by diocese confidence rating' |
| `origin_institution_id` | integer | FK → institution | Excel MANUSCRIPTS → 'Manuscript origin by institution' |
| `origin_institution_confidence_id` | integer | FK → origin_confidence | Excel MANUSCRIPTS → 'Manuscript origin confidence rating' |
| `provenance_early_institution_id` | integer | FK → institution | Excel MANUSCRIPTS → 'Manuscript provenance by early/earliest institutional owner (second occurrence of this duplicated header)' |
| `provenance_early_confidence_id` | integer | FK → provenance_confidence | Excel MANUSCRIPTS → 'Manuscript provenance by early/earliest institutional owner confidence rating (second occurrence of this duplicated header)' |
| `provenance_later_institution_id` | integer | FK → institution | Excel MANUSCRIPTS → 'Manuscript provenance by undetermined or later institutional owner' |
| `provenance_later_confidence_id` | integer | FK → provenance_confidence | Excel MANUSCRIPTS → 'no source column yet (the workbook has no confidence rating for the undetermined/later owner) — always NULL for now' |
| `codex_origin_or_provenance_secondary_reference` | character varying |  | Excel MANUSCRIPTS → 'Manuscript origin and provenance preferred secondary reference (hyperlink URL when the cell is hyperlinked)' |
| `codex_type_id` | integer | FK → codex_type | Excel MANUSCRIPTS → 'Manuscript type (whitespace-normalized label)' |
| `codex_type_selection_note` | character varying |  | Excel MANUSCRIPTS → 'Manuscript type (raw cell, incl. notes on type selection)' |
| `codex_general_note` | character varying |  | Excel MANUSCRIPTS → ''Notes', prefixed with the raw 'Unique text identifier' when it resolves to no text' |
| `codex_shelfmark` | character varying |  | Excel MANUSCRIPTS → 'Manuscript shelfmark' |

#### `codex_holding_institution`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `codex_holding_institution_id` | integer, not null | PK |  |
| `codex_holding_institution_name` | character varying, not null | unique | Excel MANUSCRIPTS → 'Manuscript holding institution' |

#### `codex_preservation_status`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `codex_preservation_status_id` | integer, not null | PK |  |
| `codex_preservation_status` | character varying, not null | unique | Excel MANUSCRIPTS → 'Preservation status of manuscript copy' |

#### `codex_type`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `codex_type_id` | integer, not null | PK |  |
| `codex_type` | character varying, not null | unique | Excel MANUSCRIPTS → 'Manuscript type (whitespace-normalized)' |
| `codex_type_note` | character varying |  |  |

#### `origin_confidence`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `origin_confidence_id` | integer, not null | PK |  |
| `origin_confidence` | character varying, not null | unique | Excel MANUSCRIPTS → ''Manuscript origin by diocese confidence rating' / 'Manuscript origin confidence rating'' |
| `origin_confidence_note` | character varying |  |  |

#### `provenance_confidence`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `provenance_confidence_id` | integer, not null | PK |  |
| `provenance_confidence` | character varying, not null | unique | Excel MANUSCRIPTS → 'Manuscript provenance by early/earliest institutional owner confidence rating' |
| `provenance_confidence_note` | character varying |  |  |

#### `vernacular_region`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `vernacular_region_id` | integer, not null | PK |  |
| `vernacular_region` | character varying, not null | unique | Excel MANUSCRIPTS → 'Vernacular region (Romance/Germanic)' |
| `vernacular_region_note` | character varying |  |  |

#### `manuscript`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `manuscript_id` | integer, not null | PK |  |
| `manuscript_unique_identifier` | character varying, not null | unique, case-insensitive | Excel MANUSCRIPTS → ''BHL or NO BHL' + '_' + 'Manuscript copy unique identifier per text' (workbook duplicates are imported as-is and warned)' |
| `text_id` | integer | FK → text | Excel MANUSCRIPTS → 'Unique text identifier (NULL when the reference is unresolvable; see general_notes)' |
| `manuscript_folio_or_page_range` | character varying |  | Excel MANUSCRIPTS → 'Folio or page range' |
| `codex_id` | integer | FK → codex | The codex this copy is bound in; resolved from 'Codex unique identifier' |

#### `manuscript_link`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `manuscript_link_id` | integer, not null | PK |  |
| `manuscript_id` | integer, not null | FK → manuscript | Excel MANUSCRIPTS → 'link columns (row)' |
| `manuscript_link_type_id` | integer, not null | FK → manuscript_link_type | Excel MANUSCRIPTS → 'link column → type' |
| `manuscript_link_url` | character varying, not null |  | Excel MANUSCRIPTS → 'link cell hyperlink target' |
| `manuscript_link_note` | character varying |  |  |

#### `manuscript_link_type`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `manuscript_link_type_id` | integer, not null | PK |  |
| `manuscript_link_type` | character varying, not null | unique |  |
| `manuscript_link_type_note` | character varying |  |  |

#### `manuscript__manuscript`

A manuscript may not be related to itself (CHECK manuscript_id <> related_manuscript_id).

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `manuscript__manuscript_id` | integer, not null | PK |  |
| `manuscript_id` | integer, not null | FK → manuscript (part of a unique key) | Excel MANUSCRIPTS → ''Based on exemplar' / 'Exemplar of which manuscript(s)' (row)' |
| `related_manuscript_id` | integer, not null | FK → manuscript (part of a unique key) | Excel MANUSCRIPTS → ''Based on exemplar' / 'Exemplar of which manuscript(s)' (resolved)' |
| `manuscript__manuscript_type_id` | integer, not null | FK → manuscript__manuscript_type (part of a unique key) | Excel MANUSCRIPTS → 'source column → type' |
| `manuscript__manuscript_note` | character varying |  |  |

#### `manuscript__manuscript_type`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `manuscript__manuscript_type_id` | integer, not null | PK |  |
| `manuscript__manuscript_type` | character varying, not null | unique |  |
| `manuscript__manuscript_type_note` | character varying |  |  |

### Publications and editions

#### `publication`

One published volume. Excel EDITIONS → 'Edition unique identifier (inc. volume)', deduplicated.

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `publication_id` | integer, not null | PK |  |
| `publication_unique_identifier` | character varying, not null | unique, case-insensitive | Excel EDITIONS → 'Edition unique identifier (inc. volume)' |
| `publication_year` | integer |  | Excel EDITIONS → 'Publication year' |
| `publication_full_reference` | character varying |  | Excel EDITIONS → 'Edition reference' |

#### `edition`

`edition_unique_identifier` is not yet unique: see `db/migrations/pending/`.

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `edition_id` | integer, not null | PK |  |
| `text_id` | integer | FK → text | Excel EDITIONS → 'Unique identifier (NULL when the reference is unresolvable; see general_notes)' |
| `edition_unique_identifier` | character varying, not null |  | Excel EDITIONS → ''BHL or NO BHL' prefix + '_' + 'Edition unique identifier per individual text'' |
| `edition_page_numbers` | character varying |  | Excel EDITIONS → 'Page numbers' |
| `edition_reprint` | boolean |  | Excel EDITIONS → 'Reprint ?' |
| `edition_reprint_identical` | boolean |  | Excel EDITIONS → 'If reprint, identically typeset?' |
| `reprint_of_edition_id` | integer | FK → edition | Excel EDITIONS → 'If reprint, of what? (resolved)' |
| `edition_reprint_of_note` | character varying |  | Excel EDITIONS → 'If reprint, of what?' |
| `edition_collation_done` | boolean |  | Excel EDITIONS → 'Collation done?' |
| `edition_general_note` | character varying |  | Excel EDITIONS → 'Notes' |
| `publication_id` | integer | FK → publication | The volume this edition is printed in; resolved from 'Edition unique identifier (inc. volume)' |

#### `edition_link`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `edition_link_id` | integer, not null | PK |  |
| `edition_id` | integer, not null | FK → edition | Excel EDITIONS → 'Edition images link (row)' |
| `edition_link_type_id` | integer, not null | FK → edition_link_type | Excel EDITIONS → 'Images of edition? → type' |
| `edition_link_url` | character varying, not null |  | Excel EDITIONS → ''Edition images link' hyperlink target' |
| `edition_link_note` | character varying |  |  |

#### `edition_link_type`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `edition_link_type_id` | integer, not null | PK |  |
| `edition_link_type` | character varying, not null | unique |  |
| `edition_link_type_note` | character varying |  |  |

#### `edition__manuscript`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `edition__manuscript_id` | integer, not null | PK |  |
| `edition_id` | integer, not null | FK → edition (part of a unique key) | Excel EDITIONS → 'Manuscript used 1–16 (row)' |
| `manuscript_id` | integer, not null | FK → manuscript (part of a unique key) | Excel EDITIONS → 'Manuscript used 1–16 (resolved)' |
| `edition__manuscript_likely_use_of_a_copy` | boolean |  | Excel EDITIONS → 'Likely use of a copy of Manuscript 1–16?' |
| `edition__manuscript_note` | character varying |  |  |

#### `edition__edition`

No self-reference rule yet: see `db/migrations/pending/`.

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `edition__edition_id` | integer, not null | PK |  |
| `edition_id` | integer, not null | FK → edition (part of a unique key) | Excel EDITIONS → 'Edition used or consulted 1–5 (row)' |
| `consulted_edition_id` | integer, not null | FK → edition (part of a unique key) | Excel EDITIONS → 'Edition used or consulted 1–5 (resolved)' |
| `edition__edition_note` | character varying |  |  |

### Repertories (hand-curated)

#### `repertory`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `repertory_id` | integer, not null | PK |  |
| `repertory_name` | character varying, not null | unique |  |
| `repertory_note` | character varying |  |  |

#### `text__repertory`

| Column | Type | Key | Source |
| :--- | :--- | :--- | :--- |
| `text__repertory_id` | integer, not null | PK |  |
| `text_id` | integer, not null | FK → text (part of a unique key) |  |
| `repertory_id` | integer, not null | FK → repertory (part of a unique key) |  |
| `text__repertory_url` | text | (part of a unique key) |  |
| `text__repertory_note` | character varying |  |  |


## 4 Initial import (removed)

The one-off Excel import (July 2026, `utils/importer/`) was removed in October
2026 and remains in git history.

## 5 Diagram

`just db_diagram` regenerates `data/hagiographies_model.svg` from every table
model in `utilities.model`. Re-run it whenever a migration changes `public`
(and `model.py` with it).
