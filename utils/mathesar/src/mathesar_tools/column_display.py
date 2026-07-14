"""Apply per-column display metadata to Mathesar from a JSON config.

The config maps table name -> column name -> ColumnMetaDataBlob fields, e.g.

    {
        "text": {
            "dating_range_start": {"num_grouping": "never"}
        }
    }

Used to disable the locale thousands separator on year/identifier integer
columns (Mathesar would otherwise render 1000 as "1.000").

Table and column names are resolved to oids/attnums on every run via the RPC
API, so the config keeps working after a drop + reimport. Configure once;
rerun any time.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .client import MathesarClient, MathesarError

DEFAULT_CONFIG = Path(__file__).parent / "column_display.json"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def load_config(path: Path) -> dict[str, dict[str, dict]]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not all(
        isinstance(cols, dict) and all(isinstance(m, dict) for m in cols.values())
        for cols in data.values()
    ):
        raise SystemExit(
            f"Config {path} must be {{\"table\": {{\"column\": {{...metadata...}}}}}}"
        )
    return data


def apply_column_display(client: MathesarClient, database_id: int, schema_oid: int,
                         config: dict[str, dict[str, dict]]) -> int:
    tables = {t["name"]: t["oid"] for t in client.list_tables(database_id, schema_oid)}
    failures = 0
    for table_name, col_config in config.items():
        oid = tables.get(table_name)
        if oid is None:
            print(f"  SKIP {table_name}: table not found in schema {schema_oid}")
            failures += 1
            continue
        columns = {c["name"]: c["id"] for c in client.list_columns(database_id, oid)}
        blobs = []
        for col_name, metadata in col_config.items():
            attnum = columns.get(col_name)
            if attnum is None:
                print(f"  SKIP {table_name}.{col_name}: column not found")
                failures += 1
                continue
            blobs.append({"attnum": attnum, **metadata})
        if not blobs:
            continue
        try:
            client.set_column_metadata(database_id, oid, blobs)
            for blob in blobs:
                print(f"  OK   {table_name} attnum {blob['attnum']}: "
                      f"{ {k: v for k, v in blob.items() if k != 'attnum'} }")
        except MathesarError as exc:
            print(f"  FAIL {table_name}: {exc}")
            failures += 1
    return failures


def main() -> None:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG
    config = load_config(config_path)

    base_url = _env("MATHESAR_URL", "http://mathesar:8000")
    username = _env("MATHESAR_USERNAME", "admin")
    password = _env("MATHESAR_PASSWORD", "admin")
    database_id = int(_env("MATHESAR_DATABASE_ID", "1"))
    schema_name = _env("MATHESAR_SCHEMA", "public")

    print(f"Applying column display metadata from {config_path}")
    with MathesarClient(base_url, username, password) as client:
        schema_oid = client.schema_oid(database_id, schema_name)
        print(f"  target: {base_url} db={database_id} schema={schema_name} (oid {schema_oid})")
        failures = apply_column_display(client, database_id, schema_oid, config)

    if failures:
        raise SystemExit(f"Completed with {failures} failure(s)")
    print("All column display metadata applied.")


if __name__ == "__main__":
    main()
