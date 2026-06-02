"""Register the research database connection in Mathesar via JSON-RPC.

Mathesar does not auto-register the research database on a fresh metadata DB, so
`databases.setup.connect_existing` must be called once after bootstrap. Idempotent:
if the connection already exists, Mathesar returns the existing one.
"""

from __future__ import annotations

import os

from .client import MathesarClient, MathesarError


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def main() -> None:
    base_url = _env("MATHESAR_URL", "http://mathesar:8000")
    username = _env("MATHESAR_USERNAME", "admin")
    password = _env("MATHESAR_PASSWORD", "admin")
    db_name = _env("POSTGRES_DB", "hagiographies")
    db_host = _env("POSTGRES_HOST", "postgres")
    db_port = int(_env("POSTGRES_PORT", "5432"))
    db_user = _env("POSTGRES_USER", "hagiographies")
    db_pass = _env("POSTGRES_PASSWORD", "changeme")

    print(f"Registering DB connection {db_user}@{db_host}:{db_port}/{db_name} in {base_url}")
    with MathesarClient(base_url, username, password) as client:
        try:
            result = client.rpc(
                "databases.setup.connect_existing",
                {
                    "host": db_host,
                    "port": db_port,
                    "database": db_name,
                    "role": db_user,
                    "password": db_pass,
                    "nickname": db_name,
                },
            )
        except MathesarError as exc:
            raise SystemExit(f"Connection setup failed: {exc}")
    db = result.get("database", {})
    print(f"Connected: database_id={db.get('id')} name={db.get('name')}")


if __name__ == "__main__":
    main()
