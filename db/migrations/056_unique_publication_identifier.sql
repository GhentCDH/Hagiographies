-- 056: publication.publication_unique_identifier is unique, regardless of case and surrounding spaces.
--
-- Already exactly unique; this adds the case/space rules.
--
-- Three parts, the same for every *_unique_identifier column (053–056 and the
-- parked edition one):
--   * UNIQUE constraint publication_publication_unique_identifier_key: exact uniqueness, visible as "unique"
--     in Mathesar and other tools;
--   * CHECK publication_publication_unique_identifier_check: no leading/trailing spaces;
--   * unique index publication_publication_unique_identifier_lower_key on lower(col): no two values that
--     differ only in case. With the CHECK, uniqueness ignores case and spaces.
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
                          string_agg(DISTINCT quote_literal(publication_unique_identifier), ' / ')) AS problem
              FROM public.publication
             GROUP BY lower(btrim(publication_unique_identifier))
            HAVING count(*) > 1
            UNION ALL
            SELECT format('%L has leading/trailing spaces', publication_unique_identifier)
              FROM public.publication
             WHERE publication_unique_identifier <> btrim(publication_unique_identifier)) p;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'publication.publication_unique_identifier is not unique yet; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.publication'::regclass AND conname = 'publication_publication_unique_identifier_key') THEN
        ALTER TABLE public.publication ADD CONSTRAINT publication_publication_unique_identifier_key UNIQUE (publication_unique_identifier);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.publication'::regclass AND conname = 'publication_publication_unique_identifier_check') THEN
        ALTER TABLE public.publication ADD CONSTRAINT publication_publication_unique_identifier_check CHECK (publication_unique_identifier = btrim(publication_unique_identifier));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS publication_publication_unique_identifier_lower_key ON public.publication (lower(publication_unique_identifier));
