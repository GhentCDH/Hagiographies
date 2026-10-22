-- 051: a text cannot list the same URL twice for the same repertory.
--
-- text__repertory (until 044: repertory_link) is a many-to-many junction with a
-- payload. Several rows per (text, repertory) are legitimate, because one text
-- can have several entries in one repertory, each with its own URL. An exact
-- repeat of (text, repertory, url) is not. PRD had none when this was written
-- (2026-10-22).
--
-- The other uniqueness candidates found in the same audit are deliberately left
-- for later; see the relabelling notes. Like 009, this refuses rather than
-- guesses: if duplicates exist it aborts and names them, and they have to be
-- resolved in Mathesar first.

DO $$
DECLARE
    offenders text;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.text__repertory'::regclass
          AND conname = 'text__repertory_text_id_repertory_id_text__repertory_url_key'
    ) THEN
        RAISE NOTICE 'text__repertory unique constraint already present';
        RETURN;
    END IF;

    SELECT string_agg(format('text_id=%s repertory_id=%s url=%s (%s rows)',
                             text_id, repertory_id, text__repertory_url, n), E'\n')
      INTO offenders
      FROM (SELECT text_id, repertory_id, text__repertory_url, count(*) AS n
              FROM public.text__repertory
             GROUP BY 1, 2, 3
            HAVING count(*) > 1) d;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'text__repertory has duplicate (text, repertory, url) rows; '
                        'resolve them in Mathesar first:\n%', offenders;
    END IF;

    ALTER TABLE public.text__repertory
        ADD CONSTRAINT text__repertory_text_id_repertory_id_text__repertory_url_key
        UNIQUE (text_id, repertory_id, text__repertory_url);
END
$$;
