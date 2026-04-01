# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hagiographies is an Excel-to-SQLite import pipeline with a Kottster admin panel and MapLibre map frontend for browsing hagiographic manuscript data. Developed by Ghent Centre for Digital Humanities.

## Common Commands

All commands use `just` (a command runner). Everything runs in Docker containers.

```sh
just rebuild          # build and start all Docker containers
just import           # import Excel data into SQLite (runs in utils container)
just export-map       # export SQLite → GeoJSON, copy to local-map/data/
just kottster         # start Kottster dev server (port 5480)
just generate-diagram # generate SVG schema diagram from SQLModel
just map-data         # download PMTiles basemap for local-map
just reset-db         # delete SQLite database
just reinit           # full reset: rebuild + reset-db + import + export + map-data
just up / just down   # start/stop containers without rebuilding
```

Gateway (Caddy) runs on port 9160, serving both the admin UI and map.

## Architecture

### Docker Services (compose.yml)

- **data-management** — Kottster admin UI (Node.js/React, port 5480)
- **utils** — Python utilities container (no long-running process; used for one-off tasks via `docker compose run`)
- **gateway** — Caddy reverse proxy (port 9160 → Kottster + static map files)

### Python Utilities (`utils/`)

Four Python sub-packages managed with UV workspaces:

- **`utilities/`** — Shared library: SQLModel data model (`model.py`), database engine config (`db.py`), env config (`config.py`)
- **`importer/`** — Reads `hagiographies.xlsx`, normalizes data, populates SQLite via SQLModel
- **`exporter/`** — Reads SQLite Places with coordinates → outputs GeoJSON for the map
- **`documenter/`** — Generates SVG entity diagram from SQLModel classes

The canonical data model lives in `utils/utilities/src/utilities/model.py`. All tables use SQLite STRICT mode. The `Table` base class provides auto-incrementing ID and `created_at`/`updated_at` audit columns. Core entities: **Text** (~60 fields), **Manuscript** (~40 fields), **Edition**, with normalized lookups (Place, Institution, Author, Typology) and many-to-many join tables.

### Kottster Admin (`kottster/`)

React 19 + Kottster 3.x admin panel. Key structure:
- `app/_server/app.js` — server config, SQLite identity provider, auth
- `app/_server/data-sources/hagiographies_db/` — knex/better-sqlite3 adapter
- `app/pages/` — JSON-defined page configs for Text, Manuscript, Edition views
- `app/schemas/sidebar.json` — navigation config
- Two Dockerfiles: `Dockerfile` (dev), `prd.Dockerfile` (production multi-stage)

### Local Map (`local-map/`)

Static MapLibre GL JS app served by Caddy at `/map/`. Reads `hagiographies_map.geojson` and `world.pmtiles` from `local-map/data/`.

### Data Flow

```
hagiographies.xlsx → [importer] → hagiographies.db → [exporter] → hagiographies_map.geojson
                                        ↓                              ↓
                                   Kottster Admin              MapLibre Map (local-map/)
```

## CI/CD

GitHub Actions (`.github/workflows/release.yml`) builds and pushes the Kottster production container to `ghcr.io/ghentcdh/hagiographies` on pushes to main (kottster paths) or version tags.

## Key Details

- SQLite database at `/data/hagiographies.db` (container path); `data/` dir on host
- All `data/` contents are gitignored (db, csv, xlsx, geojson, pmtiles)
- Python version: 3.13, managed with UV
- Node version: 22 (Kottster containers)
- Environment config: `dev.env` (shared by all services), `.env` (local Python path override)
