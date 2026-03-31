# Hagiographies

Excel-to-SQLite import pipeline with a Kottster admin panel and MapLibre map for browsing hagiographic data.

## Setup

```sh
just rebuild   # build Docker containers
just import    # create tables and import Excel data
just kottster  # start Kottster dev server on port 5480
```

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
