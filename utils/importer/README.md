# Hagiographies Importer

Typer CLI that reads the corpus workbook (`EXCEL_FILE` in `data/`), strictly
validates it, and populates PostgreSQL. Metadata (schema/DDL) and data import
are separate operations.

## Commands

Run inside the utils container (`docker compose run -w /app/importer --rm utils uv run importer …`),
or via the `just pg_*` recipes:

```
importer validate                        # parse + validate only, no DB writes
importer create-schema                   # DDL only (tables, constraints, column comments)
importer drop-schema [--yes]             # drop + recreate the public schema (destructive)
importer import-data [--create-schema] [--report-file PATH]
```

Exit codes: `0` = clean; `1` = completed but at least one row was rejected;
`2` = fatal (missing sheet/header, DB unreachable, refused drop).

## Validation policy

The importer **never fixes Excel data**. Any cell failing strict validation
(e.g. an integer expected but `'>7000'` present) causes that row to be
skipped and reported with its Excel row number; valid rows are still
imported. Rejected rows are printed as a table and written to
`data/import_report.csv`. Fix the workbook, never the importer.

## Layout

```
src/importer/
├── cli.py        # typer app, logging, exit codes
├── excel.py      # workbook access, header verification, row iteration
├── fields.py     # strict parsers (CellError) + FieldSpec declarations
├── report.py     # RowError / ImportReport, console table + CSV
├── schema.py     # create/drop schema (guarded against mathesar_django)
├── sheets/       # one module per worksheet (texts.py, manuscripts.py, editions.py)
└── legacy/       # PARKED pre-rewrite importer + IIIF tool (old schema only)
```

Each sheet module exposes `SHEET`, `parse_sheet(ws, report)` (pure, phase 1)
and `import_rows(session, rows)` (DB, phase 2); new worksheets are added by
creating a module and registering it in `sheets/__init__.py`.
