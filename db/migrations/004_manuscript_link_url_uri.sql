-- 004: manuscript_link.url becomes the mathesar_types.uri domain.
--
-- Not our change: a researcher set the column's type to URL in Mathesar on QAS
-- on 2026-07-30. Mathesar edits the schema directly and the migration runner
-- only tracks files, so it would never have noticed. Recording it here keeps
-- 000_init.sql + the migrations an honest description of the database and
-- keeps PRD and QAS identical.
--
-- mathesar_types.uri is a `text` domain with a NOT VALID check constraint that
-- regex-matches a URI. NOT VALID means Mathesar never checked the rows already
-- there — but ALTER COLUMN ... TYPE casts every row, and a cast *does* enforce
-- the domain constraint.
--
-- The cast is msar.cast_to_uri, the same function the Mathesar UI uses, so the
-- outcome is identical to doing it by hand in Mathesar. It tries the plain
-- domain cast first and only translates values the domain rejects, lowercasing
-- them and prefixing 'http://' when the resulting TLD is known. A plain
-- `USING url::mathesar_types.uri` would abort on such a value instead. See
-- 005_edition_link_url_uri.sql for the full reasoning.
--
-- The domain and msar.cast_to_uri live in Mathesar's own schemas, which
-- 000_init.sql does not contain (they are created when Mathesar first connects
-- to the database). On a database built from db/migrations/ alone they are
-- absent, so this migration deliberately does nothing there rather than fail:
-- the column stays character varying until Mathesar has been bootstrapped.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'mathesar_types' AND t.typname = 'uri'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'msar' AND p.proname = 'cast_to_uri'
    ) THEN
        RAISE NOTICE
            'mathesar_types.uri / msar.cast_to_uri not present (Mathesar not '
            'bootstrapped); leaving manuscript_link.url as character varying';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'manuscript_link'
          AND column_name = 'url'
          AND domain_schema = 'mathesar_types'
          AND domain_name = 'uri'
    ) THEN
        RAISE NOTICE 'manuscript_link.url is already mathesar_types.uri';
        RETURN;
    END IF;

    ALTER TABLE public.manuscript_link
        ALTER COLUMN url TYPE mathesar_types.uri
        USING msar.cast_to_uri(url::text);
END
$$;
