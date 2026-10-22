-- 054: manuscript.manuscript_unique_identifier is unique, regardless of case and surrounding spaces.
--
-- Not enforced at all until now; PRD had no duplicates on 2026-10-22.
--
-- Three parts, the same for every *_unique_identifier column (053–056 and the
-- parked edition one):
--   * UNIQUE constraint manuscript_manuscript_unique_identifier_key: exact uniqueness, visible as "unique"
--     in Mathesar and other tools;
--   * CHECK manuscript_manuscript_unique_identifier_check: no leading/trailing spaces;
--   * unique index manuscript_manuscript_unique_identifier_lower_key on lower(col): no two values that
--     differ only in case. With the CHECK, uniqueness ignores case and spaces.
--
-- The plain index ix_manuscript_manuscript_unique_identifier is dropped: the UNIQUE constraint's own index
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
                          string_agg(DISTINCT quote_literal(manuscript_unique_identifier), ' / ')) AS problem
              FROM public.manuscript
             GROUP BY lower(btrim(manuscript_unique_identifier))
            HAVING count(*) > 1
            UNION ALL
            SELECT format('%L has leading/trailing spaces', manuscript_unique_identifier)
              FROM public.manuscript
             WHERE manuscript_unique_identifier <> btrim(manuscript_unique_identifier)) p;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'manuscript.manuscript_unique_identifier is not unique yet; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.manuscript'::regclass AND conname = 'manuscript_manuscript_unique_identifier_key') THEN
        ALTER TABLE public.manuscript ADD CONSTRAINT manuscript_manuscript_unique_identifier_key UNIQUE (manuscript_unique_identifier);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.manuscript'::regclass AND conname = 'manuscript_manuscript_unique_identifier_check') THEN
        ALTER TABLE public.manuscript ADD CONSTRAINT manuscript_manuscript_unique_identifier_check CHECK (manuscript_unique_identifier = btrim(manuscript_unique_identifier));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS manuscript_manuscript_unique_identifier_lower_key ON public.manuscript (lower(manuscript_unique_identifier));
DROP INDEX IF EXISTS public.ix_manuscript_manuscript_unique_identifier;
