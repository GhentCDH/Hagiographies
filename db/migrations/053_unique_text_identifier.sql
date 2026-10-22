-- 053: text.text_unique_identifier is unique, regardless of case and surrounding spaces.
--
-- Was enforced by a unique index (ix_text_text_unique_identifier) rather than a constraint; this makes it a constraint like the others.
--
-- Three parts, the same for every *_unique_identifier column (053–056 and the
-- parked edition one):
--   * UNIQUE constraint text_text_unique_identifier_key: exact uniqueness, visible as "unique"
--     in Mathesar and other tools;
--   * CHECK text_text_unique_identifier_check: no leading/trailing spaces;
--   * unique index text_text_unique_identifier_lower_key on lower(col): no two values that
--     differ only in case. With the CHECK, uniqueness ignores case and spaces.
--
-- The plain index ix_text_text_unique_identifier is dropped: the UNIQUE constraint's own index
-- replaces it.
--
-- Like 009 and 051 it refuses rather than guesses: offending values are listed
-- and have to be fixed in Mathesar first. Every step is idempotent.

DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(problem, E'\n')
      INTO offenders
      FROM (SELECT format('%s rows share %s', count(*),
                          string_agg(DISTINCT quote_literal(text_unique_identifier), ' / ')) AS problem
              FROM public.text
             GROUP BY lower(btrim(text_unique_identifier))
            HAVING count(*) > 1
            UNION ALL
            SELECT format('%L has leading/trailing spaces', text_unique_identifier)
              FROM public.text
             WHERE text_unique_identifier <> btrim(text_unique_identifier)) p;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'text.text_unique_identifier is not unique yet; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.text'::regclass AND conname = 'text_text_unique_identifier_key') THEN
        ALTER TABLE public.text ADD CONSTRAINT text_text_unique_identifier_key UNIQUE (text_unique_identifier);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.text'::regclass AND conname = 'text_text_unique_identifier_check') THEN
        ALTER TABLE public.text ADD CONSTRAINT text_text_unique_identifier_check CHECK (text_unique_identifier = btrim(text_unique_identifier));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS text_text_unique_identifier_lower_key ON public.text (lower(text_unique_identifier));
DROP INDEX IF EXISTS public.ix_text_text_unique_identifier;
