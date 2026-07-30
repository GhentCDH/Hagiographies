"""Apply the numbered SQL migrations in db/migrations/.

Each file runs once, in filename order, in its own transaction, and is recorded
in schema_migration with a checksum. Re-running is a no-op; editing an already
applied migration is an error.

000_init.sql is the baseline. On a database that already carries the schema it
is recorded as applied without being executed; on an empty one it is executed
like any other migration.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import typer
from rich.table import Table

from .conn import MIGRATIONS, announce, connect, console, resolve_url

BASELINE = "000"

SCHEMA_MIGRATION_DDL = """
create table if not exists schema_migration (
    version    text primary key,
    name       text not null,
    checksum   text not null,
    applied_at timestamptz not null default now(),
    baselined  boolean not null default false
)
"""

app = typer.Typer(add_completion=False, help=__doc__)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _migrations() -> list[tuple[str, str, Path]]:
    """(version, name, path) for every migration, in filename order."""
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise typer.BadParameter(f"no migrations found in {MIGRATIONS}")
    out = []
    for path in files:
        version, _, name = path.stem.partition("_")
        out.append((version, name or path.stem, path))
    return out


def _public_has_tables(cur) -> bool:
    cur.execute(
        "select exists (select 1 from information_schema.tables "
        "where table_schema = 'public' and table_name <> 'schema_migration')"
    )
    return bool(cur.fetchone()[0])


def _applied(cur) -> dict[str, str]:
    cur.execute("select version, checksum from schema_migration")
    return dict(cur.fetchall())


@app.command()
def main(
    database_url: str = typer.Option(
        None, "--database-url", help="Override DATABASE_URL / PG_DATABASE_URL."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would happen; change nothing."
    ),
    status: bool = typer.Option(
        False, "--status", help="Show applied and pending migrations, then exit."
    ),
) -> None:
    url = resolve_url(database_url)
    announce(url)

    migrations = _migrations()

    with connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_MIGRATION_DDL)
            applied = _applied(cur)
            preexisting = _public_has_tables(cur)
        if dry_run or status:
            conn.rollback()
        else:
            conn.commit()

        if status:
            table = Table("version", "name", "state")
            for version, name, path in migrations:
                checksum = _checksum(path.read_text())
                if version not in applied:
                    state = "[yellow]pending[/]"
                elif applied[version] != checksum:
                    state = "[red]CHANGED SINCE APPLIED[/]"
                else:
                    state = "[green]applied[/]"
                table.add_row(version, name, state)
            console.print(table)
            return

        # A fresh schema_migration table on a database that already holds the
        # schema means this database *is* the baseline.
        baseline_only = preexisting and BASELINE not in applied

        pending = []
        for version, name, path in migrations:
            body = path.read_text()
            checksum = _checksum(body)
            if version in applied:
                if applied[version] != checksum:
                    console.print(
                        f"[red]error[/] {version}_{name}.sql changed after it was "
                        f"applied (recorded {applied[version]}, now {checksum}). "
                        "Migrations are immutable — add a new one instead."
                    )
                    raise typer.Exit(1)
                continue
            pending.append((version, name, path, body, checksum))

        if not pending:
            console.print("nothing to apply")
            return

        for version, name, path, body, checksum in pending:
            record_only = version == BASELINE and baseline_only
            if dry_run:
                verb = (
                    "would record (baseline: schema already present, not executed)"
                    if record_only
                    else "would apply"
                )
                console.print(f"[yellow]{verb}[/] {version}_{name}")
                continue

            with conn.cursor() as cur:
                if not record_only:
                    cur.execute(body)
                cur.execute(
                    "insert into schema_migration (version, name, checksum, baselined) "
                    "values (%s, %s, %s, %s)",
                    (version, name, checksum, record_only),
                )
            conn.commit()
            done = "recorded as baseline" if record_only else "applied"
            console.print(f"[green]{done}[/] {version}_{name}")

        if dry_run:
            console.print("[yellow]dry run — nothing was changed[/]")


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
