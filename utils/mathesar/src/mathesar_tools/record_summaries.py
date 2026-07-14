"""Apply single-field record summaries to Mathesar tables from a JSON config.

The config maps table name -> summary column name, e.g.

    {
        "place": "name",
        "manuscript": "shelfmark",
        "edition": "title"
    }

Table names and column names are resolved to oids/attnums on every run via the
RPC API, so the config keeps working after a drop + reimport (which assigns new
oids/attnums). Configure once; rerun any time.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .client import MathesarClient, MathesarError

DEFAULT_CONFIG = Path(__file__).parent / "record_summaries.json"


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def load_config(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise SystemExit(
            f"Config {path} must be a flat object of {{\"table\": \"summary_field\"}}"
        )
    return data


def apply_summaries(client: MathesarClient, database_id: int, schema_oid: int,
                    config: dict[str, str]) -> int:
    tables = {t["name"]: t["oid"] for t in client.list_tables(database_id, schema_oid)}
    failures = 0
    for table_name, field_name in config.items():
        oid = tables.get(table_name)
        if oid is None:
            print(f"  SKIP {table_name}: table not found in schema {schema_oid}")
            failures += 1
            continue
        columns = {c["name"]: c["id"] for c in client.list_columns(database_id, oid)}
        attnum = columns.get(field_name)
        if attnum is None:
            print(f"  SKIP {table_name}: column '{field_name}' not found")
            failures += 1
            continue
        try:
            client.set_record_summary(database_id, oid, attnum)
            print(f"  OK   {table_name} -> {field_name} (attnum {attnum})")
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

    print(f"Applying {len(config)} record summaries from {config_path}")
    with MathesarClient(base_url, username, password) as client:
        schema_oid = client.schema_oid(database_id, schema_name)
        print(f"  target: {base_url} db={database_id} schema={schema_name} (oid {schema_oid})")
        failures = apply_summaries(client, database_id, schema_oid, config)

    if failures:
        raise SystemExit(f"Completed with {failures} failure(s)")
    print("All record summaries applied.")


if __name__ == "__main__":
    main()
