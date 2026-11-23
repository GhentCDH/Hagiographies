-- 064: an edition cannot list itself as a consulted edition.
--
-- Parked in pending/ until the researchers fixed edition__edition_id 711
-- (BHL_7963-B "consulted" BHL_7963-B on PRD, 2026-10-22).

DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(format('edition__edition_id %s: edition %s consults itself',
                             ee.edition__edition_id, e.edition_unique_identifier), E'\n')
      INTO offenders
      FROM public.edition__edition ee
      JOIN public.edition e ON e.edition_id = ee.edition_id
     WHERE ee.edition_id = ee.consulted_edition_id;
    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'edition__edition has self-references; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.edition__edition'::regclass
                      AND conname = 'edition__edition_not_self_check') THEN
        ALTER TABLE public.edition__edition
            ADD CONSTRAINT edition__edition_not_self_check CHECK (edition_id <> consulted_edition_id);
    END IF;
END
$$;
