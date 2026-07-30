"""Backfill report: one CSV with a section column, one HTML with a table per
section. Mirrors the data/import_report.* convention the importer set."""

from __future__ import annotations

import csv
import html
from collections import Counter
from pathlib import Path
from typing import Iterable

# section -> (title, description, column headers)
SECTIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "summary": (
        "Summary",
        "What the run did.",
        ("metric", "value"),
    ),
    "unmatched_workbook": (
        "Workbook rows with no database row",
        "These workbook rows could not be matched to an existing database row, "
        "so their values were not backfilled. Almost always the identifier was "
        "edited on one side after the original import.",
        ("sheet", "excel_row", "identifier", "reason", "detail"),
    ),
    "unmatched_database": (
        "Database rows no workbook row maps to",
        "Rows that exist in the database but have no counterpart in the "
        "workbook, so nothing was written to them.",
        ("table", "pk", "identifier", "detail"),
    ),
    "codex_conflicts": (
        "Codex conflicts",
        "Manuscripts now linked to the same codex that disagree on a "
        "codex-level column. Values are read from the database after the "
        "backfill, so anything already corrected in Mathesar is not listed "
        "here. Each competing value is listed with the manuscript_id of every "
        "row holding it. These must be resolved before those columns can be "
        "moved onto the codex table.",
        ("codex", "column", "value", "manuscript_ids"),
    ),
    "publication_conflicts": (
        "Publication conflicts",
        "Editions now linked to the same publication that disagree on "
        "publication_year or reference. Read from the database, same as the "
        "codex conflicts above, and listed with the edition_id of every row "
        "holding each value. The workbook's 'Edition number (inc. volume) in "
        "database' has no database column and so cannot be checked.",
        ("publication", "column", "value", "edition_ids"),
    ),
}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, tuple]] = []

    def add(self, section: str, *values) -> None:
        expected = len(SECTIONS[section][2])
        if len(values) != expected:
            raise ValueError(
                f"section {section!r} takes {expected} values, got {len(values)}"
            )
        self.rows.append((section, tuple("" if v is None else str(v) for v in values)))

    def counts(self) -> Counter:
        return Counter(section for section, _ in self.rows)

    @staticmethod
    def _badge(section: str, body: list[tuple]) -> str:
        """Row count is misleading for the conflict sections: one conflict is
        printed as one row per competing value. Count the conflicts instead."""
        if not section.endswith("_conflicts"):
            return f"{len(body)} rows"
        if not body:
            return "0"
        conflicts = {(values[0], values[1]) for values in body}
        groups = {values[0] for values in body}
        subject = section.removesuffix("_conflicts")
        return (
            f"{len(conflicts)} conflicts across {len(groups)} {subject} entries "
            f"({len(body)} rows, one per competing value)"
        )

    def _by_section(self) -> dict[str, list[tuple]]:
        grouped: dict[str, list[tuple]] = {name: [] for name in SECTIONS}
        for section, values in self.rows:
            grouped[section].append(values)
        return grouped

    def write(self, base: Path) -> tuple[Path, Path]:
        base.parent.mkdir(parents=True, exist_ok=True)
        csv_path = base.with_suffix(".csv")
        html_path = base.with_suffix(".html")
        self._write_csv(csv_path)
        self._write_html(html_path)
        return csv_path, html_path

    def _write_csv(self, path: Path) -> None:
        widest = max(len(cols) for _, _, cols in SECTIONS.values())
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["section"] + [f"field_{i + 1}" for i in range(widest)])
            for section, values in self.rows:
                padded = list(values) + [""] * (widest - len(values))
                writer.writerow([section] + padded)

    def _write_html(self, path: Path) -> None:
        grouped = self._by_section()
        parts = [
            "<meta charset='utf-8'>",
            "<title>Hagiographies backfill report</title>",
            _STYLE,
            "<h1>Hagiographies backfill report</h1>",
            "<nav>"
            + " · ".join(
                f"<a href='#{name}'>{SECTIONS[name][0]}</a>" for name in SECTIONS
            )
            + "</nav>",
        ]
        for name, (title, description, columns) in SECTIONS.items():
            body = grouped[name]
            badge = html.escape(self._badge(name, body))
            parts.append(f"<h2 id='{name}'>{html.escape(title)} <small>{badge}</small></h2>")
            parts.append(f"<p class='desc'>{html.escape(description)}</p>")
            if not body:
                parts.append("<p class='empty'>Nothing to report.</p>")
                continue
            head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
            rows = "".join(
                "<tr>" + "".join(f"<td>{html.escape(v)}</td>" for v in values) + "</tr>"
                for values in body
            )
            parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>")
        path.write_text("\n".join(parts), encoding="utf-8")


def summarise(report: Report, pairs: Iterable[tuple[str, object]]) -> None:
    for metric, value in pairs:
        report.add("summary", metric, value)


_STYLE = """<style>
:root { color-scheme: light dark; }
body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; }
h1 { margin-bottom: .25rem; }
h2 { margin-top: 2.5rem; border-bottom: 2px solid currentColor; padding-bottom: .25rem; }
h2 small { font-weight: normal; opacity: .6; }
nav { margin: 1rem 0 2rem; opacity: .8; }
p.desc { opacity: .75; max-width: 60ch; }
p.empty { opacity: .5; font-style: italic; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid rgba(128,128,128,.35); padding: .3rem .5rem; text-align: left; vertical-align: top; }
th { position: sticky; top: 0; background: Canvas; }
tbody tr:nth-child(even) { background: rgba(128,128,128,.08); }
</style>"""
