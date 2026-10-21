#!/usr/bin/env bash
# Clone the PRD database over the QAS database.
#
# .env holds two remote connection strings:
#   PG_DATABASE_URL      -> QAS  (target, gets overwritten)
#   PG_DATABASE_URL_PRD  -> PRD  (source)
#
# Both servers run PostgreSQL 14, but the host's psql/pg_dump is newer and
# not wire-compatible with a 14 server, so every pg_dump/pg_restore call runs
# inside a postgres:14 Docker image instead of on the host.
#
# QAS ends up an EXACT mirror of PRD. That needs a full drop of every
# non-system schema first: `pg_restore --clean` only drops what the dump
# mentions, so anything that exists on QAS but not on PRD — the codex,
# publication and schema_migration tables, for instance — would survive it.
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
: "${PG_DATABASE_URL_PRD:?PG_DATABASE_URL_PRD (prd) missing from .env}"

PG_IMAGE="docker.io/postgres:14-alpine"
DUMP_DIR="$(pwd)/data"
DUMP_FILE="/dump/prd_clone.dump"
BACKUP_FILE="/dump/qas_pre_clone.dump"

pg() {
    docker run --rm -i -v "${DUMP_DIR}:/dump" "${PG_IMAGE}" "$@"
}

echo "==> Source (PRD): ${PG_DATABASE_URL_PRD%%@*}@..."
echo "==> Target (QAS): ${PG_DATABASE_URL%%@*}@..."
echo
echo "QAS will be made an exact copy of PRD: every schema is dropped first, so"
echo "tables and columns that exist only on QAS are removed, not just the ones"
echo "PRD also has."
read -r -p "This will PERMANENTLY OVERWRITE the QAS database. Type 'yes' to continue: " confirm
if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 1
fi

echo "==> Backing up the current QAS to data/qas_pre_clone.dump..."
pg pg_dump --format=custom --no-owner --no-privileges \
    --dbname="${PG_DATABASE_URL}" --file="${BACKUP_FILE}"

echo "==> Dumping PRD (custom format, all schemas)..."
pg pg_dump --format=custom --no-owner --no-privileges \
    --dbname="${PG_DATABASE_URL_PRD}" --file="${DUMP_FILE}"

# pg_dump omits 'CREATE SCHEMA public' when public is the default schema, but
# emits it when it is not. Ask the dump rather than assume, so we recreate
# public only when the restore will not.
if pg pg_restore --list "${DUMP_FILE}" | grep -qE '^[0-9]+; [0-9]+ [0-9]+ SCHEMA - public'; then
    RECREATE_PUBLIC=""
else
    RECREATE_PUBLIC="create schema public;"
fi

echo "==> Dropping every non-system schema on QAS..."
pg psql --dbname="${PG_DATABASE_URL}" -v ON_ERROR_STOP=1 -q -f - <<SQL
do \$\$
declare
    victim text;
begin
    for victim in
        select nspname from pg_namespace
        where nspname not like 'pg\\_%' and nspname <> 'information_schema'
    loop
        raise notice 'dropping schema %', victim;
        execute format('drop schema %I cascade', victim);
    end loop;
end
\$\$;
${RECREATE_PUBLIC}
SQL

echo "==> Restoring PRD into the now-empty QAS..."
pg pg_restore --no-owner --no-privileges --exit-on-error \
    --dbname="${PG_DATABASE_URL}" "${DUMP_FILE}"

echo "==> Verifying QAS matches PRD..."
summary() {
    pg psql --dbname="$1" -qtAX -c "
        select (select count(*) from information_schema.tables
                where table_schema = 'public')
            || ' tables, '
            || (select count(*) from information_schema.columns
                where table_schema = 'public')
            || ' columns, '
            || (select count(*) from pg_namespace
                where nspname not like 'pg\_%' and nspname <> 'information_schema')
            || ' schemas'"
}
prd_summary="$(summary "${PG_DATABASE_URL_PRD}")"
qas_summary="$(summary "${PG_DATABASE_URL}")"
echo "    PRD: ${prd_summary}"
echo "    QAS: ${qas_summary}"
if [[ "${prd_summary}" != "${qas_summary}" ]]; then
    echo "error: QAS does not match PRD" >&2
    exit 1
fi

echo "==> Done. QAS mirrors PRD."
echo "    PRD dump:       data/prd_clone.dump"
echo "    QAS before this run: data/qas_pre_clone.dump"
