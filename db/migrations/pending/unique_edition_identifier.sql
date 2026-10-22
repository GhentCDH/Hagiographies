-- pending: edition.edition_unique_identifier is unique, regardless of case and surrounding spaces.
--
-- BLOCKED: PRD has 'BHL_8426-K' twice (editions 770 and 811). Parked in pending/; give it the next free number and move it up once the researchers have renamed one of them.
--
-- Three parts, the same for every *_unique_identifier column (053–056 and the
-- parked edition one):
--   * UNIQUE constraint edition_edition_unique_identifier_key: exact uniqueness, visible as "unique"
--     in Mathesar and other tools;
--   * CHECK edition_edition_unique_identifier_check: no leading/trailing spaces;
--   * unique index edition_edition_unique_identifier_lower_key on lower(col): no two values that
--     differ only in case. With the CHECK, uniqueness ignores case and spaces.
--
-- The plain index ix_edition_edition_unique_identifier is dropped: the UNIQUE constraint's own index
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
                          string_agg(DISTINCT quote_literal(edition_unique_identifier), ' / ')) AS problem
              FROM public.edition
             GROUP BY lower(btrim(edition_unique_identifier))
            HAVING count(*) > 1
            UNION ALL
            SELECT format('%L has leading/trailing spaces', edition_unique_identifier)
              FROM public.edition
             WHERE edition_unique_identifier <> btrim(edition_unique_identifier)) p;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'edition.edition_unique_identifier is not unique yet; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.edition'::regclass AND conname = 'edition_edition_unique_identifier_key') THEN
        ALTER TABLE public.edition ADD CONSTRAINT edition_edition_unique_identifier_key UNIQUE (edition_unique_identifier);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.edition'::regclass AND conname = 'edition_edition_unique_identifier_check') THEN
        ALTER TABLE public.edition ADD CONSTRAINT edition_edition_unique_identifier_check CHECK (edition_unique_identifier = btrim(edition_unique_identifier));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS edition_edition_unique_identifier_lower_key ON public.edition (lower(edition_unique_identifier));
DROP INDEX IF EXISTS public.ix_edition_edition_unique_identifier;
