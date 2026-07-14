# PostgreSQL Architecture

This document describes the PostgreSQL-primary architecture of the Hagiographies project.

## 1. Current Status: PostgreSQL-Primary

- **PostgreSQL** is the single "Source of Truth": the importer and SQLModel data model target it.
- **Mathesar** is the admin UI, editing PostgreSQL directly (no separate admin database adapter to configure).

---

## 2. Lifecycle Commands

- **Import**: `just pg_import` loads the Excel workbook into PostgreSQL.
- **SQLite export**: `just pg_export_sqlite` dumps PostgreSQL to `data/hagiographies_full_export.sqlite` via Dataflow.
- **Full reset**: `just reinit` runs pg_reset → container_rebuild → pg_import → Mathesar bootstrap → summaries (local Docker only).

### Local vs remote database

The Python recipes (`pg_import`, `iiif_check`, `iiif_fix`) connect to whatever
`PG_DATABASE_URL` resolves to inside the `utils` container:

- **Local Docker Postgres** (default): `dev.env` defines
  `PG_DATABASE_URL=…@postgres:5432/…` (the in-network `postgres` service).
- **Remote server**: create a local, gitignored `.env` with a remote
  `PG_DATABASE_URL=…@your-host:5432/…`. Docker Compose layers `.env` on top of
  `dev.env` for the `utils` container (`compose.yml`), so it overrides the local
  value. `utils/utilities/src/utilities/config.py` reads `DATABASE_URL` or
  `PG_DATABASE_URL`, so no explicit `-e` flag is needed.

`pg_reset` and `reinit` recreate the `postgres-data` volume and `exec` `psql`
inside the local `postgres` container, so they only apply to the **local Docker**
database. When pointing at a remote DB, run `pg_import`/`iiif_*` directly and do
not use `pg_reset`/`reinit`.

---

## 3. Data Flow

```mermaid
graph TD
    Excel([hagiographies.xlsx]) --> Importer[importer]
    Importer -->|DATABASE_URL| PG[(PostgreSQL)]
    PG -->|Dataflow| SQLite[(data/hagiographies_full_export.sqlite)]
    PG --> Mathesar[Mathesar Admin]
```

---

## 4. DevOps & Production Operations

### Persistence
The PostgreSQL data is persisted via the `postgres-data` named volume. Ensure this volume is backed up regularly.

### Performance & Optimization
- **Backups**: Use `pg_dump` within the container for snapshots:
    ```bash
    docker compose exec postgres pg_dump -U user_name db_name > backup.sql
    ```

### Connectivity
Always use the service name `postgres` as the hostname in connection strings when services are communicating within the Docker network.
