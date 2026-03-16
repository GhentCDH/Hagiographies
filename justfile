KOTTSTER_HOST := "localhost"
KOTTSTER_PORT := "5490"
KOTTSTER_PATH := "/admin"
KOTTSTER_URL  := "http://{{KOTTSTER_HOST}}:{{KOTTSTER_PORT}}{{KOTTSTER_PATH}}"

# ── Docker lifecycle ─────────────────────────────────────────────────────────

rebuild:
    docker compose down -t 1
    docker compose up -d --build

up:
    docker compose up -d

down:
    docker compose down

# ── Import ───────────────────────────────────────────────────────────────────

import:
    docker compose run  -w /app/importer --rm utils  uv run importer

export-map:
    docker compose run  -w /app/exporter --rm utils  uv run export-map

# ── Kaartdata (pmtiles) ──────────────────────────────────────────────────────
# Haalt de nieuwste Protomaps Africa-tegel op en zet die in ./local-map/data/
map-data:
    mkdir -p local-map/data
    docker run --rm \
        -v "$(pwd)/local-map/data:/out" \
        ghcr.io/protomaps/go-pmtiles:latest extract \
        "https://build.protomaps.com/$(curl -s https://build-metadata.protomaps.dev/builds.json | \
          node -e "const b=require('fs').readFileSync('/dev/stdin','utf8');\
          console.log(JSON.parse(b).sort((a,b)=>b.key<a.key?-1:1)[0].key)")" \
        /out/world.pmtiles \
        --bbox=-15,30,45,70 \
        --maxzoom=8

# Een alternatieve download-script optie (indien pmtiles binary niet beschikbaar is)
download-world:
    node local-map/scripts/download-world-pmtiles.js \
        --bbox=-15,30,45,70 \
        --output=local-map/data/world.pmtiles \
        --maxzoom=8



# ── Data Management (Kottster) ───────────────────────────────────────────────

kottster:
    docker compose exec data-management ./scripts/dev.sh

# ── Database ─────────────────────────────────────────────────────────────────

reset-db:
    rm -f data/hagiographies.db*

reinit: rebuild reset-db import export-map map-data

# ── Dev helpers ──────────────────────────────────────────────────────────────

open-admin:
    @echo "Waiting for {{KOTTSTER_URL}}..."
    @until nc -z {{KOTTSTER_HOST}} {{KOTTSTER_PORT}}; do \
      printf "."; sleep 0.5; \
    done
    @echo "\n{{KOTTSTER_URL}} ready!"
    @if [ "{{os()}}" = "macos" ]; then \
      open "{{KOTTSTER_URL}}"; \
    elif [ "{{os()}}" = "linux" ]; then \
      xdg-open "{{KOTTSTER_URL}}"; \
    else \
      start "{{KOTTSTER_URL}}"; \
    fi

open-map:
    @if [ "{{os()}}" = "macos" ]; then \
      open "http://localhost/map/"; \
    elif [ "{{os()}}" = "linux" ]; then \
      xdg-open "http://localhost/map/"; \
    else \
      start "http://localhost/map/"; \
    fi