-- 007: hagiographies_editor may read and write all data, but never the schema.
--
-- The researchers' role. It already exists on both servers as a LOGIN role
-- with CONNECT on the database and nothing else — it cannot currently read a
-- single row. This migration gives it full DML and stops there.
--
-- The guarantee that it cannot change the schema does NOT come from a revoke:
-- it comes from ownership. Every table in public is owned by the role running
-- the migrations (hagiographies_admin on the servers), and PostgreSQL only
-- lets the owner ALTER, DROP or RENAME a table. There is no grantable
-- privilege that confers DDL on an existing table, so an editor cannot change
-- a column type, rename a table or drop anything, no matter what it is
-- granted. The REVOKEs below only close the remaining door — creating *new*
-- objects — and are belt and braces, since neither privilege is held today.
--
-- This also means Mathesar's schema-editing UI stops working for editors:
-- msar.retype_column and friends are all SECURITY INVOKER (verified: 0 of the
-- 496 functions in msar/__msar are SECURITY DEFINER), so they run the ALTER as
-- the connected role and fail on ownership. Mathesar's data editing is
-- unaffected. Schema changes remain the job of a migration run as the admin.
--
-- The role cannot be created here: hagiographies_admin has NOCREATEROLE, and
-- roles are cluster-wide rather than per-database anyway. If it is absent the
-- migration says so and does nothing, so a from-scratch database still builds.
--
-- TRUNCATE, REFERENCES and TRIGGER are deliberately not granted. TRUNCATE
-- bypasses row-level auditing and is closer to a schema operation than to
-- editing data; DELETE covers the legitimate case.

DO $$
DECLARE
    editor CONSTANT text := 'hagiographies_editor';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = editor) THEN
        RAISE NOTICE
            'role % does not exist on this server; skipping the grants. '
            'It must be created by someone with CREATEROLE.', editor;
        RETURN;
    END IF;

    -- Read and write every table, now and in the future. The ALTER DEFAULT
    -- PRIVILEGES lines matter: without them a table added by a later
    -- migration would be invisible to editors until someone remembered to
    -- grant it.
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), editor);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', editor);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', editor);
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', editor);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', editor);
    EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I', editor);

    -- No new objects: no tables of their own, no schemas of their own.
    EXECUTE format('REVOKE CREATE ON SCHEMA public FROM %I', editor);
    EXECUTE format('REVOKE CREATE ON DATABASE %I FROM %I', current_database(), editor);
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;

    -- Migration bookkeeping is readable but not editable: an editor who could
    -- rewrite schema_migration could make the runner skip or re-run work.
    -- Only relevant while the table still lives in public — since 2026-07-31
    -- the runner keeps it in the hagio_admin schema, which editors are never
    -- granted USAGE on, so there is nothing to revoke on a fresh database.
    IF to_regclass('public.schema_migration') IS NOT NULL THEN
        EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON public.schema_migration FROM %I', editor);
    END IF;

    -- Mathesar's own schemas. USAGE on mathesar_types is needed to work with
    -- the uri columns from 004-006; msar is what the Mathesar UI calls. Both
    -- are safe to expose because every function there is SECURITY INVOKER.
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mathesar_types') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA mathesar_types TO %I', editor);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'msar') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA msar TO %I', editor);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '__msar') THEN
        EXECUTE format('GRANT USAGE ON SCHEMA __msar TO %I', editor);
    END IF;

    RAISE NOTICE 'granted data read/write on % to %', current_database(), editor;
END
$$;
