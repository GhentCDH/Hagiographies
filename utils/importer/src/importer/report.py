"""Validation reporting: collected row errors, console rendering, CSV export."""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass(frozen=True)
class RowError:
    """One rejected cell: where it is in the workbook and why it failed."""

    sheet: str
    excel_row: int
    column: str
    value: Any
    reason: str


@dataclass
class ImportReport:
    """Outcome of a validate or import run."""

    errors: list[RowError] = field(default_factory=list)
    imported: int = 0
    parsed: int = 0
    skipped_empty: list[int] = field(default_factory=list)

    @property
    def failed_rows(self) -> list[int]:
        """Distinct Excel row numbers that were rejected, in order."""
        return sorted({e.excel_row for e in self.errors})

    def render(self, console: Console, *, imported: bool) -> None:
        if self.errors:
            table = Table(title="Rejected rows (fix the workbook, not the importer)")
            table.add_column("Sheet")
            table.add_column("Excel row", justify="right")
            table.add_column("Column")
            table.add_column("Value")
            table.add_column("Reason")
            for e in sorted(self.errors, key=lambda e: (e.sheet, e.excel_row)):
                table.add_row(
                    e.sheet, str(e.excel_row), e.column, repr(e.value), e.reason
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
            + f", [bold red]{len(self.failed_rows)}[/bold red] rows rejected"
            + empty_note
        )

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sheet", "excel_row", "column", "value", "reason"])
            for e in sorted(self.errors, key=lambda e: (e.sheet, e.excel_row)):
                writer.writerow([e.sheet, e.excel_row, e.column, e.value, e.reason])
