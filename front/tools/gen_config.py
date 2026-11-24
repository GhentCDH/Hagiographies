"""Generate front/app/config.generated.js: Pihka `tables` display config.

Inputs:
  - data/hagiographies_full_export.sqlite, prepared in memory with the SQL in
    front/app/prepare.js (so derived columns get labels too);
  - utils/mathesar/src/mathesar_tools/record_summaries.json (table -> the
    column Mathesar shows as a record's label);
  - utils/mathesar/src/mathesar_tools/column_display.json (table -> column ->
    Mathesar display options; only "num_grouping" is mapped).

Output: `export default { tables: {...} }` plus `export const displayColumns`
(the Mathesar record-summary column per table). Hand-written settings live in
front/app/config.js, which merges over this file.

Pihka picks a referenced row's label itself (core/engine/data-store.js,
#loadFkOptions: a column named title/name/label/display_name/description,
else the first TEXT column). This script reports every table where that
choice differs from Mathesar's record summary.

Run: uv run --no-project python front/tools/gen_config.py [--db PATH]
Python 3.13, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATHESAR = ROOT / "utils/mathesar/src/mathesar_tools"
PREPARE_JS = ROOT / "front/app/prepare.js"
OUT = ROOT / "front/app/config.generated.js"
DEFAULT_DB = ROOT / "data/hagiographies_full_export.sqlite"

PIHKA_DISPLAY_NAMES = ("title", "name", "label", "display_name", "description")

# Words that read better spelled out or capitalised in labels.
WORDS = {
    "iiif": "IIIF",
    "url": "URL",
    "legendiers": "Légendiers",
    "reecriture": "Réécriture",
    "id": "ID",
}
# Derived helper columns from prepare.js that only exist for Pihka's
# benefit (FK label, map detection): hidden from tables and detail views.
HIDDEN_DERIVED = {"label", "latitude", "longitude"}


def read_prepare_sql() -> str:
    text = PREPARE_JS.read_text(encoding="utf-8")
    match = re.search(r"String\.raw`(.*?)`;", text, re.S)
    if not match:
        sys.exit(f"could not find PREPARE_SQL in {PREPARE_JS}")
    return match.group(1)


def words(name: str) -> str:
    parts = [p for p in name.replace("__", "_").split("_") if p]
    out = [WORDS.get(p, p) for p in parts]
    text = " ".join(out)
    return text[:1].upper() + text[1:] if text else name


def column_label(table: str, column: str, ref_table: str | None) -> str:
    name = column
    if ref_table and name.endswith("_id"):
        name = name[: -len("_id")]
    for prefix in (f"{table}_", ):
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
            break
    if name == table:  # a lookup's value column, e.g. text_form.text_form
        return words(table)
    return words(name)


def pihka_display_column(columns: list[dict]) -> str | None:
    for c in columns:
        if c["name"].lower() in PIHKA_DISPLAY_NAMES and not c["pk"]:
            return c["name"]
    for c in columns:
        if not c["pk"] and (c["type"] or "").upper() == "TEXT":
            return c["name"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if not args.db.exists():
        sys.exit(f"SQLite export not found: {args.db} (run `just pg_export_sqlite`)")

    summaries: dict[str, str] = json.loads((MATHESAR / "record_summaries.json").read_text())
    display: dict[str, dict[str, dict]] = json.loads((MATHESAR / "column_display.json").read_text())

    src = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db = sqlite3.connect(":memory:")
    src.backup(db)
    src.close()
    db.executescript(read_prepare_sql())

    tables_cfg: dict[str, dict] = {}
    mismatches: list[str] = []
    names = [r[0] for r in db.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for table in names:
        cols = [
            {"name": r[1], "type": r[2], "pk": r[5] > 0}
            for r in db.execute(f'PRAGMA table_info("{table}")')
        ]
        refs = {r[3]: r[2] for r in db.execute(f'PRAGMA foreign_key_list("{table}")')}
        columns: dict[str, dict] = {}
        for c in cols:
            name, ctype = c["name"], (c["type"] or "").upper()
            cfg: dict = {"label": "ID" if c["pk"] else column_label(table, name, refs.get(name))}
            if name in HIDDEN_DERIVED:
                cfg["hidden"] = True
            if name.endswith("_url"):
                cfg["type"] = "url"
            elif ctype == "TEXT" and (name.endswith("_note") or name.endswith("_reference")):
                cfg["type"] = "text"
                cfg["maxWords"] = 12
            opts = display.get(table, {}).get(name, {})
            if opts.get("num_grouping") == "never":
                cfg["type"] = "number"
                cfg["format"] = {"useGrouping": False}
            columns[name] = cfg
        tables_cfg[table] = {"label": words(table), "columns": columns}

        if table in summaries:
            if summaries[table] not in {c["name"] for c in cols}:
                mismatches.append(f"{table}: record summary column {summaries[table]!r} missing")
            else:
                chosen = pihka_display_column(cols)
                if chosen == "label":
                    print(f"  display column: {table}: 'label' (prepare.js) extends {summaries[table]!r}")
                elif chosen != summaries[table]:
                    mismatches.append(
                        f"{table}: Pihka labels references by {chosen!r}, Mathesar by {summaries[table]!r}")

    missing = sorted(set(summaries) - set(names))
    for t in missing:
        mismatches.append(f"{t}: in record_summaries.json but not in the export")

    header = (
        "// Generated by front/tools/gen_config.py from the SQLite export (prepared with\n"
        "// front/app/prepare.js) and utils/mathesar/.../{record_summaries,column_display}.json.\n"
        "// Do not edit; override in front/app/config.js.\n"
    )
    body = json.dumps({"tables": tables_cfg}, indent=4, ensure_ascii=False)
    summary = json.dumps({t: summaries[t] for t in sorted(summaries)}, indent=4, ensure_ascii=False)
    OUT.write_text(
        f"{header}\n/** Mathesar record-summary column per table. */\n"
        f"export const displayColumns = {summary};\n\n"
        f"export default {body};\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({len(tables_cfg)} tables)")
    for line in mismatches:
        print(f"  display column: {line}")


if __name__ == "__main__":
    main()
