KOTTSTER_URL := "http://localhost:9160"

# ── Docker lifecycle ─────────────────────────────────────────────────────────

# Build and start all Docker containers
rebuild:
    docker compose down -t 1
    docker compose up -d --build

# Start containers
up:
    docker compose up -d

# Stop containers
down:
    docker compose down

# ── Import ───────────────────────────────────────────────────────────────────

# Import Excel data into SQLite
import:
    docker compose run  -w /app/importer --rm utils  uv run importer

# Export SQLite → GeoJSON and copy to local-map/data/
export-map:
    docker compose run  -w /app/exporter --rm utils  uv run export-map
    cp data/hagiographies_map.geojson local-map/data/

# Alias for export-map
export: export-map

# ── Modelgeneratie ───────────────────────────────────────────────────────────

# Generate SVG schema diagram from SQLModel
generate-diagram:
    docker compose run  -w /app/documenter --rm utils  uv run document

# ── Kaartdata (pmtiles) ──────────────────────────────────────────────────────

# Download latest Protomaps PMTiles basemap (Europe/Africa bbox)
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

# Alternative PMTiles download via Node script
download-world:
    node local-map/scripts/download-world-pmtiles.js \
        --bbox=-15,30,45,70 \
        --output=local-map/data/world.pmtiles \
        --maxzoom=8

# ── Data Management (Kottster) ───────────────────────────────────────────────

# Start Kottster dev server (port 5480)
kottster:
    docker compose exec data-management ./scripts/dev.sh

# ── Database ─────────────────────────────────────────────────────────────────

# Delete SQLite database files
reset-db:
    rm -f data/hagiographies.db*

# Full reset: rebuild, reset db, import, export, and download map data
reinit: rebuild reset-db import export-map map-data

# ── Dev helpers ──────────────────────────────────────────────────────────────

# Wait for Kottster and open admin UI in browser
open_url:
  open "{{KOTTSTER_URL}}"