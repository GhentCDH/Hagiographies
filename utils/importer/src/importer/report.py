"""Validation reporting: collected row errors, console/CSV/HTML export."""

import csv
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl.utils import get_column_letter
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
    # (sheet, column header) → Excel column letter ('AI'), registered by each
    # sheet parser from its header map so reports can point at the exact cell.
    column_letters: dict[tuple[str, str], str] = field(default_factory=dict)

    def register_columns(self, sheet: str, columns: dict[str, int]) -> None:
        """Record the Excel letter of each header (0-based index) of a sheet."""
        for header, index in columns.items():
            self.column_letters[(sheet, header)] = get_column_letter(index + 1)

    def _letter(self, e: RowError) -> str:
        """Excel column letter, or '' for composite (multi-column) labels."""
        return self.column_letters.get((e.sheet, e.column), "")

    def _ordered(self) -> list[RowError]:
        return sorted(
            self.errors,
            key=lambda e: (e.severity != "error", e.sheet, e.excel_row),
        )

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
            table.add_column("Col")
            table.add_column("Column")
            table.add_column("Value")
            table.add_column("Reason")
            for e in self._ordered():
                style = "red" if e.severity == "error" else "yellow"
                table.add_row(
                    f"[{style}]{e.severity}[/{style}]",
                    e.sheet, str(e.excel_row), self._letter(e), e.column,
                    repr(e.value), e.reason,
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
            writer.writerow(
                ["severity", "sheet", "excel_row", "excel_column", "column",
                 "value", "reason"]
            )
            for e in self._ordered():
                writer.writerow(
                    [e.severity, e.sheet, e.excel_row, self._letter(e),
                     e.column, e.value, e.reason]
                )

    def write_html(self, path: Path) -> None:
        """Interactive check-off list: one row per finding, a checkbox strikes
        it through, checked state persists in the browser's localStorage (keyed
        by the finding itself, so unchanged findings stay checked across runs).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for e in self._ordered():
            letter = self._letter(e)
            cell = f"{letter}{e.excel_row}" if letter else str(e.excel_row)
            key = "|".join(
                (e.severity, e.sheet, str(e.excel_row), e.column, e.reason)
            )
            rows.append(
                f'<tr class="{e.severity}" data-key="{html.escape(key, quote=True)}">'
                f'<td><input type="checkbox" aria-label="done"></td>'
                f"<td>{html.escape(e.severity)}</td>"
                f"<td>{html.escape(e.sheet)}</td>"
                f"<td class=cell>{html.escape(cell)}</td>"
                f"<td>{html.escape(e.column)}</td>"
                f"<td class=value>{html.escape(repr(e.value))}</td>"
                f"<td>{html.escape(e.reason)}</td></tr>"
            )
        summary = (
            f"{self.parsed} valid rows, {len(self.failed_rows)} rows rejected "
            f"(errors), {self.warning_count} warnings (unresolved links, "
            f"entity kept)"
        )
        path.write_text(
            _HTML_TEMPLATE.replace("__SUMMARY__", html.escape(summary))
            .replace("__ROWS__", "\n".join(rows)),
            encoding="utf-8",
        )


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Import report</title>
<style>
  body { font: 14px/1.45 system-ui, sans-serif; margin: 1.5rem; color: #1a1a1a; }
  h1 { font-size: 1.2rem; }
  .summary { color: #555; margin-bottom: 1rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: .3rem .6rem; text-align: left; vertical-align: top;
           border-bottom: 1px solid #e3e3e3; }
  th { position: sticky; top: 0; background: #fff; border-bottom: 2px solid #999; }
  tr.error > td:first-child { box-shadow: inset 3px 0 0 #c0392b; }
  tr.warning > td:first-child { box-shadow: inset 3px 0 0 #d9a400; }
  td.cell { font-family: ui-monospace, monospace; white-space: nowrap; }
  td.value { font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
  tr.done td { text-decoration: line-through; opacity: .45; }
  input[type=checkbox] { width: 1.05rem; height: 1.05rem; }
</style>
</head>
<body>
<h1>Validation report (fix the workbook, not the importer)</h1>
<p class="summary">__SUMMARY__ &mdash; <span id="counter"></span></p>
<table>
<thead><tr><th></th><th>Severity</th><th>Sheet</th><th>Cell</th><th>Column</th>
<th>Value</th><th>Reason</th></tr></thead>
<tbody>
__ROWS__
</tbody>
</table>
<script>
(function () {
  const STORE = "hagiographies-import-report";
  const rows = Array.from(document.querySelectorAll("tbody tr"));
  let checked;
  try { checked = new Set(JSON.parse(localStorage.getItem(STORE) || "[]")); }
  catch (e) { checked = new Set(); }
  const counter = document.getElementById("counter");
  function refresh() {
    const done = rows.filter(r => r.classList.contains("done")).length;
    counter.textContent = done + " / " + rows.length + " checked off";
  }
  rows.forEach(row => {
    const box = row.querySelector("input");
    if (checked.has(row.dataset.key)) { box.checked = true; row.classList.add("done"); }
    box.addEventListener("change", () => {
      row.classList.toggle("done", box.checked);
      if (box.checked) checked.add(row.dataset.key); else checked.delete(row.dataset.key);
      localStorage.setItem(STORE, JSON.stringify(Array.from(checked)));
      refresh();
    });
  });
  refresh();
})();
</script>
</body>
</html>
"""
