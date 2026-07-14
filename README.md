# Hagiographies

Excel-to-PostgreSQL import pipeline with a Mathesar admin UI for browsing hagiographic data.

## Commands

```sh
just rebuild                  # build and start Docker containers
just up / just down           # start / stop containers
just import-pg                # create tables and import Excel data into PostgreSQL
just export-from-pg-to-sqlite # dump PostgreSQL → data/hagiographies_full_export.sqlite (Dataflow)
just generate-diagram         # generate SVG schema diagram
just reinit                   # full reset: rebuild + import + Mathesar bootstrap
just open_url                 # open the gateway (Mathesar admin) in browser
```

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
