# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hagiographies is a PostgreSQL database of hagiographic texts, manuscripts and editions. It is curated through a Mathesar admin UI and exported to SQLite, with a file explorer for the scanned images on the network share. Developed by Ghent Centre for Digital Humanities.

**The PostgreSQL database is the single source of truth.** Researchers edit and extend it directly in Mathesar. The servers are QAS (`gcdhpsqlqas1`) and PRD (`gcdhpsqlprd1.ugent.be`), both VPN-only.

The original Excel workbook import was a one-off initial load (July 2026). The importer (`utils/importer/`) and its recipes were removed in October 2026 and remain in git history. Do not resurrect them: a re-import would overwrite curated data.

## Common Commands

All commands use `just` (a command runner). Run `just --list` to see all recipes; they are grouped by prefix (`container_`, `db_`, `files_`, `mathesar_`, `pg_`, `util_`). Most run in Docker containers; the `db_` migration recipes and the `files_` dev recipes run on the **host**.

```sh
just container_rebuild        # build and start all Docker containers
just container_up / container_down  # start/stop containers without rebuilding

just db_migrate_status        # which schema migrations are applied / pending
just db_migrate_dry_run       # report what migrating would do
just db_migrate               # apply pending migrations from db/migrations/ (PG_DATABASE_URL)
just db_migrate_prd           # apply pending migrations to PRD (PG_DATABASE_URL_PRD)
just db_local_migrate         # apply pending migrations to the local Docker Postgres
just db_clone_qas             # copy the remote DB's public schema into the local Docker Postgres (destructive, local only)
just db_scratch               # throwaway hagiographies_scratch copy of the local DB with all migrations applied
just db_diagram               # SVG diagram from the SQLModel classes (stale model, see below)

just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite via Dataflow (dataflow/config.json)
just pg_export_sqlite_dry_run # validate the Dataflow config, write nothing

just mathesar_bootstrap       # create mathesar_django DB + admin user + DB connection (idempotent; local Docker only)
just mathesar_summaries       # apply record summaries (utils/mathesar/.../record_summaries.json)
just mathesar_display         # apply column display metadata (column_display.json)

just files_run / files_dev    # file explorer backend (:3000) / Vite dev server
just files_up / files_logs    # file explorer container on :9161
just util_open                # open the gateway (Mathesar) in the browser
```

The import and reset recipes were removed in October 2026: `pg_validate`, `pg_import`, `pg_reimport`, `pg_schema_create`, `pg_schema_drop`, `pg_reset`, `reinit` and `iiif_*`. Do not re-add them.

**Which database a recipe hits:**
- **`db_*` host recipes** use `PG_DATABASE_URL` from `.env` (via direnv). The exceptions are `db_local_*`/`db_scratch*`, which use the local Docker Postgres, and `db_migrate_prd`, which uses `PG_DATABASE_URL_PRD`.
- **`utils`-container recipes** (`db_diagram`, `mathesar_*`) use `PG_DATABASE_URL`. That is `dev.env`'s local Docker Postgres unless a local `.env` overrides it.
- **`pg_export_sqlite`** does **not** follow `.env`. `dataflow/config.json` hard-codes the DSN, currently the local Docker `postgres:5432`. Make sure that DSN points at an up-to-date database before exporting (e.g. after `db_clone_qas`).

Gateway (Caddy) runs on port 9160 and reverse-proxies the Mathesar admin UI (port 8000).

## Schema Changes: `db/migrations/` Is the Source of Truth

The schema evolves through numbered SQL migrations in `db/migrations/`, applied by `just db_migrate`.
- **`000_init.sql`** is a frozen baseline: the `public` schema as it stood on 2026-07-29. On a database that already has it, the runner records it as applied without executing it.
- **Immutability:** a migration cannot change once applied. The runner stores a checksum and refuses to continue if a file changed; add a new migration instead.
- **Bookkeeping** lives in the **`hagio_admin`** schema, not `public`, so that `public` holds research data only. Editors are never granted `USAGE` on it. See `db/README.md`.

**Mathesar edits the schema too.** Setting a column's type in its UI is DDL, usually to a domain in its own `mathesar_types` schema. The runner tracks files, not schema state, so it cannot detect such changes. Reproduce each one as a new migration (see `004_manuscript_link_url_uri.sql`):
- Guard it both against already being applied and against `mathesar_types` not existing.
- Use Mathesar's `msar.cast_to_<type>()`.

Consequences:
- `utils/utilities/src/utilities/model.py` (SQLModel) is **no longer kept in sync**. It describes the July 2026 import, not the current schema, so do not treat it as the schema. `db_diagram` therefore draws an outdated picture.
- `db/` is a standalone package (`psycopg` + `openpyxl`, no SQLModel). It runs on the **host** (`uv run --project db`), because the `utils` container's DNS cannot reliably reach the UGent servers or PyPI.
- `db/src/hagio_db/{backfill,report,workbook}.py` are the **retired** 2026-07 backfill. It populated `shelfmark`, `folio_or_page_range`, `codex` and `publication` from the workbook. It is kept as a record only, with no console script and no recipe. Do not resurrect it.

## Architecture

### Docker Services (compose.yml)

- **postgres** — PostgreSQL 17, local copy (refresh with `db_clone_qas`)
- **mathesar** — Mathesar admin UI (port 8000), browses/edits the PostgreSQL data
- **utils** — Python utilities container (no long-running process; used for one-off tasks via `docker compose run`)
- **file-explorer** — managed file explorer over the network share (port 9161; `file-explorer/`, Rust/Axum + Svelte)
- **gateway** — Caddy reverse proxy (port 9160 → Mathesar)

### Code layout

- **`db/`** — migration runner (`hagio_db.migrate`) and `migrations/*.sql`; runs on the host.
- **`file-explorer/`** — web app for finding, renaming, moving and uploading the scanned manuscript/edition images on the UGent share. It also copies working links into `manuscript_link.url`/`edition_link.url`. Its tables (`file`, `directory`, `*_link_reference`, …) live in `hagio_admin` (migrations 013–017). See `file-explorer/README.md`.
- **`utils/`** — three standalone Python sub-packages run in the `utils` container (`docker compose run -w /app/<pkg>`):
  - **`utilities/`** — SQLModel model (`model.py`, stale), engine config (`db.py`), env config (`config.py`).
  - **`mathesar/`** (`mathesar_tools`) — Mathesar JSON-RPC scripts: `mathesar-connect-db`, `mathesar-record-summaries` (`record_summaries.json`) and `mathesar-column-display` (`column_display.json`).
  - **`documenter/`** — SVG entity diagram from the SQLModel classes.
- **`dataflow/`** — Dataflow config for the SQLite export.
- **`scripts/`** — `backup_prd.sh`, `backup_qas.sh` and `clone_prd_to_qas.sh`.

### Data model

Inspect the live database (`\d+`, `information_schema`) and `db/migrations/` before relying on any description here.

Conventions:
- Primary keys are `<table>_id` (autoincrement), never plain `id`.
- Foreign keys are real constraints.
- Columns loaded from the workbook carry a PostgreSQL column comment naming their original Excel column (provenance only).
- Identifiers: `text.identifier` = `BHL`/`NO_BHL` prefix + `_` + uid (e.g. `BHL_29`, `NO_BHL_ALPER`); `manuscript.identifier` = prefix + `_` + copy id (e.g. `BHL_29-4`; **not unique**); `edition.identifier_per_text` (e.g. `BHL_29-A`).
- `manuscript` and `edition` have no `title`. The title lives on `text` via `text_id`, which is nullable on both.
- Naming inconsistencies exist in the live schema. Don't rename them silently, because that breaks the Mathesar config and the export: `text.dating_range_stop` vs `dating_range_end`; `dating_confidence.notes` vs `note` elsewhere; `destinary_*` columns vs "destinatary".

Entities (July 2026 baseline plus migrations 001–012):
- **Text** — dating, réécriture self-FK, author FK, creation/destinary geography FKs. Lookups: TextForm, TextSourceType, TextSourceSubtype, DatingConfidence.
- **Author** — lookup AuthorMilieu.
- Geography — **Location**, **Archdiocese**, **Diocese**, **Institution** (each with an optional `location_id`).
- **Codex** (002, columns hoisted in 009) — the physical codex.
  - Fields: shelfmark, holding institution, location, height/width, dating, preservation status, manuscript type, origin/provenance FKs with OriginConfidence/ProvenanceConfidence, vernacular region, legendiers/composite flags, notes.
  - Copy count and "multiple copies" are derived: `count(*)` over its manuscripts.
- **Manuscript** — one text copy in a codex: `codex_id`, `text_id`, `identifier`, `folio_or_page_range`.
  - Migration 011 dropped its codex-level columns.
  - Migration 012 dropped `codex_identifier`.
- **ManuscriptLink** — typed URLs (ManuscriptLinkType); `url` is `mathesar_types.uri`.
- **ManuscriptRelation** — manuscript↔manuscript links (ManuscriptRelationshipType).
- **Publication** (003, hoisted in 010) — `name`, `publication_year`, `reference`.
- **Edition** — per-edition fields (`publication_id`, `page_numbers`, reprint self-FK, `collation_done`, notes). Related tables:
  - **EditionLink** (EditionLinkType; `url` is `uri`).
  - Link tables `edition__manuscripts` and `edition__edition`.
- **Repertory** and **RepertoryLink** — hand-curated.

The pre-restart 20-table model (`utils/utilities/src/utilities/legacy_model.py`) is parked, reference only. Nothing imports it, so do not build on it.

### Mathesar Admin

Mathesar (`mathesar/mathesar:0.11.0`) is the curation interface; it edits PostgreSQL directly. It keeps its own Django metadata DB (`mathesar_django`), separate from the research database.
- Editors use the `hagiographies_editor` role: they can edit data but not change the schema (migrations 007/008).
- Record summaries and column display options are configured via JSON-RPC by `utils/mathesar/` (`just mathesar_summaries`, `just mathesar_display`). Re-run both if table OIDs change.

### Data Flow

```
Mathesar Admin ──(curation)──▶ PostgreSQL (source of truth; schema via db/migrations/) ──[Dataflow]──▶ data/hagiographies_full_export.sqlite
file-explorer ──(links into manuscript_link / edition_link; hagio_admin.file*)──▶ PostgreSQL
```

## Key Details

- `data/` is mostly gitignored. The schema diagram (`data/hagiographies_model(.svg)`) is tracked.
- Python version: 3.13, managed with UV.
- Environment config:
  - `dev.env` — shared by all services and loaded by `just`.
  - `.env` — host overrides via direnv: `PG_DATABASE_URL` for the `db_*` recipes, `PG_DATABASE_URL_PRD`.
