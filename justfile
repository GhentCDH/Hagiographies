set dotenv-load := true
GATEWAY_URL := "http://localhost:9160"

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

# Import Excel data into PostgreSQL
import-pg:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/importer --rm utils  uv run importer


# Export PostgreSQL → GeoJSON and copy to local-map/data/
export-map:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/exporter --rm utils  uv run export-map
    cp data/hagiographies_map.geojson local-map/data/

# Migrate PostgreSQL → SQLite snapshot (columns in exporter/filter.json are dropped)
export-from-pg-to-sqlite:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/exporter --rm utils  uv run export-from-pg-to-sqlite

# Alias for export-map
export: export-map

# Run export pipeline tests
test-export:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/exporter --rm utils uv run pytest -v tests/

# ── Modelgeneratie ───────────────────────────────────────────────────────────

# Generate SVG schema diagram from SQLModel
generate-diagram:
    docker compose run  -w /app/documenter --rm utils  uv run document

# ── Mathesar ─────────────────────────────────────────────────────────────────

# Bootstrap a fresh Mathesar: create its metadata DB, the admin superuser, and
# register the research DB connection. Idempotent — safe to re-run.
mathesar-bootstrap:
    # Mathesar does not create its own metadata DB; create it if missing.
    docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -tc \
        "SELECT 1 FROM pg_database WHERE datname='mathesar_django'" | grep -q 1 \
        || docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -c \
        "CREATE DATABASE mathesar_django OWNER $POSTGRES_USER;"
    docker compose restart mathesar
    # Wait until Mathesar has migrated its metadata DB (mathesar_user exists).
    until docker compose exec -T postgres psql -U "$POSTGRES_USER" -d mathesar_django \
        -c "select 1 from mathesar_user limit 1;" >/dev/null 2>&1; do sleep 2; done
    # Create the admin superuser if it does not already exist.
    docker compose exec -T -e DJANGO_SUPERUSER_PASSWORD="$MATHESAR_PASSWORD" mathesar \
        sh -c 'cd /code && python manage.py createsuperuser --no-input \
        --username "$MATHESAR_USERNAME" --email admin@example.com' || true
    # Register the research database connection (id should be MATHESAR_DATABASE_ID).
    docker compose run -w /app/mathesar --rm utils uv run mathesar-connect-db || true

# Apply record summaries to Mathesar tables from record_summaries.json
mathesar-summaries:
    docker compose run -w /app/mathesar --rm utils uv run mathesar-record-summaries

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

# ── Database ─────────────────────────────────────────────────────────────────

# Delete the derived SQLite snapshot files
reset-db:
    rm -f data/public_hagiographies.db*

# Wipe the PostgreSQL data (research DB + Mathesar metadata) by recreating its
# volume, then start clean. The importer is insert-only and skips existing BHLs,
# so a true "from the Excel" re-import requires this wipe first.
reset-pg:
    docker compose down -t 5
    docker volume rm hagiographies_postgres-data
    docker compose up -d

# Full reset: wipe PG, rebuild, reset db, import to PG, bootstrap Mathesar
# (metadata DB + admin user + DB connection), apply summaries, migrate to
# SQLite, export map data, download map data
reinit: reset-pg rebuild reset-db import-pg mathesar-bootstrap mathesar-summaries export-from-pg-to-sqlite export-map map-data

# ── Dev helpers ──────────────────────────────────────────────────────────────

# Open the gateway (map + Mathesar admin) in browser
open_url:
  open "{{GATEWAY_URL}}"