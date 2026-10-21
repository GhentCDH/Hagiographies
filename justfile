set dotenv-load := true
# just only loads `.env` by default; the recipes need the POSTGRES_*/MATHESAR_*
# variables that live in dev.env (shared with the Docker services).
set dotenv-filename := "dev.env"
GATEWAY_URL := "http://localhost:9160"

# ── Containers ─────────────────────────────────────────────────────────────

# Build and start all Docker containers
container_rebuild:
    docker compose down -t 1
    docker compose up -d --build

# Start containers
container_up:
    docker compose up -d

# Stop containers
container_down:
    docker compose down

# ── Database (schema tooling) ──────────────────────────────────────────────

# Generate SVG schema diagram from SQLModel
db_diagram:
    docker compose run  -w /app/documenter --rm utils  uv run document

# ── Mathesar ─────────────────────────────────────────────────────────────────

# Idempotent — safe to re-run. Targets the local Docker Postgres (it exec's psql
# inside the postgres container), so it is not meaningful against a remote DB.
# Bootstrap a fresh Mathesar (metadata DB + admin user + DB connection; LOCAL Docker only)
mathesar_bootstrap:
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
mathesar_summaries:
    docker compose run -w /app/mathesar --rm utils uv run mathesar-record-summaries

# Reads column_display.json (e.g. no thousands separator on year columns)
# Apply column display metadata to Mathesar tables
mathesar_display:
    docker compose run -w /app/mathesar --rm utils uv run mathesar-column-display

# ── PostgreSQL (export) ────────────────────────────────────────────────────

# The PostgreSQL database (curated in Mathesar) is the source of truth.
# The source DSN of the export is set in dataflow/config.json.

# Full dump; config in dataflow/config.json. Output at data/hagiographies_full_export.sqlite.
# Export PostgreSQL → SQLite via Dataflow
pg_export_sqlite:
    docker run --rm --network hagiographies_default \
        -v "$(pwd)/dataflow:/data" -v "$(pwd)/data:/out" \
        ghcr.io/ghentcdh/dataflow:v0.1.0 run --config /data/config.json

# Validate the Dataflow export config and show the plan without writing anything
pg_export_sqlite_dry_run:
    docker run --rm --network hagiographies_default \
        -v "$(pwd)/dataflow:/data" -v "$(pwd)/data:/out" \
        ghcr.io/ghentcdh/dataflow:v0.1.0 run --config /data/config.json --dry-run

# ── Dev helpers ──────────────────────────────────────────────────────────────

# Open the gateway (Mathesar admin) in browser
util_open:
  open "{{GATEWAY_URL}}"
