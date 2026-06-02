# Hagiographies

Excel-to-PostgreSQL import pipeline with a Mathesar admin UI and MapLibre map for browsing hagiographic data.

## Commands

```sh
just rebuild                  # build and start Docker containers
just up / just down           # start / stop containers
just import-pg                # create tables and import Excel data into PostgreSQL
just export-from-pg-to-sqlite # migrate PostgreSQL → SQLite snapshot
just export-map               # export PostgreSQL → GeoJSON for the map
just generate-diagram         # generate SVG schema diagram
just map-data                 # download PMTiles basemap
just reset-db                 # delete the derived SQLite snapshot
just reinit                   # full reset: rebuild + import + migrate + export + map-data
just open_url                 # open the gateway (map + admin) in browser
```

## Database Migration
For details on the PostgreSQL integration and how to transition to a Postgres-first workflow, see [MIGRATION_POSTGRESQL.md](MIGRATION_POSTGRESQL.md).

## Project Structure

```
├── utils/                 # Python utilities (Docker)
│   ├── importer/          #   Excel → PostgreSQL import
│   ├── exporter/          #   PostgreSQL → SQLite + GeoJSON export
│   ├── documenter/        #   Schema diagram generator
│   ├── mathesar/          #   Mathesar record-summary config (JSON-RPC)
│   └── utilities/         #   Shared model & db config
├── local-map/             # MapLibre map frontend
├── caddy/                 # Reverse proxy config (map + Mathesar)
├── data/                  # db & data files (gitignored)
├── compose.yml            # Docker Compose services
└── justfile               # Task runner commands
```

## Credits

Development by [Ghent Centre for Digital Humanities - Ghent University](https://www.ghentcdh.ugent.be/). Funded by the [GhentCDH research projects](https://www.ghentcdh.ugent.be/projects).

<img src="https://www.ghentcdh.ugent.be/ghentcdh_logo_blue_text_transparent_bg_landscape.svg" alt="Landscape" width="500">
