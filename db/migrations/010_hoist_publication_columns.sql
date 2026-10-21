-- 010: hoist the publication-level columns from edition onto publication.
--
-- The counterpart to 009. EDITIONS repeated the volume's year and
-- bibliographic reference on every edition printed in it; 003 created
-- `publication`, and this moves those two facts onto it.
--
-- Only two columns qualify. Everything else on `edition` genuinely describes
-- the individual edition rather than the volume, which the data confirms —
-- measured across the publications holding more than one edition:
--
--   page_numbers          144 publications disagree   -> stays on edition
--   reprint_of_edition_id  66                         -> stays
--   reprint_of             45                         -> stays
--   reprint                29                         -> stays
--   general_notes           7                         -> stays
--   collation_done          1                         -> stays
--
-- ADDITIVE ONLY, like 009: publication_year and reference remain on `edition`
-- too. The later drop migration removes them from both tables at once.
--
-- Same abort-rather-than-guess guard as 009.

-- ---------------------------------------------------------------- guard ----

DO $$
DECLARE
    cols CONSTANT text[] := ARRAY['publication_year', 'reference'];
    col text;
    n integer;
    bad text[] := '{}';
BEGIN
    FOREACH col IN ARRAY cols LOOP
        EXECUTE format(
            'SELECT count(*) FROM (SELECT publication_id FROM edition '
            'WHERE publication_id IS NOT NULL GROUP BY publication_id '
            'HAVING count(DISTINCT %I) > 1) conflicting', col
        ) INTO n;
        IF n > 0 THEN
            bad := bad || format('%s (%s publications)', col, n);
        END IF;
    END LOOP;

    IF cardinality(bad) > 0 THEN
        RAISE EXCEPTION
            'cannot hoist: these columns still differ between editions '
            'sharing a publication: %. Resolve them in Mathesar (see the '
            'publication_conflicts section of data/backfill_report.html) '
            'and re-run.',
            array_to_string(bad, ', ');
    END IF;
END
$$;

-- ------------------------------------------------------------- columns ----

ALTER TABLE public.publication ADD COLUMN publication_year integer;
ALTER TABLE public.publication ADD COLUMN reference character varying;

COMMENT ON COLUMN public.publication.publication_year
    IS 'Excel EDITIONS → ''Publication year''';
COMMENT ON COLUMN public.publication.reference
    IS 'Excel EDITIONS → ''Edition reference''';

-- ---------------------------------------------------------------- data ----
-- Every group is single-valued (the guard proved it), so max() just picks it.

UPDATE public.publication p SET
    publication_year = src.publication_year,
    reference = src.reference
FROM (
    SELECT publication_id,
           max(publication_year) AS publication_year,
           max(reference) AS reference
      FROM public.edition
     WHERE publication_id IS NOT NULL
     GROUP BY publication_id
) src
WHERE src.publication_id = p.publication_id;
