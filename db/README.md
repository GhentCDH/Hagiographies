# db — schema migrations and backfills

Raw SQL against PostgreSQL. Deliberately independent of
`utils/utilities/src/utilities/model.py`: the SQLModel model is no longer kept
in sync with the database, and `db/migrations/` is the source of truth for the
schema.

```
migrations/            numbered .sql, applied in filename order, each in its own transaction
  000_init.sql         baseline: the schema as it stood on 2026-07-29 (frozen)
src/hagio_db/
  migrate.py           the migration runner
  backfill.py          the 2026-07 backfill: shelfmark, folio, codex, publication
  workbook.py          openpyxl access to the corpus workbook
  report.py            csv + html report
```

## Running

Through `just`. These recipes run on the **host**, not in the `utils`
container: the container cannot reliably resolve the UGent hostnames (or PyPI),
and sharing `db/.venv` through a bind mount makes host and container tear down
each other's environment. `PG_DATABASE_URL` comes from `.env` via direnv, the
same way `db_clone_qas` already gets it.

```sh
just db_migrate_status        # what is applied, what is pending
just db_migrate_dry_run
just db_migrate
just db_backfill_dry_run
just db_backfill
```

PRD, once the researchers have signed off:

```sh
just db_report_prd            # read-only, safe any time
just db_migrate_prd
just db_backfill_prd
```

Against the local Docker Postgres instead of whatever `PG_DATABASE_URL` points
at:

```sh
just db_clone_qas             # copy QAS into the local container (destructive, local only)
just db_local_migrate
just db_local_backfill
```

All commands take `--database-url` to target something else explicitly, which
is how PRD gets run once the researchers have signed off.

## Read-only reporting

`report` writes `data/backfill_report.{csv,html}` and changes nothing. It opens
the connection read-only, so PostgreSQL rejects any write rather than the script
merely rolling one back:

```sh
just db_report_local          # the local Docker Postgres
just db_report                # whatever PG_DATABASE_URL points at (QAS)
just db_report_prd            # PG_DATABASE_URL_PRD
```

or directly:

```sh
DATA_ROOT=data uv run --project db report --report data/backfill_report
```

The conflict sections read the codex and publication links that are already in
the database, so on a database where `db_backfill` has not run they are empty
(and the summary shows `codex rows in table: 0`). The unmatched-rows sections
work regardless.

`db_backfill --dry-run` is a different thing: it performs the writes and rolls
them back, so it reports the counts an actual run would produce.

## The baseline

`000_init.sql` is the schema as it already exists everywhere. The runner detects
that: if `public` already holds tables when `schema_migration` is first created,
000 is recorded as applied **without being executed**, and 001+ apply on top. On
an empty database 000 runs normally, so the whole schema can be built from this
directory alone. It is frozen — later changes are new numbered migrations.

## Mathesar changes the schema too

Mathesar edits the database directly, and setting a column's *type* in its UI is
a DDL change — usually to one of its own domains in the `mathesar_types` schema
(`uri`, `email`, `mathesar_money`, …). The runner tracks files, not schema
state, so it cannot see those changes: `db_migrate` will happily report "nothing
to apply" against a database that no longer matches `000_init.sql`.

When it happens, write a migration that reproduces it, as `004` does for
`manuscript_link.url`. Two rules for such a migration:

- **Guard both ends.** Skip if the change is already in place (the environment
  where Mathesar made it), and skip if `mathesar_types` does not exist (a
  database built from `db/migrations/` alone, before Mathesar has connected).
  A `DO $$ … $$` block with two `RETURN`s covers both.
- **Check the data first.** Mathesar creates its domain constraints `NOT VALID`,
  so the rows already present were never checked — but `ALTER COLUMN … TYPE`
  casts every row and the cast *does* enforce the constraint. Run the
  constraint's predicate as a `SELECT count(*)` before writing the migration.
- **Use Mathesar's own cast function, not a plain cast.** Setting a type in the
  UI runs `msar.retype_column`, which builds
  `ALTER TABLE … ALTER COLUMN … TYPE <type> USING msar.cast_to_<type>(col)`.
  Those functions do translate data, but only for values the domain rejects —
  `msar.cast_to_uri` tries the plain cast first and falls back to lowercasing
  and prefixing `http://` (keeping the result only if the TLD is in
  `msar.top_level_domains`). Calling the same function makes the migration
  identical to the UI by construction; a plain cast would instead abort on any
  value the domain rejects. Both `004` and `005` do this.

Note that `000_init.sql` covers the `public` schema only. `mathesar_types`,
`__msar` and `msar` belong to Mathesar and are created when it first connects,
so a from-scratch database has no domains available until then.

## Rules

- A migration is immutable once applied. The runner stores a checksum and
  refuses to continue if a file changed, reporting it as
  `CHANGED SINCE APPLIED`. Add a new migration instead.

  `004` was edited once, on 2026-07-30, to use `msar.cast_to_uri` instead of a
  plain cast — before PRD had ever run it, and while the only databases holding
  it (QAS and the local clone) were already in the exact end state it
  describes, so the edit could not hide unapplied work. The recorded checksum
  was updated by hand on both, after asserting that
  `manuscript_link.url` was already `mathesar_types.uri`. If that ever needs
  repeating, assert the end state first — a checksum bump on a database that
  has *not* reached it silently marks work as done.
- The backfill never invents a match. Rows are matched on the exact identifier
  the importer built; anything ambiguous or missing goes into
  `data/backfill_report.{csv,html}` instead.
- Only three things come from the workbook: `manuscript.shelfmark`,
  `manuscript.folio_or_page_range` and `edition.publication_id`. The codex link
  is pure SQL — `codex.name` is the distinct values of the existing
  `manuscript.codex_identifier` column — so a codex the researchers renamed in
  Mathesar keeps their name, and the rows with no workbook counterpart are
  linked too.
- The workbook wins on the columns it feeds. On a first run that is moot (they
  are created empty), but re-running after someone edits `shelfmark` or
  `folio_or_page_range` in Mathesar overwrites their edit. The codex link is
  unaffected, and no pre-existing column is ever written.
- `--dry-run` rolls back and still writes the report.
