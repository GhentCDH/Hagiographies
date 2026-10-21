-- 008: let hagiographies_editor read Mathesar's own reference tables.
--
-- 007 granted USAGE on the msar / __msar / mathesar_types schemas but nothing
-- on the tables inside them, which is not enough: Mathesar's SQL consults its
-- own reference data while building an ordinary query, so an editor saving a
-- cell edit got
--
--   InsufficientPrivilege: permission denied for table expr_templates
--
-- There are exactly two such tables today, both owned by the admin and both
-- static reference data:
--
--   msar.expr_templates      (25 rows)   -- SQL fragments the UI composes with
--   msar.top_level_domains   (1496 rows) -- consulted by msar.cast_to_uri
--
-- SELECT only. Editors have no reason to write Mathesar's reference data; it
-- is populated when Mathesar installs or upgrades, which runs as the admin.
-- The ALTER DEFAULT PRIVILEGES lines cover the tables a future Mathesar
-- version adds, so this does not have to be revisited on every upgrade.
--
-- This does not widen what an editor can do to the schema: every function in
-- these schemas is SECURITY INVOKER, so they still run DDL as the editor and
-- still fail on table ownership.

DO $$
DECLARE
    editor CONSTANT text := 'hagiographies_editor';
    target text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = editor) THEN
        RAISE NOTICE 'role % does not exist on this server; skipping', editor;
        RETURN;
    END IF;

    FOREACH target IN ARRAY ARRAY['msar', '__msar', 'mathesar_types'] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = target) THEN
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', target, editor);
            EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO %I', target, editor);
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT ON TABLES TO %I',
                target, editor
            );
        ELSE
            RAISE NOTICE 'schema % not present; skipping it', target;
        END IF;
    END LOOP;
END
$$;
