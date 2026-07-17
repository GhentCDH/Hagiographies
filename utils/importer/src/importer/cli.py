"""Importer CLI: Excel workbook → PostgreSQL.

Metadata (schema/DDL) and data import are separate operations:

    importer validate                  parse + validate only, no DB writes
    importer create-schema             DDL only
    importer drop-schema [--yes]       drop + recreate the public schema
    importer import-data [--create-schema] [--report-file PATH]

The importer never fixes Excel data: any cell failing strict validation
causes its row to be skipped and reported with the Excel row number; valid
rows are still imported. Fix the workbook, never the importer.

Exit codes: 0 = clean; 1 = completed but at least one row was rejected;
2 = fatal (missing sheet/header, DB unreachable, refused drop).
"""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from sqlmodel import Session

from utilities.config import DATA_ROOT, EXCEL

from . import excel
from .report import ImportReport
from .schema import SchemaGuardError, create_schema, drop_public_schema
from .sheets import SHEET_MODULES

app = typer.Typer(help=__doc__, no_args_is_help=True)
console = Console()
log = logging.getLogger("importer")

DEFAULT_REPORT = DATA_ROOT / "import_report.csv"


@app.callback()
def configure(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False)],
    )


def _engine():
    """Create the engine lazily so validate works without a database."""
    from utilities.db import engine

    return engine


def _announce_database(engine) -> None:
    """Print the resolved DB target; .env can silently retarget a remote server."""
    url = engine.url
    if url.host == "postgres":  # the compose service name (dev.env default)
        console.print(
            f"database: {url.render_as_string(hide_password=True)} "
            "[green](local Docker)[/green]"
        )
    else:
        console.print(
            f"database: {url.render_as_string(hide_password=True)} "
            "[bold red](REMOTE)[/bold red]"
        )


def _parse_workbook(report: ImportReport) -> dict[str, list]:
    """Phase 1 for every registered sheet. Fatal workbook problems exit 2."""
    try:
        workbook = excel.load(EXCEL)
        # Parsed rows accumulate in registry order so later sheets can
        # resolve cross-sheet references (EDITIONS links to TEXTS and
        # MANUSCRIPTS) purely, without a database.
        parsed = {}
        for module in SHEET_MODULES:
            ws = excel.sheet(workbook, module.SHEET)
            parsed[module.SHEET] = module.parse_sheet(ws, report, parsed)
            log.info("sheet %s: %d valid rows", module.SHEET, len(parsed[module.SHEET]))
        return parsed
    except excel.WorkbookError as error:
        console.print(f"[bold red]fatal:[/bold red] {error}")
        raise typer.Exit(code=2)


def _finish(report: ImportReport, report_file: Path, *, imported: bool) -> None:
    """Render the report, write the CSV/HTML if needed, set the exit code."""
    report.render(console, imported=imported)
    if report.errors:
        report.write_csv(report_file)
        html_file = report_file.with_suffix(".html")
        report.write_html(html_file)
        console.print(
            f"rejected-rows report written to [bold]{report_file}[/bold] "
            f"and [bold]{html_file}[/bold]"
        )
        raise typer.Exit(code=1)


@app.command()
def validate(
    report_file: Path = typer.Option(DEFAULT_REPORT, help="CSV report of rejected rows."),
) -> None:
    """Read and validate the workbook; write nothing to the database."""
    report = ImportReport()
    _parse_workbook(report)
    _finish(report, report_file, imported=False)


@app.command("create-schema")
def create_schema_command() -> None:
    """Create the metadata schema (tables, constraints, comments); no data."""
    engine = _engine()
    _announce_database(engine)
    create_schema(engine)
    console.print("schema created")


@app.command("drop-schema")
def drop_schema_command(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Drop and recreate the public schema of the research database."""
    engine = _engine()
    _announce_database(engine)
    url = engine.url
    if not yes:
        typer.confirm(
            f"Drop schema 'public' of database {url.database!r} on {url.host!r}?",
            abort=True,
        )
    try:
        drop_public_schema(engine)
    except SchemaGuardError as error:
        console.print(f"[bold red]fatal:[/bold red] {error}")
        raise typer.Exit(code=2)
    console.print("public schema dropped and recreated")


@app.command("import-data")
def import_data(
    with_schema: bool = typer.Option(
        False, "--create-schema", help="Create the metadata schema before importing."
    ),
    report_file: Path = typer.Option(DEFAULT_REPORT, help="CSV report of rejected rows."),
) -> None:
    """Validate the workbook and import all valid rows."""
    engine = _engine()
    _announce_database(engine)

    report = ImportReport()
    parsed = _parse_workbook(report)

    if with_schema:
        create_schema(engine)
    with Session(engine) as session:
        for module in SHEET_MODULES:
            report.imported += module.import_rows(session, parsed[module.SHEET])
        session.commit()

    _finish(report, report_file, imported=True)


def main() -> None:  # kept for symmetry with the old entry point
    app()


if __name__ == "__main__":
    main()
