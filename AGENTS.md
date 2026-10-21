# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hagiographies is a PostgreSQL database of hagiographic texts, manuscripts and editions. It is curated through a Mathesar admin UI and exported to SQLite. Developed by Ghent Centre for Digital Humanities.

**The PostgreSQL database is the single source of truth.** Researchers edit and extend it directly in Mathesar. The production database is `gcdhpsqlprd1.ugent.be` (VPN required). The original Excel workbook import was a one-off initial load (July 2026). The importer has since been removed from the repo (see git history before October 2026).

## Common Commands

All commands use `just` (a command runner). Everything runs in Docker containers. Run `just --list` to see all recipes; they are grouped by prefix (`container_`, `db_`, `mathesar_`, `pg_`, `util_`).

```sh
just container_rebuild        # build and start all Docker containers
just container_up / container_down  # start/stop containers without rebuilding
just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite via Dataflow (dataflow/config.json)
just pg_export_sqlite_dry_run # validate the Dataflow config, write nothing
just db_diagram               # generate SVG schema diagram from the SQLModel classes
just mathesar_bootstrap       # create mathesar_django DB + admin user + DB connection (idempotent; local Docker only)
just mathesar_summaries       # apply record summaries (utils/mathesar/.../record_summaries.json)
just mathesar_display         # apply column display metadata (column_display.json)
just util_open                # open the gateway (Mathesar) in the browser
```

The import/reset recipes (`pg_validate`, `pg_import`, `pg_reimport`, `pg_schema_create`, `pg_schema_drop`, `pg_reset`, `reinit`) and `iiif_*` were removed in October 2026. Do not re-add them.

**Which database a recipe hits:**
- **`utils`-container recipes** (`db_diagram`, `mathesar_*` RPC scripts) use `PG_DATABASE_URL`. That is `dev.env`'s local Docker Postgres unless a local `.env` overrides it. The developer's `.env` remote URLs are commented out, so there is no production access from this checkout.
- **`pg_export_sqlite`** does **not** follow `.env`. `dataflow/config.json` hard-codes the DSN, currently the local Docker `postgres:5432`. Make sure that DSN points at the up-to-date database before exporting.
- **`mathesar_bootstrap`** exec's into the local `postgres` container, so it is local only.

Gateway (Caddy) runs on port 9160 and reverse-proxies the Mathesar admin UI (port 8000).

## Architecture

### Docker Services (compose.yml)

- **postgres** — PostgreSQL 17, local copy (production lives on `gcdhpsqlprd1`)
- **mathesar** — Mathesar admin UI (port 8000), browses/edits the PostgreSQL data
- **utils** — Python utilities container (no long-running process; used for one-off tasks via `docker compose run`)
- **gateway** — Caddy reverse proxy (port 9160 → Mathesar)

### Python Utilities (`utils/`)

Three standalone sub-packages, each with its own `pyproject.toml`, run via `docker compose run -w /app/<pkg>`:

- **`utilities/`** — Shared library: SQLModel data model (`model.py`), database engine config (`db.py`), env config (`config.py`)
- **`mathesar/`** (`mathesar_tools`) — Mathesar JSON-RPC scripts: `mathesar-connect-db`, `mathesar-record-summaries` (`record_summaries.json`), `mathesar-column-display` (`column_display.json`)
- **`documenter/`** — Generates the SVG entity diagram from the SQLModel classes

### Data model

`utils/utilities/src/utilities/model.py` (SQLModel) describes the schema as it was created in July 2026. The production DB has since been modified in Mathesar, so **the live database wins**: check it with `\d+` / `information_schema` before relying on `model.py`, and update `model.py` (used by `db_diagram`) when they drift. Apply schema changes as migrations (ALTER) on the live DB, never by recreating and re-importing.

Conventions:
- Primary keys are `<table>_id` (autoincrement), never plain `id`.
- Foreign keys are real constraints, mirrored by `Relationship(back_populates=...)` on both sides in `model.py`.
- Columns loaded from the workbook carry a PostgreSQL column comment naming their original Excel column (provenance only).
- Identifiers: `text.identifier` = `BHL`/`NO_BHL` prefix + `_` + uid (e.g. `BHL_29`, `NO_BHL_ALPER`); `manuscript.identifier` = prefix + `_` + copy id (e.g. `BHL_29-4`; **not unique**); `edition.identifier_per_text` (e.g. `BHL_29-A`).
- `manuscript` and `edition` have no `title`. The title lives on `text` via `text_id`, which is nullable on both.
- Naming inconsistencies exist in the live schema. Don't rename them silently, because that breaks the Mathesar config and the export: `text.dating_range_stop` vs `manuscript.dating_range_end`; `dating_confidence.notes` vs `note` elsewhere; `destinary_*` columns vs "destinatary".

Entities:
- **Text** — dating, réécriture self-FK, author FK, creation/destinary geography FKs. Lookups: TextForm, TextSourceType, TextSourceSubtype, DatingConfidence.
- **Author** — lookup AuthorMilieu.
- Geography — **Location** (name, lat/long), **Archdiocese**, **Diocese**, **Institution** (each with an optional `location_id`).
- **Manuscript** — codex fields, dating, origin/provenance FKs into the geography tables with OriginConfidence/ProvenanceConfidence. Lookups: ManuscriptPreservationStatus, ManuscriptHoldingInstitution, VernacularRegion, ManuscriptType.
- **ManuscriptLink** — typed URLs (ManuscriptLinkType).
- **ManuscriptRelation** — manuscript↔manuscript links (ManuscriptRelationshipType).
- **Edition** — reprint self-FK. Related tables:
  - **EditionLink** (EditionLinkType).
  - Link tables `edition__manuscripts` (EditionManuscript) and `edition__edition` (EditionEdition).
- **Repertory** and **RepertoryLink** — hand-curated.

The pre-restart 20-table model (`utils/utilities/src/utilities/legacy_model.py`) is parked, reference only. Nothing imports it, so do not build on it.

### Mathesar Admin

Mathesar (`mathesar/mathesar:0.11.0`) is the curation interface; it edits PostgreSQL directly. It keeps its own Django metadata DB (`mathesar_django`), separate from the research database. Record summaries and column display options are configured via JSON-RPC by `utils/mathesar/` (`just mathesar_summaries`, `just mathesar_display`). Re-run both if table OIDs change.

### Data Flow

```
Mathesar Admin ──(curation)──▶ PostgreSQL (source of truth) ──[Dataflow]──▶ data/hagiographies_full_export.sqlite
```

## Key Details

- `data/` is mostly gitignored (`*.csv *.xlsx *.db *.sqlite`). The schema diagram (`data/hagiographies_model(.svg)`) is tracked.
- Python version: 3.13, managed with UV.
- Environment config: `dev.env` (shared by all services and loaded by `just`) and `.env` (local override; remote `PG_DATABASE_URL`s are commented out).
