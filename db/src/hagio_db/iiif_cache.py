"""The IIIF manifest cache (hagio_admin.iiif_manifest_cache, migration 069).

The IIIF check stores every manifest that checks out OK here. Manifests the
check cannot fetch (Gallica refuses non-browser clients) can be fetched in a
browser and imported with `iiif-cache-import FILE` (just db_iiif_cache_import):
FILE has one JSON object per line,

    {"url": ..., "status": 200, "etag": ..., "last_modified": ..., "body": "<manifest JSON text>"}

Each imported manifest is classified like the check does; an OK one is cached
(fetched_via 'browser') and the codex links to it get the check note
'OK (IIIF vN; fetched in a browser)'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg
import typer
from psycopg.types.json import Jsonb

from .conn import announce, connect, console, resolve_url

UPSERT = """
INSERT INTO hagio_admin.iiif_manifest_cache AS c
    (manifest_url, manifest, iiif_version, label, canvas_count, http_status,
     etag, last_modified, fetched_via, fetched_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (manifest_url) DO UPDATE SET
    manifest = EXCLUDED.manifest, iiif_version = EXCLUDED.iiif_version,
    label = EXCLUDED.label, canvas_count = EXCLUDED.canvas_count,
    http_status = EXCLUDED.http_status, etag = EXCLUDED.etag,
    last_modified = EXCLUDED.last_modified, fetched_via = EXCLUDED.fetched_via,
    fetched_at = now()
"""

VALIDATORS = """
SELECT manifest_url, etag, last_modified, iiif_version, fetched_via
  FROM hagio_admin.iiif_manifest_cache
"""


def iiif_version(data: dict) -> int | None:
    kind = data.get("type") or data.get("@type")
    ctx = data.get("@context")
    ctx = " ".join(c for c in ctx if isinstance(c, str)) if isinstance(ctx, list) else str(ctx or "")
    if kind == "Manifest" and "iiif.io/api/presentation/3" in ctx:
        return 3
    if kind == "sc:Manifest" and "iiif.io/api/presentation/2" in ctx:
        return 2
    return None


def label_text(label: object) -> str | None:
    """Flatten a v2 label (string, {@value}, list) or v3 language map to text."""
    if label is None:
        return None
    if isinstance(label, str):
        return label
    if isinstance(label, dict):
        if "@value" in label:
            return str(label["@value"])
        values = [v for vs in label.values() for v in (vs if isinstance(vs, list) else [vs])]
        return " | ".join(str(v) for v in values) or None
    if isinstance(label, list):
        parts = [label_text(x) for x in label]
        return " | ".join(p for p in parts if p) or None
    return str(label)


def canvas_count(data: dict, version: int | None) -> int | None:
    if version == 3:
        return sum(1 for i in data.get("items") or [] if isinstance(i, dict) and i.get("type") == "Canvas")
    if version == 2:
        return sum(len(s.get("canvases") or []) for s in data.get("sequences") or [] if isinstance(s, dict))
    return None


def store(cur: psycopg.Cursor, url: str, data: dict, *, status: int, etag: str | None,
          last_modified: str | None, via: str) -> None:
    """Upsert one manifest into the cache."""
    version = iiif_version(data)
    cur.execute(UPSERT, (url, Jsonb(data), version, label_text(data.get("label")),
                         canvas_count(data, version), status, etag, last_modified, via))


def validators(cur: psycopg.Cursor) -> dict[str, tuple]:
    """url -> (etag, last_modified, iiif_version, fetched_via) for every cached manifest."""
    cur.execute(VALIDATORS)
    return {row[0]: row[1:] for row in cur.fetchall()}


app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    file: Path = typer.Argument(..., exists=True, dir_okay=False, help="NDJSON file, one fetched manifest per line."),
    database_url: str = typer.Option(None, help="Database (default: DATABASE_URL / PG_DATABASE_URL)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse and report, write nothing."),
) -> None:
    url = resolve_url(database_url)
    announce(url)
    cached, refused = 0, []
    with connect(url) as conn, conn.cursor() as cur:
        for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            rec = json.loads(line)
            murl, status = rec["url"], int(rec.get("status") or 0)
            try:
                data = json.loads(rec.get("body") or "")
            except ValueError:
                data = None
            version = iiif_version(data) if isinstance(data, dict) else None
            if status != 200 or version is None:
                refused.append(f"line {n}: {murl} (HTTP {status}, {'IIIF v%s' % version if version else 'not a IIIF manifest'})")
                continue
            store(cur, murl, data, status=status, etag=rec.get("etag"),
                  last_modified=rec.get("last_modified"), via="browser")
            cur.execute(
                """UPDATE public.codex_link l SET codex_link_checked_at = now(), codex_link_check_note = %s
                     FROM public.codex_link_type t
                    WHERE t.codex_link_type_id = l.codex_link_type_id AND t.codex_link_type = 'IIIF manifest'
                      AND btrim(l.codex_link_url::text) = %s""",
                (f"OK (IIIF v{version}; fetched in a browser)", murl),
            )
            cached += 1
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    console.print(f"{cached} manifests cached" + (" (dry run, nothing written)" if dry_run else ""))
    for r in refused:
        console.print(f"[yellow]not cached[/] {r}", highlight=False)


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
