"""Minimal client for the Mathesar JSON-RPC API.

Mathesar uses Django session auth, so the flow is:
  1. GET /auth/login/  -> obtain the csrftoken cookie + the form's csrfmiddlewaretoken
  2. POST /auth/login/  -> exchange credentials for a sessionid cookie
  3. POST /api/rpc/v0/  -> call methods, sending the session cookie + X-CSRFToken header

The API is documented at https://docs.mathesar.org/latest/api/ but the docs lag
behind the shipped image, so method signatures here are verified against the
running `mathesar/mathesar:latest` container.
"""

from __future__ import annotations

import re

import httpx


class MathesarError(RuntimeError):
    pass


class MathesarClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        # follow_redirects so the login 302 is consumed and cookies settle
        self._http = httpx.Client(base_url=self.base_url, follow_redirects=True, timeout=30.0)

    # ── lifecycle ────────────────────────────────────────────────────────────
    def __enter__(self) -> "MathesarClient":
        self.login()
        return self

    def __exit__(self, *_exc) -> None:
        self._http.close()

    # ── auth ─────────────────────────────────────────────────────────────────
    def login(self) -> None:
        login_url = f"{self.base_url}/auth/login/"
        page = self._http.get(login_url)
        match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
        if not match:
            raise MathesarError("Could not find CSRF token on the Mathesar login page")
        resp = self._http.post(
            login_url,
            data={
                "csrfmiddlewaretoken": match.group(1),
                "username": self._username,
                "password": self._password,
            },
            headers={"Referer": login_url},
        )
        if "sessionid" not in self._http.cookies:
            raise MathesarError(
                f"Mathesar login failed for user '{self._username}' (status {resp.status_code})"
            )

    # ── raw rpc ──────────────────────────────────────────────────────────────
    def rpc(self, method: str, params: dict):
        csrf = self._http.cookies.get("csrftoken", "")
        resp = self._http.post(
            "/api/rpc/v0/",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers={"X-CSRFToken": csrf, "Referer": f"{self.base_url}/"},
        )
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise MathesarError(f"{method} failed: {payload['error']['message']}")
        return payload.get("result")

    # ── typed helpers ────────────────────────────────────────────────────────
    def schema_oid(self, database_id: int, schema_name: str) -> int:
        # Resolved by name on every run: DROP SCHEMA public CASCADE + CREATE
        # SCHEMA public (importer drop-schema) assigns a new oid, so a stored
        # oid goes stale after every reimport.
        schemas = self.rpc("schemas.list", {"database_id": database_id})
        for schema in schemas:
            if schema["name"] == schema_name:
                return schema["oid"]
        raise MathesarError(
            f"schema '{schema_name}' not found in database {database_id}"
        )

    def list_tables(self, database_id: int, schema_oid: int) -> list[dict]:
        return self.rpc("tables.list", {"database_id": database_id, "schema_oid": schema_oid})

    def list_columns(self, database_id: int, table_oid: int) -> list[dict]:
        return self.rpc("columns.list", {"database_id": database_id, "table_oid": table_oid})

    def set_record_summary(self, database_id: int, table_oid: int, attnum: int) -> None:
        # record_summary_template is a list of column-attnum groups; a single
        # field is [[attnum]]. (Verified against the running image.)
        self.rpc(
            "tables.metadata.set",
            {
                "database_id": database_id,
                "table_oid": table_oid,
                "metadata": {"record_summary_template": [[attnum]]},
            },
        )

    def set_column_metadata(
        self, database_id: int, table_oid: int, blobs: list[dict]
    ) -> None:
        # Each blob is a ColumnMetaDataBlob: {"attnum": N, ...display keys...},
        # e.g. {"attnum": 5, "num_grouping": "never"} to disable the locale
        # thousands separator on an integer column.
        self.rpc(
            "columns.metadata.set",
            {
                "database_id": database_id,
                "table_oid": table_oid,
                "column_meta_data_list": blobs,
            },
        )
