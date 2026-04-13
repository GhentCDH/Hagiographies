# PostgreSQL Migration Roadmap

This document provides a detailed, step-by-step guide for transitioning the Hagiographies project from its current SQLite-centric architecture to a PostgreSQL-primary workflow.

## 1. Current Status: SQLite-Primary (Dual-Source)

Currently, the project is in a **Dual-Source** state where:
- **SQLite** is the primary "Source of Truth" for imports and the Kottster Admin panel.
- **PostgreSQL** is maintained as a side-by-side secondary database for future readiness.
- **Map Data**: Generated strictly from the SQLite database.

---

## 2. Transitioning to PostgreSQL-Primary

To establish PostgreSQL as the primary database, follow these four phases:

### Phase A: Unified Environment Configuration
Update the `.env` and `dev.env` files to swap the roles of the database strings:

1.  Set `DATABASE_URL` to point to the PostgreSQL connection string.
2.  Maintain `KOTTSTER_DATABASE_PATH` only as a reference for legacy/export purposes.

### Phase B: Justfile Refactoring
Update the `justfile` to make the PostgreSQL import the default lifecycle step:

1.  **Redefine `import`**:
    ```just
    import:
        docker compose run -e DATABASE_URL=$PG_DATABASE_URL -w /app/importer --rm utils uv run importer
    ```
2.  **Update `reinit`**: Remove the direct SQLite import and rely on the PG-to-SQLite pipeline:
    ```just
    reinit: rebuild reset-db import export-from-pg-to-sqlite map-data
    ```

### Phase C: Kottster Admin Migration
The Admin panel must be reconfigured to read from the PostgreSQL adapter:

1.  **Adapter Update**: Ensure `kottster/app/_server/data-sources/hagiographies/index.js` is using `KnexPgAdapter` and the correct environment variables.
2.  **Page Source Switch**: Every `page.json` file in `kottster/app/pages/` must have its `dataSource` updated from `hagiographies_db` to `hagiographies`.
    *   *Pro-tip*: Use a bulk replace command from the project root:
        ```bash
        sed -i '' 's/"dataSource": "hagiographies_db"/"dataSource": "hagiographies"/g' kottster/app/pages/*/page.json
        ```

### Phase D: Export-Only SQLite
Once Postgres is primary, SQLite becomes a derived artifact for the map:

1.  **Source Switch for Map**: Ensure `just export-map` is updated to use the Postgres engine (by passing the env var).
2.  **Public Dump**: Continue using `just export-from-pg-to-sqlite` to generate the filtered, public-facing research database.

---

## 3. Data Flow (Target Architecture)

```mermaid
graph TD
    Excel([hagiographies.xlsx]) --> Importer[importer]
    Importer -->|DATABASE_URL| PG[(PostgreSQL)]
    PG -->|export-from-pg-to-sqlite| Exporter[exporter]
    Exporter --> SQLite[(public_hagiographies.db)]
    SQLite --> MapLibre[local-map]
    PG --> Kottster[Kottster Admin]
```

---

## 4. DevOps & Production Operations

### Persistence
The PostgreSQL data is persisted via the `postgres-data` named volume. Ensure this volume is backed up regularly.

### Performance & Optimization
- **Triggers**: PostgreSQL uses an automated trigger to manage the `updated_at` column (defined in `utilities/model.py`). No manual logic is required in the admin panel.
- **Backups**: Use `pg_dump` within the container for snapshots:
    ```bash
    docker compose exec postgres pg_dump -U user_name db_name > backup.sql
    ```

### Connectivity
Always use the service name `postgres` as the hostname in connection strings when services are communicating within the Docker network.
