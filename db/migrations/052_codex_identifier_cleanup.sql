-- 052: tidy codex identifiers so 055 can make them unique case- and space-insensitively.
--
-- Two data fixes, both written as rules rather than hard-coded ids (QAS and PRD
-- ids may differ):
--
-- 1. Trim leading/trailing whitespace from codex_unique_identifier, but only
--    where the trimmed value is not already taken. On PRD (2026-10-22) that is
--    'Brussels Boll 29a ', 'Brussels Boll38 ' and 'Brussels Boll41f '.
--
-- 2. Delete a codex that is nothing but a stray name: every column other than
--    its id and identifier is NULL, no manuscript points to it, and its
--    identifier equals another codex's apart from case and spaces. On PRD that
--    is exactly one row, 'brussels boll 50', an empty twin of 'Brussels Boll 50'.
--    A codex with any data, or with any manuscript, is never deleted here: 055
--    will refuse and name it instead.

DO $$
DECLARE
    trimmed  text;
    removed  text;
BEGIN
    WITH changed AS (
        UPDATE public.codex c
           SET codex_unique_identifier = btrim(c.codex_unique_identifier)
         WHERE c.codex_unique_identifier <> btrim(c.codex_unique_identifier)
           AND NOT EXISTS (SELECT 1 FROM public.codex o
                            WHERE o.codex_id <> c.codex_id
                              AND o.codex_unique_identifier = btrim(c.codex_unique_identifier))
        RETURNING c.codex_id, c.codex_unique_identifier
    )
    SELECT string_agg(format('%s → %L', codex_id, codex_unique_identifier), ', ')
      INTO trimmed FROM changed;

    WITH empty_twin AS (
        SELECT c.codex_id
          FROM public.codex c
         WHERE NOT EXISTS (SELECT 1 FROM public.manuscript m WHERE m.codex_id = c.codex_id)
           AND EXISTS (SELECT 1 FROM public.codex o
                        WHERE o.codex_id <> c.codex_id
                          AND lower(btrim(o.codex_unique_identifier))
                            = lower(btrim(c.codex_unique_identifier)))
           -- nothing but the id and the identifier: the row minus those two is all NULL
           AND (to_jsonb(c) - 'codex_id' - 'codex_unique_identifier')
               = (SELECT jsonb_object_agg(k, NULL)
                    FROM jsonb_object_keys(to_jsonb(c) - 'codex_id' - 'codex_unique_identifier') k)
    ), gone AS (
        DELETE FROM public.codex c USING empty_twin e
         WHERE c.codex_id = e.codex_id
        RETURNING c.codex_id, c.codex_unique_identifier
    )
    SELECT string_agg(format('%s %L', codex_id, codex_unique_identifier), ', ')
      INTO removed FROM gone;

    RAISE NOTICE 'codex identifiers trimmed: %', coalesce(trimmed, 'none');
    RAISE NOTICE 'empty duplicate codices deleted: %', coalesce(removed, 'none');
END
$$;
