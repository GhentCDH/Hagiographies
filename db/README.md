# db — schema migrations

Raw SQL against PostgreSQL. `db/migrations/` is the source of truth for the
schema. `utils/utilities/src/utilities/model.py` (SQLModel, used for the schema
diagram) mirrors the `public` schema after all migrations, so a migration that
touches `public` must update `model.py` in the same change (then run
`just db_diagram`). The runner itself does not depend on the model.

```
migrations/            numbered .sql, applied in filename order, each in its own transaction
  000_init.sql         baseline: the schema as it stood on 2026-07-29 (frozen)
src/hagio_db/
  migrate.py           the migration runner
  conn.py              database URL resolution and connection
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

## Renaming tables and columns

Migrations 018–051 (October 2026) relabelled the whole `public` schema to the
naming rules in AGENTS.md: lowercase snake_case, table-prefixed content
columns, `<a>__<b>` many-to-many junctions. There is one migration per table
(019–049). Each renames the table, its columns, and the constraint/index/sequence
names derived from them, so a migration-built database and a `model.py`-built
one match name for name.

For any future rename, use the guarded helpers from `018` instead of a bare
`ALTER … RENAME`:

```sql
SELECT hagio_admin.rename_table('old', 'new');
SELECT hagio_admin.rename_column('table', 'old', 'new');
SELECT hagio_admin.rename_constraint('table', 'old', 'new');
SELECT hagio_admin.rename_index('old', 'new');
SELECT hagio_admin.rename_sequence('old', 'new');
```

They are no-ops when the rename already happened (e.g. by hand in Mathesar),
and they refuse when both names, or neither, exist.

Renames are not free when PL/pgSQL refers to a column by name: function bodies
are stored as text. The file-explorer triggers read
`manuscript_link.manuscript_link_url` and `edition_link.edition_link_url`, so
`050` renamed those columns and replaced the functions in one transaction. Do
the same for any column that a `hagio_admin` function reads.

## Uniqueness constraints and parked migrations

`051`–`059` add the uniqueness rules described in AGENTS.md ("Uniqueness").
Each one first lists the offending rows and refuses if there are any, so a
constraint is never forced onto bad data. The only data they change themselves
is lossless:
- `052` trims identifiers and deletes a codex that holds nothing but a duplicate
  name;
- `057`–`059` remove junction rows whose every value is also held by a twin.

A constraint that is blocked by production data waits in `migrations/pending/`.
The runner only globs `migrations/*.sql`, so those files are never applied. Once
the researchers have fixed the rows named in the file:
1. give it the next free number and move it up;
2. add the matching constraint to `model.py`;
3. run `just db_diagram`.

Don't add a failing migration to `migrations/` itself: the runner stops at the
first failure, which blocks every later migration.

## The 2026-07 backfill (historical)

A one-off backfill populated `manuscript.shelfmark`,
`manuscript.folio_or_page_range`, `codex` and `publication` from the corpus
workbook in July 2026 (the codex link itself was pure SQL over the then
`manuscript.codex_identifier`). Migrations `011`/`012` dropped the columns it
used; its code (`backfill.py`, `workbook.py`, `report.py`) was removed in
October 2026 and is in git history.
