-- 005: edition_link.url becomes the mathesar_types.uri domain.
--
-- The same change 004 recorded for manuscript_link.url, applied deliberately
-- this time rather than caught after the fact.
--
-- Does Mathesar translate the data when it changes a column to URL? Yes, but
-- only for values the domain would reject. msar.cast_to_uri(text) is:
--
--     BEGIN
--       RETURN $1::mathesar_types.uri;          -- plain cast, no translation
--     EXCEPTION WHEN SQLSTATE '23514' THEN      -- check_violation
--       -- lowercase the whole value, prefix 'http://', keep it only if the
--       -- resulting TLD is in msar.top_level_domains, else raise
--     END
--
-- So a value that satisfies the domain is stored byte for byte; a value that
-- does not is lowercased and prefixed. A plain `USING url::mathesar_types.uri`
-- would instead abort the migration on such a value.
--
-- Rather than depend on today's data being clean, this migration calls
-- msar.cast_to_uri itself, so the result is identical to doing it in Mathesar
-- by construction. (For the record it makes no difference here: 0 of the 671
-- edition_link.url values are rejected by the domain, and a plain cast and
-- msar.cast_to_uri were verified to agree on every row. The same was true of
-- the 2775 manuscript_link.url rows in 004, which is why 004's plain cast
-- produced exactly what Mathesar had already done.)
--
-- Skipped entirely on a database built from db/migrations/ alone, where
-- Mathesar has never connected and neither the domain nor msar exists.

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
            'bootstrapped); leaving edition_link.url as character varying';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'edition_link'
          AND column_name = 'url'
          AND domain_schema = 'mathesar_types'
          AND domain_name = 'uri'
    ) THEN
        RAISE NOTICE 'edition_link.url is already mathesar_types.uri';
        RETURN;
    END IF;

    ALTER TABLE public.edition_link
        ALTER COLUMN url TYPE mathesar_types.uri
        USING msar.cast_to_uri(url::text);
END
$$;
