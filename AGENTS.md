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
just reinit                   # full reset: rebuild + pg_import + Mathesar bootstrap + summaries (local Docker only)
just container_up / container_down  # start/stop containers without rebuilding
just iiif_check / iiif_fix    # LEGACY — target the parked old schema; do not run against the current DB
```

## Import Policy: Strict Validation, Never Fix Data

The import script never fixes Excel data. Any cell that fails strict
validation (e.g. a number/year is expected but a character is present) causes
that row to be skipped and reported with its Excel row number; valid rows are
still imported and the importer exits non-zero (1). Rejected rows are printed
to the console and written to `data/import_report.csv`. Fix the data in the
workbook, never in the importer.

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
- Identifiers are the given, stable workbook identifiers, concatenated as-is: `text.identifier` = `BHL or NO BHL` prefix (spaces → `_`) + `_` + `Unique identifier` (e.g. `BHL_29`, `NO_BHL_ALPER`); `manuscript.identifier` = prefix + `_` + `Manuscript copy unique identifier per text` (e.g. `BHL_29-4`).
- Two documented exceptions to the no-normalization rule: manuscript preservation-status labels are matched case-insensitively to `Lost`/`Preserved`, and holding-institution names differing only in case/whitespace are merged (most frequent spelling wins); an institution of `N/A` becomes a NULL FK.

Current entities (schema restart, July 2026 — grown incrementally from here): **Text** with lookups **TextForm** (`text_form`, prose/verse), **TextSourceType** (`text_source_type`), **TextSourceSubtype** (`text_source_subtype`); **Manuscript** with lookups **ManuscriptPreservationStatus** (`manuscript_preservation_status`) and **ManuscriptHoldingInstitution** (`manuscript_holding_institution`); **Edition** (basic metadata: title, publication_year, reprint).

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
