# Managed file explorer

A small web app over the network share that holds the scanned manuscripts and
editions. Job students use it to find, rename, move and upload files, and to copy
a working link for a file into `manuscript_link.url` or `edition_link.url` in
Mathesar, without having to mount the share.

Axum + sqlx on the back, Svelte 5 on the front, built into a static bundle that
is embedded in the binary. One binary, one container.

## Why the link is a UUID

Files and folders both get a row with a UUIDv4: `hagio_admin.file` and
`hagio_admin.directory`. A file is served at
`https://files.m-patch.ugent.be/f/<uuid>`; a folder link,
`https://files.m-patch.ugent.be/d/<uuid>`, redirects into the explorer showing that
folder. Renaming or moving either does not break a link already pasted into the
database, because the UUID never changes.

## Where things live is a relation, not a string

`directory` is a tree: `parent_id` points at the folder above, and the single row
with `parent_id IS NULL` is the share root. `file` says `directory_id` plus `name`.
Nothing stores a full path.

That is what makes a rename cheap. Renaming a folder is one `UPDATE` of one `name`;
moving it is one `UPDATE` of one `parent_id`. Nothing below it is touched, however
deep it goes. Paths are assembled on demand by two views,
`hagio_admin.directory_path` and `hagio_admin.file_path`, which are also what
search and the `/f/` handler read.

## Which database rows cite which file

One table per source link table: `hagio_admin.manuscript_link_reference` and
`hagio_admin.edition_link_reference`. Each has a real foreign key to its source row
and a real foreign key to whichever of `file` or `directory` the URL named, with a
CHECK that exactly one target is set. So "what cites this file?" and "which files
are unused?" are ordinary joins.

Both are filled in by a trigger on their link table that pulls the UUID out of the
url, so they stay right without anybody doing anything. Deleting a link row needs
no trigger branch at all: the foreign key cascades.

The triggers are `SECURITY DEFINER` because the researchers edit those columns as
`hagiographies_editor`, which has no access to `hagio_admin`. They never raise: a
link with an unknown UUID shows up in `hagio_admin.link_reference_unresolved`
instead of failing their edit.

The accepted hosts live in `hagio_admin.file_link_host`, since a trigger cannot
read `config.toml`. The app rewrites that table from its `link_hosts` setting on
every startup.

## Schema

The tables come from `db/migrations/`, applied with `just db_migrate` like every
other schema change: 013 created `file`, 014 added `directory` and the folder
links, 015 dropped the path column 014 replaced. There is no migration runner in
this app on purpose: `db/migrations/` is the only source of truth for this
database. The app refuses to start if `hagio_admin.file` is missing and tells you
what to run.

**014 and 015 are staged, and the order matters.** 014 is additive and leaves
`file.relative_path` in place, so the previously deployed binary keeps working
against it. Deploy the new image, then run 015, which drops the column. Doing 015
first would break every request the old binary handles. If 015 refuses because a
file has no `directory_id`, that is a row the old binary added in between: rescan
the share and run it again.

## Running it locally

```sh
just db_migrate          # once, to create the tables
mkdir -p data/share      # a scratch share to play with
just files_run           # backend on :3000, builds the frontend into the binary
just files_dev           # optional: Vite on :5173 with hot reload, proxying to :3000
```

`just files_run` passes the local Docker Postgres url. Everything else comes from
`file-explorer/config.toml`.

If you would rather not point it at the database Mathesar is using, `just
db_scratch` makes `hagiographies_scratch`: a copy of the local database with all
migrations applied, including ones still waiting on sign-off. Then run against it
with

```sh
FILES_DATABASE__URL=postgresql://hagiographies:changeme@localhost:5432/hagiographies_scratch \
  cargo run --manifest-path file-explorer/Cargo.toml
```

`just db_scratch_status` shows its migration state and `just db_scratch_drop`
removes it.

In Docker:

```sh
just files_build && just files_up   # http://localhost:9161
```

## Configuration

`config.toml`, then `FILES_*` environment variables on top. Nested keys use two
underscores, so `[database] url` is `FILES_DATABASE__URL`. Lists are TOML arrays
either way: `FILES_EXCLUDED_DIRS='["_admin","tmp"]'`.

| Key | Default | What it does |
| --- | --- | --- |
| `database.url` | required | Postgres url. A `postgresql+psycopg://` prefix is accepted and stripped, so the repo's `PG_DATABASE_URL` works as is. Never put this in the file, it has a password. |
| `share_root` | `/srv/share` | Root of the share. Resolved once at startup; the app will not start if it is missing. |
| `public_base_url` | required | Origin used to build the links students copy. |
| `link_hosts` | host of `public_base_url` | Hosts the database trigger recognises as ours. |
| `excluded_dirs` | empty | Top level folder names hidden from the interface. Never listed, navigated, scanned or tracked. |
| `bind_addr` | `0.0.0.0:3000` | |
| `max_upload_bytes` | 2 GiB | Axum's own default is 2 MB, which no real scan fits in. |
| `scan_on_startup` | `true` | Walk the whole share at startup to pick up files added over SMB. |

The deployed container mounts its `config.toml` rather than baking it in, so it
can be changed without a rebuild.

## Search

The box next to the title searches every tracked file on the share, not just the
folder you are in. Folders as well as files, since both are rows. It is fuzzy: the letters have to
appear in order but not together, so `kln6` finds `koln-6-plate.jpg`. Spaces are ignored, case does not
matter, and a match in the file name always outranks one that only matched in the
folder path. Each hit links straight to the file, and its folder is clickable.

Postgres does the first pass with an ILIKE built from the query letters, which is
a subsequence test; the survivors are scored and ranked in `routes/search.rs`. The
ILIKE runs against the assembled path rather than the name, because a query like
`scanskoln` is a subsequence that spans the folder/name boundary.

## Undo

Every operation that cannot lose data can be undone, from the button beside the
folder buttons. Renames and moves of files and folders are put back, keeping the
id so no pasted link breaks. Every entry records ids and old values, never paths,
so undoing a file move still works after somebody has renamed the folder it has to
go back into. A folder we created is removed, and an upload is
taken back.

Undo refuses rather than destroying anything it did not create:

- a folder that is no longer empty is left alone;
- an uploaded file that has changed since it arrived is left alone;
- an upload the database already links to is left alone, because removing the file
  would take the `file_reference` row with it.

A refusal keeps the operation on the stack, so nothing is silently lost.

The stack is per person, twenty deep, held in memory. Since the app has no login
of its own, "person" means whatever the proxy in front says (`x-forwarded-user`
and friends) or else a hash of the user agent, languages and client address. That
is a bucket, not an identity: two people on identical laptops behind one address
share a stack, which costs them nothing but a confusing tooltip. A restart forgets
everything.

## What students can and cannot do

Can: browse, search, rename files and folders at any level, move files and
folders, make folders, upload files and whole folders, copy a link, undo.

Cannot: delete anything, make a folder at the top level of the share, overwrite an
existing file, or reach outside the share. Names that Windows cannot open
(`CON`, trailing dots, `:`) are refused when creating or renaming, but files that
already have such a name are still listed and can be renamed to something better.

The top level of the share is fixed: those folders can be renamed but not moved,
nothing can be moved up to the top level, and no folder can be created there. A
folder also cannot be moved into itself or anything below it; the picker greys
out those rows rather than letting you find out afterwards.

## Keeping the table honest

A file is tracked whether or not it came through this app:

- a full walk at startup, in the background so a slow share does not hold up the
  server;
- `POST /api/rescan`, also `just files_rescan`;
- every directory listing adopts what it finds there.

Rows are never deleted. A file that disappears gets `missing_since` set and shows
up greyed out in the listing, because a link to it may already be in the database
and a broken link nobody can see is worse.

## Layout

```
src/paths.rs      path safety and naming rules, with the unit tests
src/fs_ops.rs     the filesystem side, no database
src/scan.rs       keeping hagio_admin.file in step with the share
src/tree.rs       the only place a path is turned into an id, or back
src/undo.rs       the per person undo stacks and how each step reverses
src/routes/       browse, files, dirs, search, serve, undo
frontend/         Svelte 5 + Vite + Tailwind, built with bun
```
