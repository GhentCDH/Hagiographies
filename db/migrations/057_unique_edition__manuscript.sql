-- 057: edition__manuscript rows are unique.
--
-- An edition lists a manuscript it used once. PRD (2026-10-22) had 7 repeated pairs:
-- 4 exact copies, and 3 where one row says likely_use_of_a_copy = true and its
-- twin says nothing (NULL). The twin adds no information, so it is removed.
--
-- Duplicates are removed only when nothing is lost: a row goes when every value
-- it holds is also held by a twin with the same (edition_id, manuscript_id). An empty string
-- counts as NULL. Of equal twins the lowest id stays. Any duplicate that
-- remains is a real conflict: the migration then refuses and lists it, to be
-- resolved in Mathesar first.

DO $$
DECLARE
    removed   bigint;
    offenders text;
BEGIN
    DELETE FROM public.edition__manuscript r
     USING public.edition__manuscript s
     WHERE (r.edition_id, r.manuscript_id) = (s.edition_id, s.manuscript_id)
       AND r.edition__manuscript_id <> s.edition__manuscript_id
       AND (nullif(r.edition__manuscript_likely_use_of_a_copy::text, '') IS NULL OR r.edition__manuscript_likely_use_of_a_copy::text IS NOT DISTINCT FROM s.edition__manuscript_likely_use_of_a_copy::text) AND (nullif(r.edition__manuscript_note::text, '') IS NULL OR r.edition__manuscript_note::text IS NOT DISTINCT FROM s.edition__manuscript_note::text)
       AND (NOT ((nullif(s.edition__manuscript_likely_use_of_a_copy::text, '') IS NULL OR s.edition__manuscript_likely_use_of_a_copy::text IS NOT DISTINCT FROM r.edition__manuscript_likely_use_of_a_copy::text) AND (nullif(s.edition__manuscript_note::text, '') IS NULL OR s.edition__manuscript_note::text IS NOT DISTINCT FROM r.edition__manuscript_note::text)) OR s.edition__manuscript_id < r.edition__manuscript_id);
    GET DIAGNOSTICS removed = ROW_COUNT;
    RAISE NOTICE 'edition__manuscript: % redundant duplicate rows removed', removed;

    SELECT string_agg(format('(%s): rows %s', concat_ws(', ', edition_id, manuscript_id), ids), E'\n')
      INTO offenders
      FROM (SELECT edition_id, manuscript_id, string_agg(edition__manuscript_id::text, ', ' ORDER BY edition__manuscript_id) AS ids
              FROM public.edition__manuscript
             GROUP BY edition_id, manuscript_id
            HAVING count(*) > 1) d;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'edition__manuscript has conflicting duplicates; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.edition__manuscript'::regclass AND conname = 'edition__manuscript_edition_id_manuscript_id_key') THEN
        ALTER TABLE public.edition__manuscript ADD CONSTRAINT edition__manuscript_edition_id_manuscript_id_key UNIQUE (edition_id, manuscript_id);
    END IF;
END
$$;
