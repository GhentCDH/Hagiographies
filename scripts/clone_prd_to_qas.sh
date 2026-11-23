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
# Privileges are copied too (no --no-privileges): the researchers'
# hagiographies_editor role needs its grants from migrations 007/008 to use
# Mathesar, and a restore without them leaves QAS unusable for them. Roles are
# cluster-wide, so the script checks up front that every role PRD grants to
# exists on QAS, and afterwards that QAS's privileges equal PRD's.
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

# Every role named in an ACL in the database (schemas, tables, sequences,
# functions, default privileges), other than PUBLIC.
GRANTEE_ROLES="
select distinct r.rolname
  from (select nspacl as acl from pg_namespace
        union all select relacl from pg_class
        union all select proacl from pg_proc
        union all select defaclacl from pg_default_acl) a,
       aclexplode(a.acl) e
  join pg_roles r on r.oid = e.grantee
 order by 1"

# Every ACL outside the system schemas, one line per object. An explicit ACL
# that equals the default for functions (PUBLIC and the owner may execute) is
# written as '-', as a NULL ACL means the same.
ACLS="
with ns as (select oid, nspname from pg_namespace
             where nspname not like 'pg\_%' and nspname <> 'information_schema')
select 'schema ' || nspname || ' ' || coalesce(n.nspacl::text, '-')
  from pg_namespace n join ns using (oid, nspname)
union all
select 'rel ' || ns.nspname || '.' || c.relname || ' ' || coalesce(c.relacl::text, '-')
  from pg_class c join ns on ns.oid = c.relnamespace
union all
select 'func ' || p.oid::regprocedure || ' '
       || case when p.proacl is null
                 or p.proacl = array[makeaclitem(0, p.proowner, 'EXECUTE', false),
                                     makeaclitem(p.proowner, p.proowner, 'EXECUTE', false)]
               then '-' else p.proacl::text end
  from pg_proc p join ns on ns.oid = p.pronamespace
union all
select 'default ' || coalesce(ns.nspname, '*') || ' ' || d.defaclobjtype || ' ' || d.defaclacl::text
  from pg_default_acl d left join ns on ns.oid = d.defaclnamespace
 order by 1"

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
pg pg_dump --format=custom --no-owner \
    --dbname="${PG_DATABASE_URL}" --file="${BACKUP_FILE}"

echo "==> Dumping PRD (custom format, all schemas)..."
pg pg_dump --format=custom --no-owner \
    --dbname="${PG_DATABASE_URL_PRD}" --file="${DUMP_FILE}"

# pg_dump omits 'CREATE SCHEMA public' when public is the default schema, but
# emits it when it is not. Ask the dump rather than assume, so we recreate
# public only when the restore will not.
if pg pg_restore --list "${DUMP_FILE}" | grep -qE '^[0-9]+; [0-9]+ [0-9]+ SCHEMA - public'; then
    RECREATE_PUBLIC=""
else
    RECREATE_PUBLIC="create schema public;"
fi

echo "==> Checking that every role PRD grants to exists on QAS..."
prd_roles="$(pg psql --dbname="${PG_DATABASE_URL_PRD}" -qtAX -c "${GRANTEE_ROLES}")"
for role in ${prd_roles}; do
    exists="$(pg psql --dbname="${PG_DATABASE_URL}" -qtAX \
        -c "select count(*) from pg_roles where rolname = '${role}'")"
    if [[ "${exists}" != "1" ]]; then
        echo "error: role ${role} has privileges on PRD but does not exist on QAS;" >&2
        echo "       create it first (needs CREATEROLE). Nothing was changed." >&2
        exit 1
    fi
done

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
pg pg_restore --no-owner --exit-on-error \
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

echo "==> Verifying QAS privileges match PRD..."
if ! diff <(pg psql --dbname="${PG_DATABASE_URL_PRD}" -qtAX -c "${ACLS}") \
          <(pg psql --dbname="${PG_DATABASE_URL}" -qtAX -c "${ACLS}") >&2; then
    echo "error: QAS privileges differ from PRD (lines above: < PRD, > QAS)" >&2
    exit 1
fi

echo "==> Done. QAS mirrors PRD."
echo "    PRD dump:       data/prd_clone.dump"
echo "    QAS before this run: data/qas_pre_clone.dump"
