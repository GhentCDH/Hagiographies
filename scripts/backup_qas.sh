#!/usr/bin/env bash
# Backup the QAS database
#
# .env holds the remote connection strings:
#   PG_DATABASE_URL  -> QAS
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
    echo "error: .env not found in $(pwd)" >&2
    exit 1
fi

set -a
source .env
set +a

: "${PG_DATABASE_URL:?PG_DATABASE_URL (qas) missing from .env}"

PG_IMAGE="docker.io/postgres:14-alpine"
DUMP_DIR="$(pwd)/data"
FILE="qas_backup_$(date -Iseconds).dump"
DUMP_FILE="/dump/${FILE}"

echo "==> Source (QAS): ${PG_DATABASE_URL%%@*}@..."
echo

echo "==> Dumping QAS (custom format, all schemas)..."
docker run --rm \
    -v "${DUMP_DIR}:/dump" \
    "${PG_IMAGE}" \
    pg_dump --format=custom --no-owner --no-privileges \
    --dbname="${PG_DATABASE_URL}" \
    --file="${DUMP_FILE}"

echo "==> Done. QAS now backed up (saved to data/${FILE})."
