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

# ── IIIF ─────────────────────────────────────────────────────────────────────
# LEGACY — check-iiif targets the parked old schema (image/codex tables in
# utilities.legacy_model) and cannot run against the current database.

# Check IIIF image links point to a real manifest (writes data/iiif_manifest_report.csv)
iiif_check:
    docker compose run -w /app/importer --rm utils uv run check-iiif

# Like iiif_check, but also discover manifests on viewer pages → image.iiif_manifest_url
iiif_fix:
    docker compose run -w /app/importer --rm utils uv run check-iiif --fix

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

# ── PostgreSQL (data) ──────────────────────────────────────────────────────

# The target DB is whatever PG_DATABASE_URL resolves to in the utils container:
# dev.env's local Docker Postgres by default, or a remote server if .env
# overrides PG_DATABASE_URL. config.py reads DATABASE_URL or PG_DATABASE_URL,
# so no explicit -e is needed.
# The importer never fixes Excel data: rows failing strict validation are
# skipped and reported (exit 1); fix the workbook, then re-run.

# Validate the Excel workbook only — no database writes (report: data/import_report.csv)
pg_validate:
    docker compose run -w /app/importer --rm utils uv run importer validate

# Create the metadata schema (DDL only, no data)
pg_schema_create:
    docker compose run -w /app/importer --rm utils uv run importer create-schema

# Drop + recreate the public schema of the research DB (destructive; local or remote!)
pg_schema_drop:
    docker compose run -w /app/importer --rm utils uv run importer drop-schema --yes

# Import Excel data into PostgreSQL, creating the schema if needed
pg_import:
    docker compose run -w /app/importer --rm utils uv run importer import-data --create-schema

# Full DB-level refresh: drop the public schema, recreate it, re-import.
# Re-run mathesar_summaries/mathesar_display afterwards (table OIDs change).
pg_reimport: pg_schema_drop pg_import

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

# Recreates the postgres-data volume then starts clean. For a normal refresh
# use pg_reimport (schema drop + import) — this wipe is only needed to also
# reset Mathesar's metadata DB. LOCAL Docker Postgres ONLY — it removes the
# volume and cannot reset a remote DB; skip when pointing at a remote
# PG_DATABASE_URL.
# Wipe the PostgreSQL data (research DB + Mathesar metadata); LOCAL Docker only
pg_reset:
    docker compose down -t 5
    docker volume rm hagiographies_postgres-data
    docker compose up -d

# ── Full reset ─────────────────────────────────────────────────────────────

# Chains pg_reset + container_rebuild + pg_import + mathesar_bootstrap +
# summaries + display. LOCAL Docker Postgres ONLY (pg_reset wipes the volume).
# Full reset: wipe PG, rebuild, import, bootstrap Mathesar, apply config
reinit: pg_reset container_rebuild pg_import mathesar_bootstrap mathesar_summaries mathesar_display

# ── Dev helpers ──────────────────────────────────────────────────────────────

# Open the gateway (Mathesar admin) in browser
util_open:
  open "{{GATEWAY_URL}}"
