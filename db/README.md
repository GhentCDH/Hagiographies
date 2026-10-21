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
  backfill.py          RETIRED: the 2026-07 backfill, kept as a record
  workbook.py          RETIRED: openpyxl access to the corpus workbook
  report.py            RETIRED: csv + html report
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
```

PRD, once the researchers have signed off:

```sh
just db_migrate_prd
```

Against the local Docker Postgres instead of whatever `PG_DATABASE_URL` points
at:

```sh
just db_clone_qas             # copy QAS into the local container (destructive, local only)
just db_local_migrate
```

All commands take `--database-url` to target something else explicitly, which
is how PRD gets run once the researchers have signed off.

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
  `007` was edited the same way on 2026-07-31, when the bookkeeping table moved
  out of `public` and its unqualified `REVOKE … ON schema_migration` would
  otherwise have failed on a from-scratch build. Precondition asserted before
  re-recording: the editor role already could not write the table.
- The bookkeeping lives in the **`hagio_admin`** schema, not `public`, so
  `public` holds research data only and Mathesar shows the researchers their
  tables rather than ours. The runner creates that schema and relocates the
  table automatically on databases that predate the change; it cannot be a
  migration, because the runner reads the table before applying anything.
- Editors are never granted `USAGE` on `hagio_admin`, which makes it invisible
  to them rather than merely unreadable.

## The 2026-07 backfill (historical)

`backfill.py`, `report.py` and `workbook.py` record how `manuscript.shelfmark`,
`manuscript.folio_or_page_range`, `codex` and `publication` were first
populated from the corpus workbook. It ran once against QAS and PRD, the
researchers verified the result, and it has no console script or recipe any
more — migrations `011` and `012` dropped the columns it reads and writes, so
it cannot run and must not be resurrected. It is kept because it is the only
description of how the data got where it is.

How it worked, in short: rows were matched only on the exact identifier the
importer had built, never guessed, and everything unmatched went to
`data/backfill_report.{csv,html}`. Only `shelfmark`, `folio_or_page_range` and
`edition.publication_id` came from the workbook; the codex link was pure SQL
over `manuscript.codex_identifier`, so codices the researchers had renamed in
Mathesar kept their names and rows absent from the workbook were linked too.
