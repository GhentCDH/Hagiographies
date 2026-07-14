"""Per-sheet importers.

Each module exposes SHEET (the stripped sheet name), parse_sheet(ws, report)
and import_rows(session, rows). Future sheets (MANUSCRIPTS, EDITIONS) slot in
by adding a module here and listing it in SHEET_MODULES — the CLI iterates
over this registry.
"""

from . import editions, manuscripts, texts

SHEET_MODULES = [texts, manuscripts, editions]
