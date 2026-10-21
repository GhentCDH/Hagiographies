-- 006: repertory_link.url becomes the mathesar_types.uri domain.
--
-- The third and last of the link tables, after 004 (manuscript_link) and 005
-- (edition_link). Same shape, same guards, same msar.cast_to_uri — see 005 for
-- why the Mathesar cast function is used rather than a plain cast.
--
-- repertory_link is hand-curated and still empty (0 rows, as is repertory), so
-- there is no data to convert or to reject: this is a pure type change today.
--
-- No other column in the schema qualifies. Surveyed on 2026-07-30: only the
-- three link tables hold URLs. The near misses all mix URLs with bibliographic
-- references and would abort the cast — manuscript.dating_reference (38 of 410
-- values raise), manuscript.origin_or_provenance_secondary_reference (58 of
-- 375) and text.reference (110 of 176). Their remaining values only satisfy
-- the domain because a citation like 'Author, Title: subtitle' contains a
-- colon that the permissive URI regex reads as a scheme, so converting them
-- would be wrong even where it happens to succeed.
--
-- Note repertory_link.url is `text` rather than `character varying`; the
-- domain's base type is text either way.

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
            'bootstrapped); leaving repertory_link.url as text';
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'repertory_link'
          AND column_name = 'url'
          AND domain_schema = 'mathesar_types'
          AND domain_name = 'uri'
    ) THEN
        RAISE NOTICE 'repertory_link.url is already mathesar_types.uri';
        RETURN;
    END IF;

    ALTER TABLE public.repertory_link
        ALTER COLUMN url TYPE mathesar_types.uri
        USING msar.cast_to_uri(url::text);
END
$$;
