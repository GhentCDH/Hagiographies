-- 018: guarded rename helpers for the October 2026 relabelling (019–051).
--
-- The researchers asked for self-describing names: every content column carries
-- its table name, lookup value columns are named after their table, and
-- many-to-many junction tables are <a>__<b>. Applying that is ~150 renames of
-- tables, columns and the constraints/indexes/sequences named after them, split
-- into one migration per table.
--
-- Mathesar can rename tables and columns from its UI, so a rename may already
-- have happened by hand on some database. These helpers make every rename
-- idempotent and loud about surprises:
--
--   old present, new absent  -> rename
--   old absent,  new present -> already done, NOTICE and carry on
--   both present             -> refuse (two objects would claim one name)
--   both absent              -> refuse (the schema is not what we think it is)
--
-- They live in hagio_admin (never granted to editors) and are kept after the
-- relabelling: the next rename migration can reuse them. All work on schema
-- public.

CREATE OR REPLACE FUNCTION hagio_admin.rename_relation(
    kind char, old_name text, new_name text
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    kind_word text := CASE kind WHEN 'r' THEN 'TABLE' WHEN 'i' THEN 'INDEX'
                                WHEN 'S' THEN 'SEQUENCE' END;
    has_old boolean;
    has_new boolean;
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_class
                   WHERE relnamespace = 'public'::regnamespace
                     AND relname = old_name AND relkind = kind),
           EXISTS (SELECT 1 FROM pg_class
                   WHERE relnamespace = 'public'::regnamespace
                     AND relname = new_name)
      INTO has_old, has_new;

    IF has_old AND NOT has_new THEN
        EXECUTE format('ALTER %s public.%I RENAME TO %I', kind_word, old_name, new_name);
    ELSIF NOT has_old AND has_new THEN
        RAISE NOTICE '% public.% already renamed to %', lower(kind_word), old_name, new_name;
    ELSIF has_old AND has_new THEN
        RAISE EXCEPTION 'cannot rename % public.% to %: the new name is taken',
            lower(kind_word), old_name, new_name;
    ELSE
        RAISE EXCEPTION 'cannot rename % public.% to %: neither exists',
            lower(kind_word), old_name, new_name;
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION hagio_admin.rename_table(old_name text, new_name text)
RETURNS void LANGUAGE sql
AS $$ SELECT hagio_admin.rename_relation('r', old_name, new_name) $$;

CREATE OR REPLACE FUNCTION hagio_admin.rename_index(old_name text, new_name text)
RETURNS void LANGUAGE sql
AS $$ SELECT hagio_admin.rename_relation('i', old_name, new_name) $$;

CREATE OR REPLACE FUNCTION hagio_admin.rename_sequence(old_name text, new_name text)
RETURNS void LANGUAGE sql
AS $$ SELECT hagio_admin.rename_relation('S', old_name, new_name) $$;

CREATE OR REPLACE FUNCTION hagio_admin.rename_column(
    table_name text, old_name text, new_name text
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    rel oid := to_regclass(format('public.%I', table_name));
    has_old boolean;
    has_new boolean;
BEGIN
    IF rel IS NULL THEN
        RAISE EXCEPTION 'cannot rename column %.%: table public.% does not exist',
            table_name, old_name, table_name;
    END IF;
    SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = rel
                     AND attname = old_name AND attnum > 0 AND NOT attisdropped),
           EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = rel
                     AND attname = new_name AND attnum > 0 AND NOT attisdropped)
      INTO has_old, has_new;

    IF has_old AND NOT has_new THEN
        EXECUTE format('ALTER TABLE public.%I RENAME COLUMN %I TO %I',
                       table_name, old_name, new_name);
    ELSIF NOT has_old AND has_new THEN
        RAISE NOTICE 'column %.% already renamed to %', table_name, old_name, new_name;
    ELSIF has_old AND has_new THEN
        RAISE EXCEPTION 'cannot rename column %.% to %: the new name is taken',
            table_name, old_name, new_name;
    ELSE
        RAISE EXCEPTION 'cannot rename column %.% to %: neither exists',
            table_name, old_name, new_name;
    END IF;
END
$$;

-- Renaming a PRIMARY KEY or UNIQUE constraint renames its index as well.
CREATE OR REPLACE FUNCTION hagio_admin.rename_constraint(
    table_name text, old_name text, new_name text
) RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    rel oid := to_regclass(format('public.%I', table_name));
    has_old boolean;
    has_new boolean;
BEGIN
    IF rel IS NULL THEN
        RAISE EXCEPTION 'cannot rename constraint %: table public.% does not exist',
            old_name, table_name;
    END IF;
    SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = rel AND conname = old_name),
           EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = rel AND conname = new_name)
      INTO has_old, has_new;

    IF has_old AND NOT has_new THEN
        EXECUTE format('ALTER TABLE public.%I RENAME CONSTRAINT %I TO %I',
                       table_name, old_name, new_name);
    ELSIF NOT has_old AND has_new THEN
        RAISE NOTICE 'constraint % on % already renamed to %', old_name, table_name, new_name;
    ELSIF has_old AND has_new THEN
        RAISE EXCEPTION 'cannot rename constraint % on % to %: the new name is taken',
            old_name, table_name, new_name;
    ELSE
        RAISE EXCEPTION 'cannot rename constraint % on % to %: neither exists',
            old_name, table_name, new_name;
    END IF;
END
$$;
