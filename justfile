set dotenv-load := true
# just only loads `.env` by default; the recipes need the POSTGRES_*/MATHESAR_*
# variables that live in dev.env (shared with the Docker services).
set dotenv-filename := "dev.env"
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

# Export PostgreSQL → SQLite via Dataflow (full dump; config in dataflow/config.json).
# Output appears at data/hagiographies_full_export.sqlite.
export-from-pg-to-sqlite:
    docker run --rm --network hagiographies_default \
        -v "$(pwd)/dataflow:/data" -v "$(pwd)/data:/out" \
        ghcr.io/ghentcdh/dataflow:v0.1.0 run --config /data/config.json

# Validate the Dataflow export config and show the plan without writing anything
export-from-pg-to-sqlite-dry-run:
    docker run --rm --network hagiographies_default \
        -v "$(pwd)/dataflow:/data" -v "$(pwd)/data:/out" \
        ghcr.io/ghentcdh/dataflow:v0.1.0 run --config /data/config.json --dry-run

# ── IIIF ─────────────────────────────────────────────────────────────────────

# Check whether IIIF image links point to a real manifest; writes
# data/iiif_manifest_report.csv
check-iiif:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/importer --rm utils uv run check-iiif

# Same, but also discover manifests on viewer pages and store them in
# image.iiif_manifest_url
fix-iiif:
    docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/importer --rm utils uv run check-iiif --fix

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

# Apply column display metadata (e.g. no thousands separator on year columns)
# from column_display.json
mathesar-display:
    docker compose run -w /app/mathesar --rm utils uv run mathesar-column-display

# ── Database ─────────────────────────────────────────────────────────────────

# Wipe the PostgreSQL data (research DB + Mathesar metadata) by recreating its
# volume, then start clean. The importer is insert-only and skips existing BHLs,
# so a true "from the Excel" re-import requires this wipe first.
reset-pg:
    docker compose down -t 5
    docker volume rm hagiographies_postgres-data
    docker compose up -d

# Full reset: wipe PG, rebuild, import to PG, bootstrap Mathesar
# (metadata DB + admin user + DB connection), apply summaries + display config
reinit: reset-pg rebuild import-pg mathesar-bootstrap mathesar-summaries mathesar-display

# ── Dev helpers ──────────────────────────────────────────────────────────────

# Open the gateway (Mathesar admin) in browser
open_url:
  open "{{GATEWAY_URL}}"