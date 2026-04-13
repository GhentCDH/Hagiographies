# PostgreSQL Migration Guide

This document describes the transition from a SQLite-centric architecture to a PostgreSQL-primary workflow. 

## Current State: Dual-Database Support

The project currently supports both **SQLite** and **PostgreSQL**.
- **SQLite** is the default for local development and legacy imports.
- **PostgreSQL** is configured as the primary backend for the Kottster admin panel (data management).

## Future State: PostgreSQL as Primary

To move towards a setup where PostgreSQL is the "Source of Truth" and SQLite is purely an export artifact, follow these steps:

### 1. Unified Environment Configuration
Update your `.env` and `dev.env` to prioritize the PostgreSQL connection string. Ensure `PG_DATABASE_URL` is correctly set.

### 2. Workflow Refactor (via `justfile`)
To establish Postgres as the primary destination for imports, the following changes are recommended in the `justfile`:

- **Redefine `import`**: Point it to PostgreSQL by default.
  ```just
  import:
      docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/importer --rm utils uv run importer
  ```
- **Deprecate SQLite Import in `reinit`**:
  Instead of importing directly to SQLite, rely on the export pipeline:
  ```just
  # New reinit logic
  reinit: rebuild reset-db import export-from-pg-to-sqlite map-data
  ```

### 3. Source-Agnostic Export Scripts
The export scripts (`export_map.py` and `export_sqlite.py`) are designed to be **source-agnostic**. They use the `DATABASE_URL` environment variable to determine their source.

- To export from SQLite (default):
  `just export-map`
- To export from PostgreSQL:
  `just export-from-pg-to-sqlite` (sets `DATABASE_URL=$PG_DATABASE_URL`)

## Data Flow Diagram

```mermaid
graph TD
    Excel([hagiographies.xlsx]) --> Importer[importer]
    Importer -->|DATABASE_URL| PG[(PostgreSQL)]
    PG -->|export-from-pg-to-sqlite| Exporter[exporter]
    Exporter --> SQLite[(public_hagiographies.db)]
    SQLite --> MapLibre[local-map]
    PG --> Kottster[Kottster Admin]
```

## Production Deployment
In production, ensure the `postgres` service is backed by a persistent volume (`postgres-data`) and that all services reference the internal Docker network for connectivity.
