-- 059: edition__edition rows are unique.
--
-- An edition lists a consulted edition once. PRD (2026-10-22) had 24 repeated
-- pairs, all exact copies (one pair differed only by an empty note vs NULL).
-- The rule that an edition cannot consult itself is parked in
-- pending/edition__edition_no_self_reference.sql: PRD has one such row
-- (BHL_7963-B) that the researchers have to fix first.
--
-- Duplicates are removed only when nothing is lost: a row goes when every value
-- it holds is also held by a twin with the same (edition_id, consulted_edition_id). An empty string
-- counts as NULL. Of equal twins the lowest id stays. Any duplicate that
-- remains is a real conflict: the migration then refuses and lists it, to be
-- resolved in Mathesar first.

DO $$
DECLARE
    removed   bigint;
    offenders text;
BEGIN
    DELETE FROM public.edition__edition r
     USING public.edition__edition s
     WHERE (r.edition_id, r.consulted_edition_id) = (s.edition_id, s.consulted_edition_id)
       AND r.edition__edition_id <> s.edition__edition_id
       AND (nullif(r.edition__edition_note::text, '') IS NULL OR r.edition__edition_note::text IS NOT DISTINCT FROM s.edition__edition_note::text)
       AND (NOT ((nullif(s.edition__edition_note::text, '') IS NULL OR s.edition__edition_note::text IS NOT DISTINCT FROM r.edition__edition_note::text)) OR s.edition__edition_id < r.edition__edition_id);
    GET DIAGNOSTICS removed = ROW_COUNT;
    RAISE NOTICE 'edition__edition: % redundant duplicate rows removed', removed;

    SELECT string_agg(format('(%s): rows %s', concat_ws(', ', edition_id, consulted_edition_id), ids), E'\n')
      INTO offenders
      FROM (SELECT edition_id, consulted_edition_id, string_agg(edition__edition_id::text, ', ' ORDER BY edition__edition_id) AS ids
              FROM public.edition__edition
             GROUP BY edition_id, consulted_edition_id
            HAVING count(*) > 1) d;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'edition__edition has conflicting duplicates; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.edition__edition'::regclass AND conname = 'edition__edition_edition_id_consulted_edition_id_key') THEN
        ALTER TABLE public.edition__edition ADD CONSTRAINT edition__edition_edition_id_consulted_edition_id_key UNIQUE (edition_id, consulted_edition_id);
    END IF;
END
$$;
