# Hagiographies

Excel-to-SQLite import pipeline with a Kottster admin panel and MapLibre map for browsing hagiographic data.

## Commands

```sh
just rebuild          # build and start Docker containers
just up / just down   # start / stop containers
just import           # create tables and import Excel data
just export-map       # export SQLite → GeoJSON for the map
just kottster         # start Kottster dev server (port 5480)
just generate-diagram # generate SVG schema diagram
just map-data         # download PMTiles basemap
just reset-db         # delete SQLite database
just reinit           # full reset: rebuild + import + export + map-data
just open-admin       # open Kottster admin in browser
just open-map         # open map frontend in browser
```

## Database Migration
For details on the PostgreSQL integration and how to transition to a Postgres-first workflow, see [MIGRATION_POSTGRESQL.md](MIGRATION_POSTGRESQL.md).

## Project Structure

```
├── utils/                 # Python utilities (Docker)
│   ├── importer/          #   Excel → SQLite import
│   ├── exporter/          #   SQLite → GeoJSON export
│   ├── documenter/        #   Schema diagram generator
│   └── utilities/         #   Shared model & db config
├── kottster/              # Admin UI (React/Kottster 3)
├── local-map/             # MapLibre map frontend
├── caddy/                 # Reverse proxy config
├── data/                  # SQLite db & data files (gitignored)
├── compose.yml            # Docker Compose services
└── justfile               # Task runner commands
```

## Credits

Development by [Ghent Centre for Digital Humanities - Ghent University](https://www.ghentcdh.ugent.be/). Funded by the [GhentCDH research projects](https://www.ghentcdh.ugent.be/projects).

<img src="https://www.ghentcdh.ugent.be/ghentcdh_logo_blue_text_transparent_bg_landscape.svg" alt="Landscape" width="500">
