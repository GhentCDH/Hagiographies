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
just pg_import                # import Excel data into PostgreSQL (runs in utils container)
just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite via Dataflow (see dataflow/config.json)
just pg_export_sqlite_dry_run # validate the Dataflow config, write nothing
just iiif_check               # verify IIIF image links point to real manifests (report CSV)
just iiif_fix                 # also discover manifests on viewer pages → image.iiif_manifest_url
just db_diagram               # generate SVG schema diagram from SQLModel
just reinit                   # full reset: rebuild + pg_import + Mathesar bootstrap + summaries (local Docker only)
just container_up / container_down  # start/stop containers without rebuilding
```

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
- **`importer/`** — Reads `hagiographies.xlsx`, normalizes data, populates PostgreSQL via SQLModel
- **`documenter/`** — Generates SVG entity diagram from SQLModel classes

The canonical data model lives in `utils/utilities/src/utilities/model.py` and targets PostgreSQL. The `Table` base class provides an auto-incrementing ID. Core entities: **Text**, **Codex** (physical book), **Manuscript** (one copy of a text in a codex), **Edition** (+ **EditionVolume** for the containing book), with normalized lookups (Place, Institution, Author, Typology) and join tables (EditionManuscript, EditionConsultedVolume, ManuscriptRelation).

### Mathesar Admin

Mathesar (`mathesar/mathesar:0.11.0`) browses and edits the PostgreSQL data directly.
It keeps its own Django metadata DB (`mathesar_django`), separate from the research
database. Record summaries (the display label per table) are configured via the
JSON-RPC API by `utils/mathesar/` (`just mathesar_summaries`).

### Data Flow

```
hagiographies.xlsx → [importer] → PostgreSQL
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
