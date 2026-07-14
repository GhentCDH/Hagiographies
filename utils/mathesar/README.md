# mathesar-tools

Configure Mathesar through its JSON-RPC API instead of the web UI.

## Record summaries

`mathesar-record-summaries` sets each table's **record summary** (the label shown
in foreign-key cells and record pickers) to a single column, driven by a JSON config:

```json
{
    "place": "name",
    "manuscript": "shelfmark",
    "edition": "title"
}
```

Schema, table and column names are resolved to oids/attnums on every run, so
the config survives a schema drop + reimport (`just pg_reimport`). Run it any
time after `just pg_import`.

### Run

```sh
just mathesar_summaries                 # uses the bundled record_summaries.json
```

Pass a different config path as the first argument to the script.

### Config (env)

- `MATHESAR_URL` (default `http://mathesar:8000` — the Docker service name)
- `MATHESAR_USERNAME` / `MATHESAR_PASSWORD` (default `admin` / `admin`)
- `MATHESAR_DATABASE_ID` (default `1`)
- `MATHESAR_SCHEMA` (default `public`; resolved to its oid on every run)
