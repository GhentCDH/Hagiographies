"""Backfill the three workbook columns that never reached the database.

  MANUSCRIPTS!Q 'Manuscript shelfmark'              -> manuscript.shelfmark
  MANUSCRIPTS!R 'Folio or page range'               -> manuscript.folio_or_page_range
  EDITIONS!E 'Edition unique identifier (inc. vol)' -> publication + edition.publication_id

and normalises an existing column into a table of its own, without the workbook:

  manuscript.codex_identifier                       -> codex + manuscript.codex_id

The database has diverged from the workbook since the original import, so rows
are matched only on an exact, unambiguous identifier match — the same identifier
the importer built. Everything that cannot be matched is reported, never guessed.

Also reports, for the researchers, where the *database* contradicts itself about
a codex or a publication once the links exist — rows sharing a codex that
disagree on a codex-level column. Read back from the database rather than the
workbook, so conflicts already fixed in Mathesar do not resurface. Those
conflicts are what stops the remaining codex-level columns from being hoisted
onto the new tables.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import typer

from . import workbook as wb
from .conn import EXCEL, announce, connect, console, resolve_url
from .report import Report, summarise

MANUSCRIPTS = "MANUSCRIPTS"
EDITIONS = "EDITIONS"

PREFIX_COLUMN = "BHL or NO BHL"
COPY_ID_COLUMN = "Manuscript copy unique identifier per text"
SHELFMARK_COLUMN = "Manuscript shelfmark"
FOLIO_COLUMN = "Folio or page range"

TEXT_UID_COLUMN = "Unique identifier"
EDITION_ID_COLUMN = "Edition unique identifier per individual text"
PUBLICATION_COLUMN = "Edition unique identifier (inc. volume)"

VALID_PREFIXES = {"BHL", "NO BHL"}

# manuscript columns that describe the text copy rather than the codex, so they
# legitimately differ between copies bound in the same codex. Every other
# manuscript column is codex-level and is checked for conflicts.
COPY_LEVEL_DB_COLUMNS = {
    "manuscript_id",
    "identifier",
    "text_id",
    "folio_or_page_range",
    "codex_id",  # the grouping key
    "codex_identifier",  # the codex name, identical within a group by definition
    "codex_number",  # the codex name, identical within a group by definition
}

# edition columns that describe the published volume rather than the individual
# edition. The workbook's 'Edition number (inc. volume) in database' has no
# database column, so it cannot be checked here.
PUBLICATION_LEVEL_DB_COLUMNS = ["publication_year", "reference"]

app = typer.Typer(add_completion=False, help=__doc__)


def _columns_of(cur, table: str) -> list[str]:
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema = 'public' and table_name = %s order by ordinal_position",
        (table,),
    )
    return [name for (name,) in cur.fetchall()]


def _fk_labels(cur, table: str, columns) -> dict[str, dict[int, str]]:
    """For each FK column, a map of referenced id -> its human-readable name.

    Without this the conflict report would list bare integers, which nobody can
    act on. Lookup tables in this schema call that column 'name' or 'label'.
    """
    cur.execute(
        """
        select kcu.column_name, ccu.table_name, ccu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on kcu.constraint_name = tc.constraint_name
         and kcu.table_schema = tc.table_schema
        join information_schema.constraint_column_usage ccu
          on ccu.constraint_name = tc.constraint_name
         and ccu.table_schema = tc.table_schema
        where tc.constraint_type = 'FOREIGN KEY'
          and tc.table_schema = 'public'
          and tc.table_name = %s
        """,
        (table,),
    )
    references = {
        column: (ref_table, ref_pk)
        for column, ref_table, ref_pk in cur.fetchall()
        if column in columns
    }

    labels: dict[str, dict[int, str]] = {}
    for column, (ref_table, ref_pk) in references.items():
        available = _columns_of(cur, ref_table)
        display = next(
            (c for c in ("name", "label", "identifier") if c in available), None
        )
        if display is None:
            continue
        cur.execute(f"select {ref_pk}, {display} from {ref_table}")
        labels[column] = {key: value for key, value in cur.fetchall()}
    return labels


def _db_conflicts(
    cur,
    report: Report,
    section: str,
    *,
    table: str,
    pk: str,
    group_column: str,
    group_names: dict[int, str],
    columns: list[str],
) -> int:
    """Report rows sharing a group that disagree on a group-level column.

    Values come from the database, not the workbook, so anything the
    researchers have already fixed in Mathesar no longer shows up, and each
    competing value is listed with the primary keys of the rows holding it.
    """
    labels = _fk_labels(cur, table, columns)
    selected = ", ".join(columns)
    cur.execute(
        f"select {group_column}, {pk}, {selected} from {table} "
        f"where {group_column} is not null"
    )
    groups: dict[int, list[tuple]] = defaultdict(list)
    for row in cur.fetchall():
        groups[row[0]].append(row)

    total = 0
    for group_id in sorted(groups, key=lambda g: group_names.get(g, "")):
        rows = groups[group_id]
        if len(rows) < 2:
            continue
        for offset, column in enumerate(columns, start=2):
            seen: dict[str, list[int]] = defaultdict(list)
            for row in rows:
                value = row[offset]
                if value is None:
                    continue
                value = labels.get(column, {}).get(value, value)
                seen[str(value)].append(row[1])
            if len(seen) < 2:
                continue
            total += 1
            for value, keys in sorted(seen.items()):
                report.add(
                    section,
                    group_names.get(group_id, f"{group_column} {group_id}"),
                    column,
                    value,
                    ", ".join(str(key) for key in sorted(keys)),
                )
    return total


def _read_manuscripts(book, report: Report):
    ws = wb.sheet(book, MANUSCRIPTS)
    positions = wb.headers(ws)
    wb.require(positions, PREFIX_COLUMN, COPY_ID_COLUMN, SHELFMARK_COLUMN, FOLIO_COLUMN)

    entries: dict[str, dict] = {}
    for row in wb.rows(ws):
        prefix = wb.cell_exact(row, positions, PREFIX_COLUMN)
        copy_id = wb.cell_exact(row, positions, COPY_ID_COLUMN)
        if prefix not in VALID_PREFIXES or not copy_id:
            report.add(
                "unmatched_workbook",
                MANUSCRIPTS,
                row.number,
                "",
                "unusable identifier",
                f"prefix={prefix!r} copy id={copy_id!r}",
            )
            continue

        identifier = f"{prefix.replace(' ', '_')}_{copy_id}"
        if identifier in entries:
            report.add(
                "unmatched_workbook",
                MANUSCRIPTS,
                row.number,
                identifier,
                "duplicate in workbook",
                f"first seen on row {entries[identifier]['row']}",
            )
            continue
        entries[identifier] = {
            "row": row.number,
            "shelfmark": wb.cell(row, positions, SHELFMARK_COLUMN),
            "folio": wb.cell(row, positions, FOLIO_COLUMN),
        }

    return entries


def _read_editions(book, report: Report):
    ws = wb.sheet(book, EDITIONS)
    positions = wb.headers(ws)
    wb.require(positions, TEXT_UID_COLUMN, EDITION_ID_COLUMN, PUBLICATION_COLUMN)

    entries: list[dict] = []
    publication_names: set[str] = set()
    for row in wb.rows(ws):
        publication = wb.cell(row, positions, PUBLICATION_COLUMN)
        if publication:
            publication_names.add(publication)

        text_uid = wb.cell_exact(row, positions, TEXT_UID_COLUMN)
        edition_id = wb.cell_exact(row, positions, EDITION_ID_COLUMN)
        if not text_uid or not edition_id:
            report.add(
                "unmatched_workbook",
                EDITIONS,
                row.number,
                "",
                "unusable identifier",
                f"text={text_uid!r} edition={edition_id!r}",
            )
            continue
        entries.append(
            {
                "row": row.number,
                "text_uid": text_uid,
                "edition_id": edition_id,
                "publication": publication,
            }
        )

    return entries, sorted(publication_names)


# manuscript.codex_identifier normalised the same way workbook.norm() does:
# whitespace collapsed, trimmed, and the N/A spellings treated as no value.
_CODEX_NAME = r"btrim(regexp_replace(codex_identifier, '\s+', ' ', 'g'))"
_CODEX_HAS_NAME = (
    f"codex_identifier is not null and lower({_CODEX_NAME}) "
    "not in ('', 'n/a', 'na', '-')"
)


def _link_codex(cur, *, write: bool) -> tuple[int, int, int]:
    """Normalise manuscript.codex_identifier into the codex table and link it.

    Pure SQL: the workbook plays no part. The database column is the source of
    truth, so a codex the researchers renamed in Mathesar keeps their name, and
    the rows that have no workbook counterpart still get linked.

    Returns (codex rows, manuscripts linked, codex rows nothing references).
    """
    if write:
        cur.execute(
            f"insert into codex (name) select distinct {_CODEX_NAME} "
            f"from manuscript where {_CODEX_HAS_NAME} "
            "on conflict (name) do nothing"
        )
        cur.execute(
            "update manuscript m set codex_id = c.codex_id from codex c "
            f"where c.name = {_CODEX_NAME} and m.codex_id is distinct from c.codex_id"
        )

    cur.execute("select count(*) from codex")
    (total,) = cur.fetchone()
    cur.execute("select count(codex_id) from manuscript")
    (linked,) = cur.fetchone()
    cur.execute(
        "select count(*) from codex c where not exists "
        "(select 1 from manuscript m where m.codex_id = c.codex_id)"
    )
    (unused,) = cur.fetchone()
    return total, linked, unused


def _names_of(cur, table: str, pk: str) -> dict[int, str]:
    cur.execute(f"select {pk}, name from {table}")
    return dict(cur.fetchall())


def _insert_names(cur, table: str, pk: str, names, *, write: bool) -> dict[str, int]:
    if write and names:
        cur.executemany(
            f"insert into {table} (name) values (%s) on conflict (name) do nothing",
            [(name,) for name in names],
        )
    cur.execute(f"select name, {pk} from {table}")
    return dict(cur.fetchall())


def run(
    database_url: str | None,
    excel: Path | None,
    report_base: Path,
    *,
    write: bool,
    dry_run: bool = False,
) -> None:
    """Match workbook to database and write the report.

    write=False is the read-only mode: the connection is opened read-only, no
    codex/publication rows are created and nothing is updated. The report then
    describes the database as it stands — the conflicts come from the codex and
    publication links already there, so run the backfill first for it to say
    anything about them.
    """
    url = resolve_url(database_url)
    announce(url)
    path = excel or EXCEL
    if not path.exists():
        console.print(f"[red]error[/] workbook not found: {path}")
        raise typer.Exit(1)
    console.print(f"workbook: {path}")
    if not write:
        console.print("[green]read-only[/] — no data will be changed")

    report = Report()
    book = wb.load(path)
    manuscripts = _read_manuscripts(book, report)
    editions, publication_names = _read_editions(book, report)

    with connect(url, read_only=not write) as conn:
        cur = conn.cursor()

        # codex comes entirely from the database column; only publication and
        # the two text columns are taken from the workbook.
        codex_rows, codex_linked, codex_unused = _link_codex(cur, write=write)
        publication_ids = _insert_names(
            cur, "publication", "publication_id", publication_names, write=write
        )

        # --- manuscripts -------------------------------------------------
        cur.execute("select identifier, manuscript_id from manuscript")
        db_manuscripts = dict(cur.fetchall())

        updates = []
        for identifier, entry in manuscripts.items():
            manuscript_id = db_manuscripts.get(identifier)
            if manuscript_id is None:
                report.add(
                    "unmatched_workbook",
                    MANUSCRIPTS,
                    entry["row"],
                    identifier,
                    "no manuscript",
                    "no row in the database has this identifier",
                )
                continue
            updates.append((entry["shelfmark"], entry["folio"], manuscript_id))
        updated_manuscripts = len(updates)
        if updates and write:
            cur.executemany(
                "update manuscript set shelfmark = %s, folio_or_page_range = %s "
                "where manuscript_id = %s",
                updates,
            )

        for identifier, manuscript_id in sorted(db_manuscripts.items()):
            if identifier not in manuscripts:
                report.add(
                    "unmatched_database",
                    "manuscript",
                    manuscript_id,
                    identifier,
                    "no workbook row builds this identifier",
                )

        # --- editions ----------------------------------------------------
        cur.execute("select identifier, text_id from text")
        db_texts = dict(cur.fetchall())

        cur.execute("select text_id, identifier_per_text, edition_id from edition")
        db_editions: dict[tuple[int, str], list[int]] = defaultdict(list)
        for text_id, identifier_per_text, edition_id in cur.fetchall():
            db_editions[(text_id, identifier_per_text)].append(edition_id)

        updates = []
        matched_editions: set[int] = set()
        claims: dict[int, list[dict]] = defaultdict(list)
        for entry in editions:
            uid = entry["text_uid"]
            candidates = [
                (prefix, db_texts[f"{prefix}_{uid}"])
                for prefix in ("BHL", "NO_BHL")
                if f"{prefix}_{uid}" in db_texts
            ]
            if not candidates:
                report.add(
                    "unmatched_workbook",
                    EDITIONS,
                    entry["row"],
                    uid,
                    "no text",
                    f"neither BHL_{uid} nor NO_BHL_{uid} exists in text.identifier",
                )
                continue

            hits = []
            for prefix, text_id in candidates:
                key = (text_id, f"{prefix}_{entry['edition_id']}")
                hits.extend((key, eid) for eid in db_editions.get(key, ()))
            if not hits:
                report.add(
                    "unmatched_workbook",
                    EDITIONS,
                    entry["row"],
                    f"{candidates[0][0]}_{entry['edition_id']}",
                    "no edition",
                    "the text exists but has no edition with this identifier",
                )
                continue
            if len(hits) > 1:
                report.add(
                    "unmatched_workbook",
                    EDITIONS,
                    entry["row"],
                    f"{candidates[0][0]}_{entry['edition_id']}",
                    "ambiguous",
                    "matches edition ids " + ", ".join(str(e) for _, e in hits),
                )
                continue

            claims[hits[0][1]].append(entry)

        # Two workbook rows can resolve to the same database edition. Applying
        # both would silently let the last one win, so only act when they agree.
        for edition_id, entries_for_edition in claims.items():
            publications = {e["publication"] for e in entries_for_edition}
            rows_involved = ", ".join(str(e["row"]) for e in entries_for_edition)
            if len(entries_for_edition) > 1 and len(publications) > 1:
                report.add(
                    "unmatched_workbook",
                    EDITIONS,
                    rows_involved,
                    f"edition_id {edition_id}",
                    "contested",
                    "these rows resolve to the same edition but disagree on the "
                    "publication: " + ", ".join(sorted(map(str, publications))),
                )
                continue
            if len(entries_for_edition) > 1:
                report.add(
                    "unmatched_workbook",
                    EDITIONS,
                    rows_involved,
                    f"edition_id {edition_id}",
                    "duplicate target",
                    "these rows resolve to the same edition and agree; applied once",
                )
            matched_editions.add(edition_id)
            publication = entries_for_edition[0]["publication"]
            updates.append(
                (
                    publication_ids.get(publication) if publication else None,
                    edition_id,
                )
            )
        updated_editions = len(updates)
        if updates and write:
            cur.executemany(
                "update edition set publication_id = %s where edition_id = %s",
                updates,
            )

        for (text_id, identifier_per_text), edition_ids in sorted(
            db_editions.items(), key=lambda kv: kv[1]
        ):
            for edition_id in edition_ids:
                if edition_id not in matched_editions:
                    report.add(
                        "unmatched_database",
                        "edition",
                        edition_id,
                        identifier_per_text,
                        f"text_id {text_id}: no workbook row matched this edition",
                    )

        # --- conflicts, read back out of the database ----------------------
        # Run after the updates so the groups exist, and against the database
        # rather than the workbook so anything the researchers have already
        # corrected in Mathesar is not reported as still broken.
        codex_conflicts = _db_conflicts(
            cur,
            report,
            "codex_conflicts",
            table="manuscript",
            pk="manuscript_id",
            group_column="codex_id",
            group_names=_names_of(cur, "codex", "codex_id"),
            columns=[
                column
                for column in _columns_of(cur, "manuscript")
                if column not in COPY_LEVEL_DB_COLUMNS
            ],
        )
        publication_conflicts = _db_conflicts(
            cur,
            report,
            "publication_conflicts",
            table="edition",
            pk="edition_id",
            group_column="publication_id",
            group_names={v: k for k, v in publication_ids.items()},
            columns=PUBLICATION_LEVEL_DB_COLUMNS,
        )

        mode = (
            "read-only report (nothing changed)"
            if not write
            else "dry run (rolled back)"
            if dry_run
            else "applied"
        )
        verb = "matched" if not write else "updated"
        counts = report.counts()
        summarise(
            report,
            [
                ("database", url.split("@")[-1]),
                ("workbook", str(path)),
                ("mode", mode),
                ("codex rows in table", codex_rows),
                ("manuscripts linked to a codex", codex_linked),
                ("codex rows nothing references", codex_unused),
                ("publication rows in table", len(publication_ids)),
                ("publication names in workbook", len(publication_names)),
                (f"manuscripts {verb} (shelfmark/folio)", updated_manuscripts),
                ("manuscripts in workbook", len(manuscripts)),
                ("manuscripts in database", len(db_manuscripts)),
                (f"editions {verb}", updated_editions),
                ("editions in workbook", len(editions)),
                ("editions in database", sum(len(v) for v in db_editions.values())),
                ("unmatched workbook rows", counts["unmatched_workbook"]),
                ("unmatched database rows", counts["unmatched_database"]),
                ("codex conflicts (codex × column)", codex_conflicts),
                ("publication conflicts (publication × column)", publication_conflicts),
            ],
        )

        if write and not dry_run:
            conn.commit()
        else:
            conn.rollback()

    csv_path, html_path = report.write(report_base)

    console.print()
    console.print(
        f"manuscripts {verb} (shelfmark/folio): [bold]{updated_manuscripts}[/]"
    )
    console.print(f"editions {verb}:    [bold]{updated_editions}[/]")
    console.print(
        f"codex rows:          [bold]{codex_rows}[/] "
        f"({codex_linked} manuscripts linked, {codex_unused} unreferenced)"
    )
    console.print(f"publication rows:    [bold]{len(publication_ids)}[/]")
    console.print(f"codex conflicts:       {codex_conflicts}")
    console.print(f"publication conflicts: {publication_conflicts}")
    console.print(f"unmatched workbook rows: {counts['unmatched_workbook']}")
    console.print(f"unmatched database rows: {counts['unmatched_database']}")
    console.print(f"report: {csv_path} and {html_path}")
    if not write:
        console.print("[green]read-only — nothing was changed[/]")
    elif dry_run:
        console.print("[yellow]dry run — the database was rolled back[/]")


@app.command()
def backfill_command(
    database_url: str = typer.Option(
        None, "--database-url", help="Override DATABASE_URL / PG_DATABASE_URL."
    ),
    excel: Path = typer.Option(
        None, "--excel", help=f"Workbook to read (default {EXCEL})."
    ),
    report_base: Path = typer.Option(
        Path("/data/backfill_report"),
        "--report",
        help="Report path without extension; .csv and .html are written.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Roll back at the end; still writes the report."
    ),
) -> None:
    """Apply the backfill and write the report."""
    run(database_url, excel, report_base, write=True, dry_run=dry_run)


report_app = typer.Typer(add_completion=False)


@report_app.command()
def report_command(
    database_url: str = typer.Option(
        None, "--database-url", help="Override DATABASE_URL / PG_DATABASE_URL."
    ),
    excel: Path = typer.Option(
        None, "--excel", help=f"Workbook to read (default {EXCEL})."
    ),
    report_base: Path = typer.Option(
        Path("/data/backfill_report"),
        "--report",
        help="Report path without extension; .csv and .html are written.",
    ),
) -> None:
    """Write the report without touching the database.

    The connection is opened read-only, so PostgreSQL itself rejects any write.
    Conflicts are read from the codex and publication links already in the
    database, so run the backfill first if you want those sections populated.
    """
    run(database_url, excel, report_base, write=False)


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


def report_entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(report_app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
