# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hagiographies is an Excel-to-PostgreSQL import pipeline with a Mathesar admin UI and MapLibre map frontend for browsing hagiographic manuscript data. A general PostgreSQL→SQLite migration produces a derived, publishable SQLite snapshot. Developed by Ghent Centre for Digital Humanities.

## Common Commands

All commands use `just` (a command runner). Everything runs in Docker containers.

```sh
just rebuild                  # build and start all Docker containers
just import-pg                # import Excel data into PostgreSQL (runs in utils container)
just export-from-pg-to-sqlite # migrate PostgreSQL → SQLite snapshot (filter.json drops columns)
just export-map               # export PostgreSQL → GeoJSON, copy to local-map/data/
just generate-diagram         # generate SVG schema diagram from SQLModel
just map-data                 # download PMTiles basemap for local-map
just reset-db                 # delete the derived SQLite snapshot
just reinit                   # full reset: rebuild + reset-db + import-pg + migrate + export + map-data
just up / just down           # start/stop containers without rebuilding
```

Gateway (Caddy) runs on port 9160, serving the static map and reverse-proxying the Mathesar admin UI.

## Architecture

### Docker Services (compose.yml)

- **postgres** — PostgreSQL 17, the canonical data store
- **mathesar** — Mathesar admin UI (port 8000), browses/edits the PostgreSQL data
- **utils** — Python utilities container (no long-running process; used for one-off tasks via `docker compose run`)
- **gateway** — Caddy reverse proxy (port 9160 → static map files + Mathesar)

### Python Utilities (`utils/`)

Four Python sub-packages managed with UV workspaces:

- **`utilities/`** — Shared library: SQLModel data model (`model.py`), database engine config (`db.py`), env config (`config.py`)
- **`importer/`** — Reads `hagiographies.xlsx`, normalizes data, populates PostgreSQL via SQLModel
- **`exporter/`** — `export_sqlite.py` migrates PostgreSQL → SQLite (dropping columns listed in `filter.json`); `export_map.py` reads Places with coordinates → GeoJSON for the map
- **`documenter/`** — Generates SVG entity diagram from SQLModel classes

The canonical data model lives in `utils/utilities/src/utilities/model.py` and targets PostgreSQL. The `Table` base class provides auto-incrementing ID and `created_at`/`updated_at` audit columns (re-ordered to appear last via `_move_audit_columns_last()`). Core entities: **Text** (~60 fields), **Manuscript** (~40 fields), **Edition**, with normalized lookups (Place, Institution, Author, Typology) and many-to-many join tables.

### Mathesar Admin

Mathesar (`mathesar/mathesar:0.11.0`) browses and edits the PostgreSQL data directly.
It keeps its own Django metadata DB (`mathesar_django`), separate from the research
database. Record summaries (the display label per table) are configured via the
JSON-RPC API by `utils/mathesar/` (`just mathesar-summaries`).

### Local Map (`local-map/`)

Static MapLibre GL JS app served by Caddy at `/map/`. Reads `hagiographies_map.geojson` and `world.pmtiles` from `local-map/data/`.

### Data Flow

```
hagiographies.xlsx → [importer] → PostgreSQL → [export_sqlite] → public_hagiographies.db
                                       │
                                       ├────── Mathesar Admin (edits PostgreSQL directly)
                                       │
                                       └────── [export_map] → hagiographies_map.geojson → MapLibre Map (local-map/)
```

## Key Details

- PostgreSQL is the canonical store (service `postgres`); the importer and model target it
- Mathesar (port 8000) is the admin UI, editing PostgreSQL directly; fronted by the gateway at port 9160
- Derived SQLite snapshot at `/data/public_hagiographies.db` (container path); `data/` dir on host
- All `data/` contents are gitignored (db, csv, xlsx, geojson, pmtiles)
- Python version: 3.13, managed with UV
- Environment config: `dev.env` (shared by all services), `.env` (local Python path override)
