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

# ── Database (migrations) ──────────────────────────────────────────────────

# db/migrations/ is the source of truth for the schema; the SQLModel model in
# utils/utilities mirrors it and must be updated with every migration.
#
# These run on the HOST, not in the utils container, unlike the mathesar_* recipes.
# Two reasons: the container's DNS cannot reliably resolve the UGent servers
# (or even PyPI), and ./db is bind-mounted, so a container run and a host run
# would keep tearing down each other's db/.venv. The host already needs
# PG_DATABASE_URL for db_clone_qas, so nothing new is required — it comes from
# .env via direnv.

LOCAL_DB := "postgresql://" + env('POSTGRES_USER', 'hagiographies') + ":" + env('POSTGRES_PASSWORD', 'changeme') + "@localhost:" + env('POSTGRES_PORT', '5432') + "/" + env('POSTGRES_DB', 'hagiographies')
DB := "uv run --project db"

# Show which migrations are applied and which are pending
db_migrate_status:
    {{DB}} migrate --status

# Report what migrating would do, without changing anything
db_migrate_dry_run:
    {{DB}} migrate --dry-run

# Apply pending schema migrations
db_migrate:
    {{DB}} migrate

# Apply pending migrations to the local Docker Postgres
db_local_migrate:
    {{DB}} migrate --database-url "{{LOCAL_DB}}"

db_local_migrate_status:
    {{DB}} migrate --database-url "{{LOCAL_DB}}" --status

# Apply pending migrations to PRD
db_migrate_prd:
    {{DB}} migrate --database-url "$PG_DATABASE_URL_PRD"

db_migrate_prd_status:
    {{DB}} migrate --database-url "$PG_DATABASE_URL_PRD" --status

# ── IIIF manifest links (codex_link) ───────────────────────────────────────
# 'IIIF manifest' links are the source of truth; each has a derived
# 'IIIF viewer' link (https://theseusviewer.org/?iiif-content=<manifest>).
# Three targets per recipe: QAS (PG_DATABASE_URL), _prd, and db_local_ (Docker).
# Load .env first when direnv is not active: set -a; source .env; set +a
#
# After researchers edited links by hand in Mathesar:
#   just db_iiif_sync --dry-run      # what would change (no network)
#   just db_iiif_sync                # unpack/merge manifests, repair viewer pairs
#   just db_iiif_check --only unchecked   # check new or edited manifests
#
# Re-checking:
#   just db_iiif_check               # every manifest (~15 min; Gallica is paced at 10 s)
#   just db_iiif_check --only failed # retry everything that was not OK
#   just db_iiif_check --dry-run     # fetch and report, write nothing
#   just db_iiif_check --skip-host gallica.bnf.fr   # everything but Gallica (its copies come from a browser)
#
# Gallica refuses any non-browser client (403, from every network), so its
# manifests are noted as 'not verifiable automatically'; open them in a browser.
# To fetch from outside the UGent network, e.g. via kleemburg.be:
#   ssh -N -D 127.0.0.1:1080 kleemburg.be &        # SOCKS tunnel; kill it afterwards
#   just db_iiif_check --proxy socks5h://127.0.0.1:1080 --delay 10
# Only the HTTP requests use the tunnel; the database is still reached directly (VPN).
# The check runs the sync first (--no-sync skips it). Results land in
# codex_link_checked_at / codex_link_check_note; editing a link's URL clears
# them (migration 068). Filter on codex_link_check_note in Mathesar.

# Manifest cache: every manifest that checks out OK is stored in
# hagio_admin.iiif_manifest_cache (full JSON, label, canvas count; migration 069)
# and re-fetched conditionally (ETag/Last-Modified) on later checks.
# Manifests fetched in a browser (Gallica) are imported from an NDJSON file,
# one {"url","status","etag","last_modified","body"} object per line:
#   just db_iiif_cache_import ~/Downloads/gallica_manifests.ndjson [--dry-run]
# A Gallica 403 then counts as OK on later checks, backed by that browser copy.

# Import manifests fetched in a browser into the cache (NDJSON, see above)
db_iiif_cache_import FILE *ARGS:
    {{DB}} iiif-cache-import "{{FILE}}" {{ARGS}}

db_iiif_cache_import_prd FILE *ARGS:
    {{DB}} iiif-cache-import "{{FILE}}" --database-url "$PG_DATABASE_URL_PRD" {{ARGS}}

db_local_iiif_cache_import FILE *ARGS:
    {{DB}} iiif-cache-import "{{FILE}}" --database-url "{{LOCAL_DB}}" {{ARGS}}

# Repair the manifest/viewer link pairs (no network; --dry-run to only report)
db_iiif_sync *ARGS:
    {{DB}} iiif-sync {{ARGS}}

db_iiif_sync_prd *ARGS:
    {{DB}} iiif-sync --database-url "$PG_DATABASE_URL_PRD" {{ARGS}}

db_local_iiif_sync *ARGS:
    {{DB}} iiif-sync --database-url "{{LOCAL_DB}}" {{ARGS}}

# Options: --only all|unchecked|failed, --dry-run, --no-sync, --delay, --timeout
# Sync, then fetch the manifests (≤1 request/s per host) and record the results
db_iiif_check *ARGS:
    {{DB}} iiif-check {{ARGS}}

db_iiif_check_prd *ARGS:
    {{DB}} iiif-check --database-url "$PG_DATABASE_URL_PRD" {{ARGS}}

db_local_iiif_check *ARGS:
    {{DB}} iiif-check --database-url "{{LOCAL_DB}}" {{ARGS}}

# Overwrites the local research DB with a copy of whatever PG_DATABASE_URL
# points at (QAS), so migrations can be rehearsed locally.
# Requires PG_DATABASE_URL in the host environment (.env / direnv).
# A throwaway copy of the local database with ALL migrations applied, including
# the ones still pending sign-off. For trying out a migration, or running the
# file explorer, without touching the local DB Mathesar is pointed at.
#
# The whole database is copied, not just public. hagio_admin holds the migration
# history, and without it the runner would baseline 000 and then try to re-apply
# 001 onwards to a schema that already has them. Mathesar's mathesar_types holds
# the uri domain that the link tables' url columns are declared as, so without it
# those tables cannot even be created.

# Built from parts rather than by substituting into LOCAL_DB: the user and the
# database are both called "hagiographies", so a replace would rename both.
SCRATCH_DB := "postgresql://" + env('POSTGRES_USER', 'hagiographies') + ":" + env('POSTGRES_PASSWORD', 'changeme') + "@localhost:" + env('POSTGRES_PORT', '5432') + "/hagiographies_scratch"

# Rebuild hagiographies_scratch from the local DB and migrate it (LOCAL only)
db_scratch:
    pg_dump --no-owner --no-privileges -Fc "{{LOCAL_DB}}" -f data/local_clone.dump
    psql -q "{{LOCAL_DB}}" -c 'drop database if exists hagiographies_scratch;'
    psql -q "{{LOCAL_DB}}" -c 'create database hagiographies_scratch;'
    pg_restore --no-owner --no-privileges -d "{{SCRATCH_DB}}" data/local_clone.dump
    {{DB}} migrate --database-url "{{SCRATCH_DB}}"

# What the scratch database's migration state is
db_scratch_status:
    {{DB}} migrate --status --database-url "{{SCRATCH_DB}}"

# Drop the scratch database
db_scratch_drop:
    psql -q "{{LOCAL_DB}}" -c 'drop database if exists hagiographies_scratch;'

# Clone the remote DB into the local Docker Postgres (destructive, LOCAL only)
db_clone_qas:
    # public only: Mathesar's own __msar/msar/mathesar_types schemas already
    # exist locally and would make pg_restore fail on every object.
    pg_dump --no-owner --no-privileges --schema=public -Fc "$PG_DATABASE_URL" -f data/qas_clone.dump
    # the dump recreates the schema itself, so only drop it here
    psql -q "{{LOCAL_DB}}" -c 'drop schema if exists public cascade;'
    pg_restore --no-owner --no-privileges -d "{{LOCAL_DB}}" data/qas_clone.dump
    psql -qtA "{{LOCAL_DB}}" -c "select 'manuscript='||count(*) from manuscript" \
        -c "select 'edition='||count(*) from edition" -c "select 'text='||count(*) from text"

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

# ── File explorer ────────────────────────────────────────────────────────────

# The managed file explorer over the network share (file-explorer/). Runs on the
# HOST for dev, like the db_ recipes: it needs cargo and bun, and the share is a
# host path. Reads db/migrations/ 013 tables, so migrate before first run.

FILES := "FILES_DATABASE__URL=\"" + LOCAL_DB + "\""

# Run the file explorer backend on :3000 (builds the frontend first)
files_run:
    cd file-explorer && {{FILES}} cargo run

# Run the Vite dev server, proxying /api and /f to the backend on :3000
files_dev:
    cd file-explorer/frontend && bun run dev

# Run the file explorer tests
files_test:
    cd file-explorer && cargo test

# Typecheck the frontend
files_check:
    cd file-explorer/frontend && bun run check

# Build the file explorer tagged Docker image and save as a .tar.gz
files_build tag:
    cd file-explorer && podman build -t hagio-file-explorer:{{tag}} .
    podman tag localhost/hagio-file-explorer:{{tag}} localhost/hagio-file-explorer:latest
    podman save localhost/hagio-file-explorer:{{tag}} | gzip > hagio-file-explorer-{{tag}}.tar.gz

# Start the file explorer container on :9161
files_up:
    docker compose up -d file-explorer

# Follow the file explorer container logs
files_logs:
    docker compose logs -f file-explorer

# Re-scan the whole share and update the file table
files_rescan:
    curl -fsS -X POST http://localhost:9161/api/rescan

# ── Front end (front/: static browser over the SQLite export) ────────────────
# Runs on the HOST. No build step: front/index.html loads plain ES modules from
# front/app and the Pihka submodule (front/vendor/pihka). front_compose inlines
# everything into one file that ships next to the .sqlite on a data repository.
# Refresh the export first (db_clone_qas, then pg_export_sqlite) for a release.
FRONT_DB := "data/hagiographies_full_export.sqlite"

# Regenerate front/app/config.generated.js from the Mathesar label/display JSON
front_config:
    uv run --no-project python front/tools/gen_config.py

# Serve the decomposed front end on http://localhost:9162 (links the export in)
front_serve port="9162":
    git submodule update --init front/vendor/pihka
    mkdir -p front/app/database
    ln -sf "{{justfile_directory()}}/{{FRONT_DB}}" front/app/database/hagiographies.sqlite
    uv run --no-project python front/tools/serve.py --port {{port}}

# Compose front/dist/hagiographies.html (+ .sqlite, SHA256SUMS, README.txt); --release refuses TBD metadata
front_compose *args:
    uv run --no-project python front/tools/compose.py --db {{FRONT_DB}} {{args}}
