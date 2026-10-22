-- 058: manuscript__manuscript rows are unique and never self-referencing.
--
-- A manuscript relation (A 'Based on exemplar' / 'Exemplar of' B) is stated once,
-- and a manuscript cannot be related to itself. PRD (2026-10-22) had 1 exact
-- duplicate (BHL_767-16 / BHL_767-13) and no self-references.
--
-- Duplicates are removed only when nothing is lost: a row goes when every value
-- it holds is also held by a twin with the same (manuscript_id, related_manuscript_id, manuscript__manuscript_type_id). An empty string
-- counts as NULL. Of equal twins the lowest id stays. Any duplicate that
-- remains is a real conflict: the migration then refuses and lists it, to be
-- resolved in Mathesar first.

DO $$
DECLARE
    removed   bigint;
    offenders text;
BEGIN
    DELETE FROM public.manuscript__manuscript r
     USING public.manuscript__manuscript s
     WHERE (r.manuscript_id, r.related_manuscript_id, r.manuscript__manuscript_type_id) = (s.manuscript_id, s.related_manuscript_id, s.manuscript__manuscript_type_id)
       AND r.manuscript__manuscript_id <> s.manuscript__manuscript_id
       AND (nullif(r.manuscript__manuscript_note::text, '') IS NULL OR r.manuscript__manuscript_note::text IS NOT DISTINCT FROM s.manuscript__manuscript_note::text)
       AND (NOT ((nullif(s.manuscript__manuscript_note::text, '') IS NULL OR s.manuscript__manuscript_note::text IS NOT DISTINCT FROM r.manuscript__manuscript_note::text)) OR s.manuscript__manuscript_id < r.manuscript__manuscript_id);
    GET DIAGNOSTICS removed = ROW_COUNT;
    RAISE NOTICE 'manuscript__manuscript: % redundant duplicate rows removed', removed;

    SELECT string_agg(format('(%s): rows %s', concat_ws(', ', manuscript_id, related_manuscript_id, manuscript__manuscript_type_id), ids), E'\n')
      INTO offenders
      FROM (SELECT manuscript_id, related_manuscript_id, manuscript__manuscript_type_id, string_agg(manuscript__manuscript_id::text, ', ' ORDER BY manuscript__manuscript_id) AS ids
              FROM public.manuscript__manuscript
             GROUP BY manuscript_id, related_manuscript_id, manuscript__manuscript_type_id
            HAVING count(*) > 1) d;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'manuscript__manuscript has conflicting duplicates; fix in Mathesar first:\n%', offenders;
    END IF;

    SELECT string_agg(format('%s refers to itself', manuscript__manuscript_id), E'\n')
      INTO offenders FROM public.manuscript__manuscript WHERE manuscript_id = related_manuscript_id;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'manuscript__manuscript has self-references; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.manuscript__manuscript'::regclass AND conname = 'manuscript__manuscript_relation_key') THEN
        ALTER TABLE public.manuscript__manuscript ADD CONSTRAINT manuscript__manuscript_relation_key UNIQUE (manuscript_id, related_manuscript_id, manuscript__manuscript_type_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.manuscript__manuscript'::regclass AND conname = 'manuscript__manuscript_not_self_check') THEN
        ALTER TABLE public.manuscript__manuscript ADD CONSTRAINT manuscript__manuscript_not_self_check CHECK (manuscript_id <> related_manuscript_id);
    END IF;
END
$$;
