# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hagiographies is an Excel-to-PostgreSQL import pipeline with a Mathesar admin UI for browsing hagiographic manuscript data. Developed by Ghent Centre for Digital Humanities.

## Common Commands

All commands use `just` (a command runner). Everything runs in Docker containers.

Recipes are grouped by area prefix (`container_`, `db_`, `iiif_`, `mathesar_`,
`pg_`); run `just --list` to see them all.

```sh
just container_rebuild        # build and start all Docker containers
just pg_validate              # validate the Excel workbook only, no DB writes (report: data/import_report.csv)
just pg_import                # import Excel data into PostgreSQL, creating the schema if needed
just pg_schema_create         # create the metadata schema only (DDL, no data)
just pg_schema_drop           # drop + recreate the research DB's public schema (destructive)
just pg_reimport              # full refresh: pg_schema_drop + pg_import
just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite via Dataflow (see dataflow/config.json)
just pg_export_sqlite_dry_run # validate the Dataflow config, write nothing
just db_diagram               # generate SVG schema diagram from SQLModel
just db_migrate_status        # which schema migrations are applied / pending
just db_migrate               # apply pending migrations from db/migrations/
just db_migrate_prd           # apply pending migrations to PRD
just db_clone_qas             # copy the remote DB into the local Docker Postgres (destructive, local only)
just db_local_migrate         # same, forced at the local Docker Postgres
just reinit                   # full reset: rebuild + pg_import + Mathesar bootstrap + summaries (local Docker only)
just container_up / container_down  # start/stop containers without rebuilding
just iiif_check / iiif_fix    # LEGACY — target the parked old schema; do not run against the current DB
```

## Schema Changes: `db/migrations/` Is the Source of Truth

From July 2026 the schema evolves through numbered SQL migrations in
`db/migrations/`, applied by `just db_migrate`. `000_init.sql` is a frozen
baseline (the schema as it stood on 2026-07-29); on a database that already
carries it the runner records it as applied without executing it, so an empty
database can still be built from the directory alone. A migration is immutable
once applied — the runner stores a checksum and refuses to continue if a file
changed; add a new migration instead.

Mathesar edits the schema too — setting a column's type in its UI is DDL,
usually to a domain in its own `mathesar_types` schema. The runner tracks files,
not schema state, so it cannot detect that; reproduce such a change as a new
migration (see `004_manuscript_link_url_uri.sql`), guarded both against being
already applied and against `mathesar_types` not existing.

Consequences:

- `utils/utilities/src/utilities/model.py` is **no longer kept in sync** with
  the database. It still describes the July 2026 import, but not the columns
  and tables added since. Do not treat it as the schema.
- **Never run `pg_schema_create`, `pg_schema_drop`, `pg_reimport` or `reinit`
  against a migrated database** — they rebuild the schema from the stale
  SQLModel model and would drop the migrated tables.
- `db/` is a standalone package (`psycopg` + `openpyxl`, no SQLModel). Unlike
  every other recipe it runs on the **host** (`uv run --project db`), not in the
  `utils` container: the container's DNS cannot reliably reach the UGent servers
  or PyPI, and bind-mounting `db/` made host and container fight over
  `db/.venv`. `PG_DATABASE_URL` comes from `.env` via direnv. See
  `db/README.md`.

The migration bookkeeping table lives in the **`hagio_admin`** schema, not
`public`, so `public` holds research data only and Mathesar shows researchers
their tables rather than ours. The runner creates the schema and relocates the
table automatically; editors are never granted `USAGE` on it.

The 2026-07 backfill that first populated `manuscript.shelfmark`,
`manuscript.folio_or_page_range`, `codex` and `publication` from the workbook is
**retired**: it ran once, the researchers verified it, and migrations 011/012
dropped the columns it reads and writes. `db/src/hagio_db/{backfill,report,workbook}.py`
are kept as the record of how the data got where it is, with no console script
and no recipe. Do not resurrect them.

## Import Policy: Strict Validation, Never Fix Data

The import script never fixes Excel data. The report distinguishes two
severities: **errors** — validation fails (e.g. a number/year is expected but
a character is present) or a required text link cannot be resolved; the row
is rejected and reported with its Excel row number — and **warnings** — a
linked reference (manuscript used, consulted edition, reprint-of) is not
found; the entity itself is still imported and only the link is skipped.
Valid rows are always imported and the importer exits non-zero (1) whenever
anything is reported. The report is printed to the console and written to
`data/import_report.csv`. Fix the data in the workbook, never in the
importer.

**Database selection:** `pg_import` and the `iiif_*` recipes target whatever
`PG_DATABASE_URL` resolves to in the `utils` container — `dev.env`'s local Docker
Postgres by default, or a remote server if a local `.env` overrides
`PG_DATABASE_URL`. `config.py` reads `DATABASE_URL` or `PG_DATABASE_URL`, so no
explicit `-e` is passed. `pg_reset` and `reinit` recreate the `postgres-data`
volume and are therefore **local Docker only** — skip them for a remote DB.

Gateway (Caddy) runs on port 9160, reverse-proxying the Mathesar admin UI.

## Architecture

### Docker Services (compose.yml)

- **postgres** — PostgreSQL 17, the canonical data store
- **mathesar** — Mathesar admin UI (port 8000), browses/edits the PostgreSQL data
- **utils** — Python utilities container (no long-running process; used for one-off tasks via `docker compose run`)
- **gateway** — Caddy reverse proxy (port 9160 → Mathesar)

### Python Utilities (`utils/`)

Three Python sub-packages, each standalone with its own `pyproject.toml`, run via `docker compose run -w /app/<pkg>`:

- **`utilities/`** — Shared library: SQLModel data model (`model.py`), database engine config (`db.py`), env config (`config.py`)
- **`importer/`** — Typer CLI reading the corpus workbook (`EXCEL_FILE` in `data/`), strictly validating and populating PostgreSQL via SQLModel. Modules: `excel.py` (workbook access), `fields.py` (strict parsers + FieldSpec), `report.py` (rejected-row reporting), `schema.py` (DDL ops), `sheets/` (one module per worksheet)
- **`documenter/`** — Generates SVG entity diagram from SQLModel classes

The canonical data model lives in `utils/utilities/src/utilities/model.py` and targets PostgreSQL. Conventions:

- Primary keys are `<table>_id` (autoincrement), never plain `id`.
- Foreign keys are real database constraints (`Field(foreign_key=...)` emits `FOREIGN KEY ... REFERENCES` DDL), and every FK pair also has SQLModel `Relationship(back_populates=...)` navigation on both sides. `just pg_schema_create` recreates the full schema, FKs included, without any data.
- Every imported field records its source Excel column via `excel_field()`, both as a pydantic description and as a PostgreSQL column comment (visible in `\d+` and Mathesar).
- Identifiers are the given, stable workbook identifiers, concatenated as-is: `text.identifier` = `BHL or NO BHL` prefix (spaces → `_`) + `_` + `Unique identifier` (e.g. `BHL_29`, `NO_BHL_ALPER`); `manuscript.identifier` = prefix + `_` + `Manuscript copy unique identifier per text` (e.g. `BHL_29-4`); `edition.identifier_per_text` = the text's prefix + `_` + `Edition unique identifier per individual text` (e.g. `BHL_29-A`).
- `manuscript` and `edition` carry no `title` — the title lives on `text`, reachable via the `text_id` FK (required on `edition`; nullable on `manuscript`: an unresolvable workbook text reference is a warning, the manuscript is imported with `text_id` NULL and the raw reference in `general_notes`).
- Two documented exceptions to the no-normalization rule: manuscript preservation-status labels are matched case-insensitively to `Lost`/`Preserved`, and holding-institution names differing only in case/whitespace are merged (most frequent spelling wins); an institution of `N/A` becomes a NULL FK.

Current entities (schema restart, July 2026 — grown incrementally from here): **Text** (identification, dating incl. `dating_confidence` FK, réécriture incl. self-FK `reecriture_text_id`, author FK, creation/destinatary geography FKs, reference, general_note) with lookups **TextForm**, **TextSourceType**, **TextSourceSubtype**, **DatingConfidence**; **Author** (deduped by name; anonymous authors are one row per text named `Anonymous <text.identifier>` with the raw cell in `note`) with lookup **AuthorMilieu**; geography **Location** (lat/long, deduped by coordinates), **Archdiocese**, **Diocese**, **Institution** (each `name` + optional `location_id` + `note`); **Manuscript** (FK to text; codex fields incl. tri-states `codex_multiple_copies`/`codex_composite`/`codex_legendiers_usable`; `location_id` FK resolved by place name — new locations get NULL lat/long; height/width as text; dating fields incl. shared `dating_confidence` FK, `dating_range_start`/`_end` set to 0 when non-integer with the raw values kept in `dating_note`, and `dating_reference` storing the cell's hyperlink URL when present) with lookups **ManuscriptPreservationStatus** and **ManuscriptHoldingInstitution**; **ManuscriptLink** (`manuscript_link`: typed URLs from the Légendiers/catalogue/images link columns — always the cell hyperlink target, never the display text 'Link'; images typed by 'Type of online images', unrecognized types warn and skip) with lookup **ManuscriptLinkType** (9 seeded labels); origin/provenance FKs (`origin_archdiocese_id`/`origin_diocese_id`/`origin_institution_id` into the shared geography lookups, confidence ratings via **OriginConfidence** and **ProvenanceConfidence**; the workbook's provenance early-owner headers appear twice — the importer reads the SECOND occurrences, the first hold stray GPS; `provenance_later_confidence_id` has no source column yet and stays NULL; the MANUSCRIPTS GPS pairs — diocese, early owner, later owner — are read with swapped headers like TEXTS but as plain degrees, W-Europe validated with warnings, and become coordinate-deduplicated **Location** rows linked via `location_id` on Archdiocese/Diocese/Institution — GPS-less names get a name-keyed NULL-coordinate location; an entity's existing `location_id` is never overwritten), **VernacularRegion** FK (G/R/F; Unknown/N/A → NULL), **ManuscriptType** FK (whitespace-normalized label, raw cell kept in `manuscript_type_note`), and **ManuscriptRelation** (`manuscript_relation`) manuscript↔manuscript links typed via **ManuscriptRelationshipType** ('Based on exemplar', 'Exemplar of', comma-split; refs resolve like EDITIONS manuscript refs); **Edition** (FK to text, prefixed per-text identifier, publication metadata, reprint flags + self-FK `reprint_of_edition_id`, tri-state `collation_done` — a non-tristate 'Collation done?' value warns and stays NULL — and `general_notes` from 'Notes') with **EditionLink** (`edition_link`: the 'Edition images link' cell's hyperlink URL, typed by the strict 'Images of edition?' value SCAN/Transcription/NO/N/A; a missing or non-http(s) hyperlink only warns) and lookup **EditionLinkType** (2 seeded labels); link tables **EditionManuscript** (`edition__manuscripts`, tri-state `likely_use_of_a_copy`) and **EditionEdition** (`edition__edition`); **Repertory** and **RepertoryLink** — hand-curated, not populated by the importer.

Added after the restart by `db/migrations/` and therefore **absent from
`model.py`**: `manuscript.shelfmark` and `manuscript.folio_or_page_range`
(migration 001); table `codex` (`codex_id`, `name`) with `manuscript.codex_id`
(002); table `publication` (`publication_id`, `name`) with
`edition.publication_id` (003). `codex.name` deduplicates the **database** column
`manuscript.codex_identifier` (whitespace-collapsed, `N/A` → no codex) — pure
SQL, the workbook plays no part, so codices the researchers renamed in Mathesar
keep their name and the rows absent from the workbook are linked too.
`publication.name` deduplicates EDITIONS 'Edition unique identifier (inc.
volume)', which has no database column and can therefore only come from the
workbook. Both tables started as id+name only, because the codex- and
publication-level columns contradicted themselves for 7–16% of the multi-row
groups; once the researchers had resolved those conflicts, migrations 009 and
010 hoisted them:

- **009** moves 30 codex-level columns from `manuscript` onto `codex`
  (shelfmark, holding institution, location, height/width, all `dating_*`,
  preservation status, manuscript type, all `origin_*`/`provenance_*`,
  vernacular region, the `codex_*` flags and notes, `general_notes`).
- **010** moves `publication_year` and `reference` from `edition` onto
  `publication`. Nothing else on `edition` qualifies — `page_numbers`,
  `reprint*`, `collation_done` and `general_notes` are per edition, and the
  data says so loudly (144 publications disagree on `page_numbers` alone).
- Both are **additive**: the columns still exist on `manuscript`/`edition`.
  `db/migrations/pending/011_drop_hoisted_columns.sql` removes them and is
  parked outside the runner's glob until the researchers sign off; move it into
  `db/migrations/` to activate. It is the only destructive migration.
- Both **abort rather than guess** if any group still disagrees, naming the
  offending columns.
- `codex_number`, `codex_copy_amount` and `codex_multiple_copies` are not
  hoisted at all — `codex_id` replaces the first and the other two are
  `count(*)` and `count(*) > 1` over the codex's manuscripts. 011 drops them.
- `manuscript.codex_identifier` stays: it duplicates `codex.name` but is what
  `codex.name` was derived from, so it is the only way to rebuild the link.
  `manuscript.folio_or_page_range` stays for good — it is per text copy.

TEXTS-sheet geography quirks: the GPS column headers are **swapped** in the workbook — the '… GPS Longitude' column holds latitude ×10⁶ and '… GPS Latitude' holds longitude ×10⁶; the importer reads them swapped/unscaled and requires Western-Europe coordinates (lat 44–56, lon −2–10), warning otherwise. `'Unknown'` and `'N/A'` in institution/destinatary/milieu columns mean NULL. The 'Precise institutional origin?'/'Precise destinatary?' flags are not stored (institution presence implies precision).

EDITIONS-sheet reference resolution (all cross-links resolve within the parsed workbook, purely, before any DB write): the edition→text link matches `Unique identifier` against the TEXTS identifier suffix; manuscript refs are tried as a copy identifier (`29-1`) then as a codex identifier within the edition's text (`Cologne HA 6`); edition refs (consulted, reprint-of) are tried as a per-text edition identifier (`618-A`, when globally unique) then as an `(inc. volume)` identifier within the same text (`Surius 5 (1574)`). A ref of `N/A` means no link; every other unresolvable or ambiguous ref is reported (the edition row itself is kept, except an unresolvable *text* link which rejects the row).

The pre-restart 20-table model and its importer are **parked, reference only**: `utils/utilities/src/utilities/legacy_model.py` and `utils/importer/src/importer/legacy/`. Do not build new code against them.

### Mathesar Admin

Mathesar (`mathesar/mathesar:0.11.0`) browses and edits the PostgreSQL data directly.
It keeps its own Django metadata DB (`mathesar_django`), separate from the research
database. Record summaries (the display label per table) are configured via the
JSON-RPC API by `utils/mathesar/` (`just mathesar_summaries`).

### Data Flow

```
corpus workbook (data/*.xlsx) → [importer] → PostgreSQL
                                                  │
                                                  ├────── Mathesar Admin (edits PostgreSQL directly)
                                                  │
                                                  └────── [Dataflow] → data/hagiographies_full_export.sqlite
```

## Key Details

- PostgreSQL is the canonical store (service `postgres`); the importer and model target it
- Mathesar (port 8000) is the admin UI, editing PostgreSQL directly; fronted by the gateway at port 9160
- All `data/` contents are gitignored (db, sqlite, csv, xlsx)
- Python version: 3.13, managed with UV
- Environment config: `dev.env` (shared by all services), `.env` (local Python path override)
