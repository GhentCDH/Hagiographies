# Hagiographies

PostgreSQL database of hagiographic texts, manuscripts and editions, curated through
a Mathesar admin UI and exported to SQLite. The PostgreSQL database is the single
source of truth. The original Excel import was a one-off and is no longer used.

## Commands

```sh
just container_rebuild        # build and start Docker containers
just container_up / container_down  # start / stop containers
just pg_export_sqlite         # dump PostgreSQL → data/hagiographies_full_export.sqlite (Dataflow)
just db_diagram               # generate SVG schema diagram
just mathesar_summaries       # apply Mathesar record summaries
just mathesar_display         # apply Mathesar column display settings
just util_open                # open the gateway (Mathesar admin) in browser

```

Recipes are grouped by prefix (`container_`, `db_`, `mathesar_`, `pg_`, `util_`);
run `just --list` to see them all.

**Local vs remote database:** by default the recipes target the local Docker
Postgres (`dev.env`'s `PG_DATABASE_URL`, host `postgres`). To point the `utils`
recipes (`mathesar_*`) at a remote server instead, set `PG_DATABASE_URL` to a
remote URL in a local `.env` file (gitignored) — it overrides `dev.env` in the
`utils` container. The SQLite export does not follow `.env`: its source DSN is
set in `dataflow/config.json`. The obsolete Excel-import and reset recipes have been
removed.

## Database
For details on the PostgreSQL architecture and operations, see [POSTGRESQL.md](POSTGRESQL.md).

## Project Structure

```
├── utils/                 # Python utilities (Docker)
│   ├── documenter/        #   Schema diagram generator
│   ├── mathesar/          #   Mathesar config via JSON-RPC (summaries, display)
│   └── utilities/         #   Shared model & db config
├── caddy/                 # Reverse proxy config (Mathesar)
├── dataflow/              # Dataflow config for the SQLite export
├── data/                  # db & data files (mostly gitignored)
├── compose.yml            # Docker Compose services
└── justfile               # Task runner commands
```

## Credits

Development by [Ghent Centre for Digital Humanities - Ghent University](https://www.ghentcdh.ugent.be/). Funded by the [GhentCDH research projects](https://www.ghentcdh.ugent.be/projects).

<img src="https://www.ghentcdh.ugent.be/ghentcdh_logo_blue_text_transparent_bg_landscape.svg" alt="Landscape" width="500">
