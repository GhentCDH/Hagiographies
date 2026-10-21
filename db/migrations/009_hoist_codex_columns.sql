-- 009: hoist the codex-level columns from manuscript onto codex.
--
-- The MANUSCRIPTS worksheet was a join of two entities: the physical codex and
-- the text copies bound in it. The importer flattened that into `manuscript`,
-- so every attribute of the book was repeated once per copy. 002 created
-- `codex`; this moves the book's own attributes onto it.
--
-- ADDITIVE ONLY. The columns remain on `manuscript` too, so nothing is lost
-- and Mathesar keeps working unchanged. A later migration drops them, once the
-- researchers have confirmed the hoisted values in Mathesar.
--
-- Three columns are deliberately NOT moved, because codex_id makes them
-- redundant and they should be computed rather than stored:
--
--   codex_number           a hand-kept numbering of codices; codex_id is that
--   codex_copy_amount      count(*) of the codex's manuscripts
--   codex_multiple_copies  that same count > 1
--
-- They stay on `manuscript` for now and go in the same later drop migration.
-- codex_number is also the one column that still conflicts (10 codices, mostly
-- adjacent pairs like Arras 5 -> {12,13}), so not moving it costs nothing.
--
-- If any codex disagrees with itself on a column being moved, the migration
-- aborts and names the columns. Silently picking a winner is exactly what the
-- conflict report exists to prevent. Verified clean on QAS on 2026-07-30:
-- all 30 columns, across the 263 codices holding more than one manuscript.

-- ---------------------------------------------------------------- guard ----

DO $$
DECLARE
    cols CONSTANT text[] := ARRAY[
        'manuscript_preservation_status_id',
        'location_id',
        'manuscript_holding_institution_id',
        'height',
        'width',
        'dating_century',
        'dating_range_start',
        'dating_range_end',
        'dating_reference',
        'dating_confidence_id',
        'dating_note',
        'codex_legendiers_usable',
        'codex_composite',
        'codex_legendiers_entry_code',
        'codex_notes',
        'vernacular_region_id',
        'origin_archdiocese_id',
        'origin_diocese_id',
        'origin_diocese_confidence_rating_id',
        'origin_institution_id',
        'origin_institution_confidence_rating_id',
        'provenance_early_institute_id',
        'provenance_early_confidence_id',
        'provenance_later_institute_id',
        'provenance_later_confidence_id',
        'origin_or_provenance_secondary_reference',
        'manuscript_type_id',
        'manuscript_type_note',
        'general_notes',
        'shelfmark'
    ];
    col text;
    n integer;
    bad text[] := '{}';
BEGIN
    FOREACH col IN ARRAY cols LOOP
        EXECUTE format(
            'SELECT count(*) FROM (SELECT codex_id FROM manuscript '
            'WHERE codex_id IS NOT NULL GROUP BY codex_id '
            'HAVING count(DISTINCT %I) > 1) conflicting', col
        ) INTO n;
        IF n > 0 THEN
            bad := bad || format('%s (%s codices)', col, n);
        END IF;
    END LOOP;

    IF cardinality(bad) > 0 THEN
        RAISE EXCEPTION
            'cannot hoist: these columns still differ between manuscripts '
            'sharing a codex: %. Resolve them in Mathesar (see the '
            'codex_conflicts section of data/backfill_report.html) and re-run.',
            array_to_string(bad, ', ');
    END IF;
END
$$;

-- ------------------------------------------------------------- columns ----


ALTER TABLE public.codex ADD COLUMN manuscript_preservation_status_id integer;
ALTER TABLE public.codex ADD COLUMN location_id integer;
ALTER TABLE public.codex ADD COLUMN manuscript_holding_institution_id integer;
ALTER TABLE public.codex ADD COLUMN height character varying;
ALTER TABLE public.codex ADD COLUMN width character varying;
ALTER TABLE public.codex ADD COLUMN dating_century integer;
ALTER TABLE public.codex ADD COLUMN dating_range_start integer;
ALTER TABLE public.codex ADD COLUMN dating_range_end integer;
ALTER TABLE public.codex ADD COLUMN dating_reference character varying;
ALTER TABLE public.codex ADD COLUMN dating_confidence_id integer;
ALTER TABLE public.codex ADD COLUMN dating_note character varying;
ALTER TABLE public.codex ADD COLUMN codex_legendiers_usable boolean;
ALTER TABLE public.codex ADD COLUMN codex_composite boolean;
ALTER TABLE public.codex ADD COLUMN codex_legendiers_entry_code character varying;
ALTER TABLE public.codex ADD COLUMN codex_notes character varying;
ALTER TABLE public.codex ADD COLUMN vernacular_region_id integer;
ALTER TABLE public.codex ADD COLUMN origin_archdiocese_id integer;
ALTER TABLE public.codex ADD COLUMN origin_diocese_id integer;
ALTER TABLE public.codex ADD COLUMN origin_diocese_confidence_rating_id integer;
ALTER TABLE public.codex ADD COLUMN origin_institution_id integer;
ALTER TABLE public.codex ADD COLUMN origin_institution_confidence_rating_id integer;
ALTER TABLE public.codex ADD COLUMN provenance_early_institute_id integer;
ALTER TABLE public.codex ADD COLUMN provenance_early_confidence_id integer;
ALTER TABLE public.codex ADD COLUMN provenance_later_institute_id integer;
ALTER TABLE public.codex ADD COLUMN provenance_later_confidence_id integer;
ALTER TABLE public.codex ADD COLUMN origin_or_provenance_secondary_reference character varying;
ALTER TABLE public.codex ADD COLUMN manuscript_type_id integer;
ALTER TABLE public.codex ADD COLUMN manuscript_type_note character varying;
ALTER TABLE public.codex ADD COLUMN general_notes character varying;
ALTER TABLE public.codex ADD COLUMN shelfmark character varying;

ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_manuscript_preservation_status_id_fkey FOREIGN KEY (manuscript_preservation_status_id)
    REFERENCES public.manuscript_preservation_status(manuscript_preservation_status_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_location_id_fkey FOREIGN KEY (location_id)
    REFERENCES public.location(location_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_manuscript_holding_institution_id_fkey FOREIGN KEY (manuscript_holding_institution_id)
    REFERENCES public.manuscript_holding_institution(manuscript_holding_institution_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_dating_confidence_id_fkey FOREIGN KEY (dating_confidence_id)
    REFERENCES public.dating_confidence(dating_confidence_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_vernacular_region_id_fkey FOREIGN KEY (vernacular_region_id)
    REFERENCES public.vernacular_region(vernacular_region_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_origin_archdiocese_id_fkey FOREIGN KEY (origin_archdiocese_id)
    REFERENCES public.archdiocese(archdiocese_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_origin_diocese_id_fkey FOREIGN KEY (origin_diocese_id)
    REFERENCES public.diocese(diocese_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_origin_diocese_confidence_rating_id_fkey FOREIGN KEY (origin_diocese_confidence_rating_id)
    REFERENCES public.origin_confidence(origin_confidence_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_origin_institution_id_fkey FOREIGN KEY (origin_institution_id)
    REFERENCES public.institution(institution_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_origin_institution_confidence_rating_id_fkey FOREIGN KEY (origin_institution_confidence_rating_id)
    REFERENCES public.origin_confidence(origin_confidence_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_provenance_early_institute_id_fkey FOREIGN KEY (provenance_early_institute_id)
    REFERENCES public.institution(institution_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_provenance_early_confidence_id_fkey FOREIGN KEY (provenance_early_confidence_id)
    REFERENCES public.provenance_confidence(provenance_confidence_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_provenance_later_institute_id_fkey FOREIGN KEY (provenance_later_institute_id)
    REFERENCES public.institution(institution_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_provenance_later_confidence_id_fkey FOREIGN KEY (provenance_later_confidence_id)
    REFERENCES public.provenance_confidence(provenance_confidence_id);
ALTER TABLE ONLY public.codex
    ADD CONSTRAINT codex_manuscript_type_id_fkey FOREIGN KEY (manuscript_type_id)
    REFERENCES public.manuscript_type(manuscript_type_id);

COMMENT ON COLUMN public.codex.manuscript_preservation_status_id
    IS 'Excel MANUSCRIPTS → ''Preservation status of manuscript copy''';
COMMENT ON COLUMN public.codex.location_id
    IS 'Excel MANUSCRIPTS → ''Manuscript location''';
COMMENT ON COLUMN public.codex.manuscript_holding_institution_id
    IS 'Excel MANUSCRIPTS → ''Manuscript holding institution''';
COMMENT ON COLUMN public.codex.height
    IS 'Excel MANUSCRIPTS → ''Manuscript height''';
COMMENT ON COLUMN public.codex.width
    IS 'Excel MANUSCRIPTS → ''Manuscript width''';
COMMENT ON COLUMN public.codex.dating_century
    IS 'Excel MANUSCRIPTS → ''Manuscript dating by (earliest) century''';
COMMENT ON COLUMN public.codex.dating_range_start
    IS 'Excel MANUSCRIPTS → ''Manuscript dating range start (0 when not an integer in the workbook)''';
COMMENT ON COLUMN public.codex.dating_range_end
    IS 'Excel MANUSCRIPTS → ''Manuscript dating range end (0 when not an integer in the workbook)''';
COMMENT ON COLUMN public.codex.dating_reference
    IS 'Excel MANUSCRIPTS → ''Preferred secondary reference for manuscript dating (hyperlink URL when the cell is hyperlinked)''';
COMMENT ON COLUMN public.codex.dating_confidence_id
    IS 'Excel MANUSCRIPTS → ''Confidence rating for manuscript dating''';
COMMENT ON COLUMN public.codex.dating_note
    IS 'Excel MANUSCRIPTS → ''raw ''Manuscript dating range start/end'' when not integers''';
COMMENT ON COLUMN public.codex.codex_legendiers_usable
    IS 'Excel MANUSCRIPTS → ''Usable Légendiers entry for codex contents''';
COMMENT ON COLUMN public.codex.codex_composite
    IS 'Excel MANUSCRIPTS → ''Composite?''';
COMMENT ON COLUMN public.codex.codex_legendiers_entry_code
    IS 'Excel MANUSCRIPTS → ''Légendiers entry code''';
COMMENT ON COLUMN public.codex.codex_notes
    IS 'Excel MANUSCRIPTS → ''Notes on codex contents''';
COMMENT ON COLUMN public.codex.vernacular_region_id
    IS 'Excel MANUSCRIPTS → ''Vernacular region (Romance/Germanic)''';
COMMENT ON COLUMN public.codex.origin_archdiocese_id
    IS 'Excel MANUSCRIPTS → ''Manuscript origin by archdiocese''';
COMMENT ON COLUMN public.codex.origin_diocese_id
    IS 'Excel MANUSCRIPTS → ''Manuscript origin by diocese''';
COMMENT ON COLUMN public.codex.origin_diocese_confidence_rating_id
    IS 'Excel MANUSCRIPTS → ''Manuscript origin by diocese confidence rating''';
COMMENT ON COLUMN public.codex.origin_institution_id
    IS 'Excel MANUSCRIPTS → ''Manuscript origin by institution''';
COMMENT ON COLUMN public.codex.origin_institution_confidence_rating_id
    IS 'Excel MANUSCRIPTS → ''Manuscript origin confidence rating''';
COMMENT ON COLUMN public.codex.provenance_early_institute_id
    IS 'Excel MANUSCRIPTS → ''Manuscript provenance by early/earliest institutional owner (second occurrence of this duplicated header)''';
COMMENT ON COLUMN public.codex.provenance_early_confidence_id
    IS 'Excel MANUSCRIPTS → ''Manuscript provenance by early/earliest institutional owner confidence rating (second occurrence of this duplicated header)''';
COMMENT ON COLUMN public.codex.provenance_later_institute_id
    IS 'Excel MANUSCRIPTS → ''Manuscript provenance by undetermined or later institutional owner''';
COMMENT ON COLUMN public.codex.provenance_later_confidence_id
    IS 'Excel MANUSCRIPTS → ''no source column yet (the workbook has no confidence rating for the undetermined/later owner) — always NULL for now''';
COMMENT ON COLUMN public.codex.origin_or_provenance_secondary_reference
    IS 'Excel MANUSCRIPTS → ''Manuscript origin and provenance preferred secondary reference (hyperlink URL when the cell is hyperlinked)''';
COMMENT ON COLUMN public.codex.manuscript_type_id
    IS 'Excel MANUSCRIPTS → ''Manuscript type (whitespace-normalized label)''';
COMMENT ON COLUMN public.codex.manuscript_type_note
    IS 'Excel MANUSCRIPTS → ''Manuscript type (raw cell, incl. notes on type selection)''';
COMMENT ON COLUMN public.codex.general_notes
    IS 'Excel MANUSCRIPTS → ''''Notes'', prefixed with the raw ''Unique text identifier'' when it resolves to no text''';
COMMENT ON COLUMN public.codex.shelfmark
    IS 'Excel MANUSCRIPTS → ''Manuscript shelfmark''';

-- ---------------------------------------------------------------- data ----
-- Every group is single-valued (the guard above proved it), so the aggregate
-- just picks that one value; bool_or is used where max() is not defined.

UPDATE public.codex c SET
    manuscript_preservation_status_id = src.manuscript_preservation_status_id,
    location_id = src.location_id,
    manuscript_holding_institution_id = src.manuscript_holding_institution_id,
    height = src.height,
    width = src.width,
    dating_century = src.dating_century,
    dating_range_start = src.dating_range_start,
    dating_range_end = src.dating_range_end,
    dating_reference = src.dating_reference,
    dating_confidence_id = src.dating_confidence_id,
    dating_note = src.dating_note,
    codex_legendiers_usable = src.codex_legendiers_usable,
    codex_composite = src.codex_composite,
    codex_legendiers_entry_code = src.codex_legendiers_entry_code,
    codex_notes = src.codex_notes,
    vernacular_region_id = src.vernacular_region_id,
    origin_archdiocese_id = src.origin_archdiocese_id,
    origin_diocese_id = src.origin_diocese_id,
    origin_diocese_confidence_rating_id = src.origin_diocese_confidence_rating_id,
    origin_institution_id = src.origin_institution_id,
    origin_institution_confidence_rating_id = src.origin_institution_confidence_rating_id,
    provenance_early_institute_id = src.provenance_early_institute_id,
    provenance_early_confidence_id = src.provenance_early_confidence_id,
    provenance_later_institute_id = src.provenance_later_institute_id,
    provenance_later_confidence_id = src.provenance_later_confidence_id,
    origin_or_provenance_secondary_reference = src.origin_or_provenance_secondary_reference,
    manuscript_type_id = src.manuscript_type_id,
    manuscript_type_note = src.manuscript_type_note,
    general_notes = src.general_notes,
    shelfmark = src.shelfmark
FROM (
    SELECT codex_id,
           max(manuscript_preservation_status_id) AS manuscript_preservation_status_id,
           max(location_id) AS location_id,
           max(manuscript_holding_institution_id) AS manuscript_holding_institution_id,
           max(height) AS height,
           max(width) AS width,
           max(dating_century) AS dating_century,
           max(dating_range_start) AS dating_range_start,
           max(dating_range_end) AS dating_range_end,
           max(dating_reference) AS dating_reference,
           max(dating_confidence_id) AS dating_confidence_id,
           max(dating_note) AS dating_note,
           bool_or(codex_legendiers_usable) AS codex_legendiers_usable,
           bool_or(codex_composite) AS codex_composite,
           max(codex_legendiers_entry_code) AS codex_legendiers_entry_code,
           max(codex_notes) AS codex_notes,
           max(vernacular_region_id) AS vernacular_region_id,
           max(origin_archdiocese_id) AS origin_archdiocese_id,
           max(origin_diocese_id) AS origin_diocese_id,
           max(origin_diocese_confidence_rating_id) AS origin_diocese_confidence_rating_id,
           max(origin_institution_id) AS origin_institution_id,
           max(origin_institution_confidence_rating_id) AS origin_institution_confidence_rating_id,
           max(provenance_early_institute_id) AS provenance_early_institute_id,
           max(provenance_early_confidence_id) AS provenance_early_confidence_id,
           max(provenance_later_institute_id) AS provenance_later_institute_id,
           max(provenance_later_confidence_id) AS provenance_later_confidence_id,
           max(origin_or_provenance_secondary_reference) AS origin_or_provenance_secondary_reference,
           max(manuscript_type_id) AS manuscript_type_id,
           max(manuscript_type_note) AS manuscript_type_note,
           max(general_notes) AS general_notes,
           max(shelfmark) AS shelfmark
      FROM public.manuscript
     WHERE codex_id IS NOT NULL
     GROUP BY codex_id
) src
WHERE src.codex_id = c.codex_id;
