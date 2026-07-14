# Hagiographies

Excel-to-PostgreSQL import pipeline with a Mathesar admin UI for browsing hagiographic data.

## Commands

```sh
just container_rebuild        # build and start Docker containers
just container_up / container_down  # start / stop containers
just pg_import                # create tables and import Excel data into PostgreSQL
just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite (Dataflow)
just db_diagram               # generate SVG schema diagram
just reinit                   # full reset: rebuild + import + Mathesar bootstrap (local Docker)
just util_open                # open the gateway (Mathesar admin) in browser
```

Recipes are grouped by prefix (`container_`, `db_`, `iiif_`, `mathesar_`, `pg_`); run
`just --list` to see them all.

**Local vs remote database:** by default the recipes target the local Docker
Postgres (`dev.env`'s `PG_DATABASE_URL`, host `postgres`). To point `pg_import`
and the `iiif_*` recipes at a remote server instead, set `PG_DATABASE_URL` to a
remote URL in a local `.env` file (gitignored) — it overrides `dev.env` in the
`utils` container. `pg_reset` and `reinit` are local-Docker-only (they recreate
the `postgres-data` volume), so skip them when using a remote DB.

## Database
For details on the PostgreSQL architecture and operations, see [POSTGRESQL.md](POSTGRESQL.md).

## Project Structure

```
├── utils/                 # Python utilities (Docker)
│   ├── importer/          #   Excel → PostgreSQL import
│   ├── documenter/        #   Schema diagram generator
│   ├── mathesar/          #   Mathesar record-summary config (JSON-RPC)
│   └── utilities/         #   Shared model & db config
├── caddy/                 # Reverse proxy config (Mathesar)
├── dataflow/              # Dataflow config for the SQLite export
├── data/                  # db & data files (gitignored)
├── compose.yml            # Docker Compose services
└── justfile               # Task runner commands
```

## Credits

Development by [Ghent Centre for Digital Humanities - Ghent University](https://www.ghentcdh.ugent.be/). Funded by the [GhentCDH research projects](https://www.ghentcdh.ugent.be/projects).

<img src="https://www.ghentcdh.ugent.be/ghentcdh_logo_blue_text_transparent_bg_landscape.svg" alt="Landscape" width="500">
