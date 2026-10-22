-- 055: codex.codex_unique_identifier is unique, regardless of case and surrounding spaces.
--
-- Already exactly unique; 052 removed the case-variant twin and the stray spaces.
--
-- Three parts, the same for every *_unique_identifier column (053–056 and the
-- parked edition one):
--   * UNIQUE constraint codex_codex_unique_identifier_key: exact uniqueness, visible as "unique"
--     in Mathesar and other tools;
--   * CHECK codex_codex_unique_identifier_check: no leading/trailing spaces;
--   * unique index codex_codex_unique_identifier_lower_key on lower(col): no two values that
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
                          string_agg(DISTINCT quote_literal(codex_unique_identifier), ' / ')) AS problem
              FROM public.codex
             GROUP BY lower(btrim(codex_unique_identifier))
            HAVING count(*) > 1
            UNION ALL
            SELECT format('%L has leading/trailing spaces', codex_unique_identifier)
              FROM public.codex
             WHERE codex_unique_identifier <> btrim(codex_unique_identifier)) p;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION E'codex.codex_unique_identifier is not unique yet; fix in Mathesar first:\n%', offenders;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.codex'::regclass AND conname = 'codex_codex_unique_identifier_key') THEN
        ALTER TABLE public.codex ADD CONSTRAINT codex_codex_unique_identifier_key UNIQUE (codex_unique_identifier);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'public.codex'::regclass AND conname = 'codex_codex_unique_identifier_check') THEN
        ALTER TABLE public.codex ADD CONSTRAINT codex_codex_unique_identifier_check CHECK (codex_unique_identifier = btrim(codex_unique_identifier));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS codex_codex_unique_identifier_lower_key ON public.codex (lower(codex_unique_identifier));
