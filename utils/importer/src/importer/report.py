"""Validation reporting: collected row errors, console rendering, CSV export."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass(frozen=True)
class RowError:
    """One reported cell: where it is in the workbook and what is wrong.

    severity 'error': validation failed, the entity cannot be imported (the
    row is rejected). severity 'warning': a linked reference was not found —
    the entity itself is still imported, only the link is skipped.
    """

    sheet: str
    excel_row: int
    column: str
    value: Any
    reason: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ImportReport:
    """Outcome of a validate or import run."""

    errors: list[RowError] = field(default_factory=list)
    imported: int = 0
    parsed: int = 0
    skipped_empty: list[int] = field(default_factory=list)

    @property
    def failed_rows(self) -> list[int]:
        """Distinct Excel row numbers that were rejected (errors only)."""
        return sorted({e.excel_row for e in self.errors if e.severity == "error"})

    @property
    def warning_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == "warning")

    def render(self, console: Console, *, imported: bool) -> None:
        if self.errors:
            table = Table(title="Validation report (fix the workbook, not the importer)")
            table.add_column("Severity")
            table.add_column("Sheet")
            table.add_column("Excel row", justify="right")
            table.add_column("Column")
            table.add_column("Value")
            table.add_column("Reason")
            ordered = sorted(
                self.errors,
                key=lambda e: (e.severity != "error", e.sheet, e.excel_row),
            )
            for e in ordered:
                style = "red" if e.severity == "error" else "yellow"
                table.add_row(
                    f"[{style}]{e.severity}[/{style}]",
                    e.sheet, str(e.excel_row), e.column, repr(e.value), e.reason,
                )
            console.print(table)

        if self.skipped_empty:
            # The MANUSCRIPTS sheet's used range runs to Excel's row limit, so
            # there can be ~1M empty rows — never enumerate more than a few.
            rows = self.skipped_empty
            shown = ", ".join(map(str, rows[:10])) + (", …" if len(rows) > 10 else "")
            empty_note = f", {len(rows)} empty rows skipped (Excel rows {shown})"
        else:
            empty_note = ""
        console.print(
            f"[bold]{self.parsed}[/bold] valid rows"
            + (f", [bold]{self.imported}[/bold] imported" if imported else "")
            + f", [bold red]{len(self.failed_rows)}[/bold red] rows rejected (errors)"
            + f", [bold yellow]{self.warning_count}[/bold yellow] warnings "
            f"(unresolved links, entity kept)"
            + empty_note
        )

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["severity", "sheet", "excel_row", "column", "value", "reason"])
            for e in sorted(
                self.errors,
                key=lambda e: (e.severity != "error", e.sheet, e.excel_row),
            ):
                writer.writerow(
                    [e.severity, e.sheet, e.excel_row, e.column, e.value, e.reason]
                )
