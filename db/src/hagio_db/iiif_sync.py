"""Keep the codices' IIIF manifest and IIIF viewer links in step.

The 'IIIF manifest' links are the source of truth; the 'IIIF viewer' links
(https://theseusviewer.org/?iiif-content=<manifest>) are derived from them.
After researchers edit links by hand in Mathesar, this repairs the pairs:

  1. a manifest wrapped in a viewer URL (…?iiif-content=<manifest>) is
     unpacked to the bare manifest URL, and same-codex duplicates that this
     creates are merged (lowest id kept, notes joined with ' | ');
  2. every manifest gets its Theseus viewer link on the same codex;
  3. a viewer link that is not the Theseus link of one of its codex's
     manifests is removed:
       * if it wraps a manifest the codex has (e.g. a pasted Mirador link),
         its note moves to that manifest's Theseus link;
       * if its manifest is not on the codex (the manifest was deleted or
         changed), it is removed when it has no note, and reported and kept
         when it has one.

No network access; one transaction; --dry-run rolls it back. Run it on its
own (just db_iiif_sync) or let the IIIF check run it first (just db_iiif_check).
"""

from __future__ import annotations

import sys

import psycopg
import typer

from .conn import announce, connect, console, resolve_url

THESEUS = "https://theseusviewer.org/?iiif-content="

# A query value that is itself an http(s) URL, possibly percent-encoded.
WRAPPED = r"[?&](iiif-content|manifest)=https?(:|%3A)"


def theseus_sql(expr: str) -> str:
    """SQL for the Theseus link of manifest `expr` (same encoding as 066)."""
    return (
        f"'{THESEUS}' || replace(replace(replace(replace(replace(replace(replace("
        f"{expr}, '%', '%25'), '&', '%26'), '?', '%3F'), '#', '%23'), "
        f"'=', '%3D'), '+', '%2B'), ' ', '%20')"
    )


def unwrap_sql(expr: str) -> str:
    """SQL for the manifest inside viewer URL `expr`, decoded; NULL if not wrapped."""
    value = (
        rf"regexp_replace(btrim({expr}), '^[^?]*\?(.*&)?(iiif-content|manifest)=', '', 'i')"
    )
    decoded = value
    for enc, dec in (("%3A", ":"), ("%2F", "/"), ("%3F", "?"), ("%3D", "="),
                     ("%26", "&"), ("%23", "#"), ("%2B", "+"), ("%20", " "), ("%25", "%")):
        decoded = f"replace({decoded}, '{enc}', '{dec}')"
    return f"CASE WHEN btrim({expr}) ~* '{WRAPPED}' THEN {decoded} END"


TYPES = """
SELECT (SELECT codex_link_type_id FROM public.codex_link_type WHERE codex_link_type = 'IIIF manifest'),
       (SELECT codex_link_type_id FROM public.codex_link_type WHERE codex_link_type = 'IIIF viewer')
"""

# 1. Unpack and merge the manifests.
MANIFESTS = f"""
CREATE TEMP TABLE sync_manifest ON COMMIT DROP AS
SELECT l.codex_link_id, l.codex_id, c.codex_unique_identifier AS codex,
       nullif(btrim(l.codex_link_note), '') AS note, l.codex_link_url::text AS old_url,
       coalesce({unwrap_sql('l.codex_link_url::text')}, btrim(l.codex_link_url::text)) AS new_url
  FROM public.codex_link l JOIN public.codex c USING (codex_id)
 WHERE l.codex_link_type_id = %(manifest)s;

CREATE TEMP TABLE sync_manifest_group ON COMMIT DROP AS
SELECT codex_id, new_url, min(codex_link_id) AS keep_id, count(*) AS n,
       string_agg(DISTINCT note, ' | ' ORDER BY note) AS notes
  FROM sync_manifest GROUP BY codex_id, new_url;
"""

MERGED = """
SELECT m.codex, m.old_url, g.new_url
  FROM sync_manifest m JOIN sync_manifest_group g USING (codex_id, new_url)
 WHERE m.codex_link_id <> g.keep_id ORDER BY 1, 2
"""

UNPACKED = """
SELECT m.codex, m.old_url, m.new_url
  FROM sync_manifest m JOIN sync_manifest_group g ON g.keep_id = m.codex_link_id
 WHERE m.old_url <> m.new_url ORDER BY 1, 2
"""

APPLY_MANIFESTS = """
DELETE FROM public.codex_link l
 USING sync_manifest m JOIN sync_manifest_group g USING (codex_id, new_url)
 WHERE l.codex_link_id = m.codex_link_id AND m.codex_link_id <> g.keep_id;

UPDATE public.codex_link l
   SET codex_link_url = g.new_url,
       codex_link_note = CASE WHEN g.n > 1 THEN g.notes ELSE l.codex_link_note END
  FROM sync_manifest_group g
 WHERE l.codex_link_id = g.keep_id
   AND (l.codex_link_url::text <> g.new_url
        OR (g.n > 1 AND l.codex_link_note IS DISTINCT FROM g.notes));
"""

# 2./3. The viewer links, against the manifests as they are now.
VIEWERS = f"""
CREATE TEMP TABLE sync_expected ON COMMIT DROP AS
SELECT DISTINCT l.codex_id, l.codex_link_url::text AS manifest,
       {theseus_sql('l.codex_link_url::text')} AS viewer_url
  FROM public.codex_link l WHERE l.codex_link_type_id = %(manifest)s;

CREATE TEMP TABLE sync_stray ON COMMIT DROP AS
SELECT v.codex_link_id, v.codex_id, c.codex_unique_identifier AS codex,
       v.codex_link_url::text AS url, nullif(btrim(v.codex_link_note), '') AS note,
       e.viewer_url AS replaced_by
  FROM public.codex_link v
  JOIN public.codex c USING (codex_id)
  LEFT JOIN sync_expected e
         ON e.codex_id = v.codex_id AND e.manifest = {unwrap_sql('v.codex_link_url::text')}
 WHERE v.codex_link_type_id = %(viewer)s
   AND NOT EXISTS (SELECT 1 FROM sync_expected x
                    WHERE x.codex_id = v.codex_id AND x.viewer_url = v.codex_link_url::text);
"""

MISSING = """
SELECT c.codex_unique_identifier, e.viewer_url
  FROM sync_expected e JOIN public.codex c USING (codex_id)
 WHERE NOT EXISTS (SELECT 1 FROM public.codex_link v
                    WHERE v.codex_id = e.codex_id AND v.codex_link_type_id = %(viewer)s
                      AND v.codex_link_url::text = e.viewer_url)
 ORDER BY 1, 2
"""

APPLY_VIEWERS = """
INSERT INTO public.codex_link (codex_id, codex_link_type_id, codex_link_url)
SELECT codex_id, %(viewer)s, viewer_url FROM sync_expected
ON CONFLICT (codex_id, codex_link_type_id, codex_link_url) DO NOTHING;

UPDATE public.codex_link v
   SET codex_link_note = concat_ws(' | ', nullif(btrim(v.codex_link_note), ''), s.notes)
  FROM (SELECT codex_id, replaced_by, string_agg(DISTINCT note, ' | ' ORDER BY note) AS notes
          FROM sync_stray WHERE replaced_by IS NOT NULL AND note IS NOT NULL
         GROUP BY 1, 2) s
 WHERE v.codex_id = s.codex_id AND v.codex_link_type_id = %(viewer)s
   AND v.codex_link_url::text = s.replaced_by
   AND position(s.notes IN coalesce(v.codex_link_note, '')) = 0;

DELETE FROM public.codex_link l USING sync_stray s
 WHERE l.codex_link_id = s.codex_link_id
   AND (s.replaced_by IS NOT NULL OR s.note IS NULL);
"""


def sync(conn: psycopg.Connection) -> int:
    """Bring the manifest/viewer pairs in step, inside the caller's transaction.

    Prints what it does and returns the number of changes (kept strays with a
    note are reported, not counted).
    """
    with conn.cursor() as cur:
        cur.execute(TYPES)
        manifest, viewer = cur.fetchone()
        if manifest is None or viewer is None:
            raise RuntimeError("codex_link_type 'IIIF manifest' or 'IIIF viewer' missing; run the migrations (066)")

        def run(sql: str) -> None:
            # The type ids are integers from the database, inlined rather than
            # bound: bound parameters rule out multi-statement SQL and would
            # make psycopg read the '%25'-style literals as placeholders.
            cur.execute(sql.replace("%(manifest)s", str(int(manifest)))
                           .replace("%(viewer)s", str(int(viewer))))

        run(MANIFESTS)
        run(MERGED)
        merged = cur.fetchall()
        run(UNPACKED)
        unpacked = cur.fetchall()
        run(APPLY_MANIFESTS)

        run(VIEWERS)
        run(MISSING)
        missing = cur.fetchall()
        run("SELECT codex, url, replaced_by, note FROM sync_stray ORDER BY codex, url")
        strays = cur.fetchall()
        run(APPLY_VIEWERS)

    def show(title: str, rows: list, fmt) -> None:
        if rows:
            console.print(f"[bold]{title}[/] ({len(rows)})")
            for row in rows:
                console.print("  " + fmt(row), highlight=False)

    show("manifest unpacked from a viewer URL", unpacked, lambda r: f"{r[0]}: {r[1]} → {r[2]}")
    show("duplicate manifest merged into its twin", merged, lambda r: f"{r[0]}: {r[1]}")
    show("viewer link added", missing, lambda r: f"{r[0]}: {r[1]}")
    replaced = [s for s in strays if s[2] is not None]
    orphans = [s for s in strays if s[2] is None and s[3] is None]
    kept = [s for s in strays if s[2] is None and s[3] is not None]
    show("viewer link replaced by the Theseus link of its manifest", replaced,
         lambda r: f"{r[0]}: {r[1]}" + (" (note moved)" if r[3] else ""))
    show("viewer link removed, its manifest is not on the codex", orphans, lambda r: f"{r[0]}: {r[1]}")
    if kept:
        console.print(f"[yellow]viewer link kept: its manifest is not on the codex, but it has a note; "
                      f"fix or delete it in Mathesar[/] ({len(kept)})")
        for r in kept:
            console.print(f"  {r[0]}: {r[1]} — {r[3]}", highlight=False)

    changes = len(unpacked) + len(merged) + len(missing) + len(replaced) + len(orphans)
    if not changes and not kept:
        console.print("manifest and viewer links are in sync")
    return changes


app = typer.Typer(add_completion=False, help=__doc__)


@app.command()
def main(
    database_url: str = typer.Option(
        None, help="Database to sync (default: DATABASE_URL / PG_DATABASE_URL)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would change, change nothing."
    ),
) -> None:
    url = resolve_url(database_url)
    announce(url)
    with connect(url) as conn:
        changes = sync(conn)
        if dry_run:
            conn.rollback()
            console.print("[yellow]dry run — nothing was changed[/]")
        else:
            conn.commit()
            console.print(f"[green]done[/]: {changes} changes")


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
