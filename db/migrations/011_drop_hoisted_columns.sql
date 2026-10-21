-- 011: drop the columns that 009 and 010 hoisted. NOT YET ACTIVE.
--
-- This file lives in db/migrations/pending/ so the runner ignores it (it globs
-- db/migrations/*.sql and does not recurse). Move it up one directory when the
-- researchers have confirmed the hoisted values look right in Mathesar:
--
--     git mv db/migrations/pending/011_drop_hoisted_columns.sql db/migrations/
--     just db_local_migrate     # rehearse on a fresh clone first
--
-- This is the only destructive migration in the set. Take a dump first:
--
--     pg_dump --no-owner --no-privileges -Fc "$PG_DATABASE_URL" \
--         -f data/pre_drop.dump
--
-- Before dropping, it re-checks that codex/publication actually hold the
-- values, so a half-run hoist cannot silently lose data.
--
-- Not dropped, deliberately:
--
--   manuscript.codex_identifier  duplicates codex.name, but it is the column
--                                codex.name was derived from and the only way
--                                to rebuild the link from scratch. Drop it in
--                                a later migration if you want the redundancy
--                                gone; it is a judgement call, not an
--                                oversight.
--   manuscript.folio_or_page_range  genuinely per text copy, stays for good.
--
-- Known consumers that must be updated in the same commit:
--
--   db/src/hagio_db/backfill.py  writes manuscript.shelfmark; after this it
--                                must write codex.shelfmark (or be retired,
--                                since it is a one-off that has already run).
--   utils/mathesar/.../column_display.json  configures edition.publication_year;
--                                that column moves to publication.

-- --------------------------------------------------------------- guard ----

DO $$
DECLARE
    missing text[] := '{}';
    n integer;
BEGIN
    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.manuscript_preservation_status_id IS NOT NULL AND m.manuscript_preservation_status_id IS DISTINCT FROM c.manuscript_preservation_status_id' INTO n;
    IF n > 0 THEN missing := missing || 'manuscript_preservation_status_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.location_id IS NOT NULL AND m.location_id IS DISTINCT FROM c.location_id' INTO n;
    IF n > 0 THEN missing := missing || 'location_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.manuscript_holding_institution_id IS NOT NULL AND m.manuscript_holding_institution_id IS DISTINCT FROM c.manuscript_holding_institution_id' INTO n;
    IF n > 0 THEN missing := missing || 'manuscript_holding_institution_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.height IS NOT NULL AND m.height IS DISTINCT FROM c.height' INTO n;
    IF n > 0 THEN missing := missing || 'height (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.width IS NOT NULL AND m.width IS DISTINCT FROM c.width' INTO n;
    IF n > 0 THEN missing := missing || 'width (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_century IS NOT NULL AND m.dating_century IS DISTINCT FROM c.dating_century' INTO n;
    IF n > 0 THEN missing := missing || 'dating_century (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_range_start IS NOT NULL AND m.dating_range_start IS DISTINCT FROM c.dating_range_start' INTO n;
    IF n > 0 THEN missing := missing || 'dating_range_start (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_range_end IS NOT NULL AND m.dating_range_end IS DISTINCT FROM c.dating_range_end' INTO n;
    IF n > 0 THEN missing := missing || 'dating_range_end (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_reference IS NOT NULL AND m.dating_reference IS DISTINCT FROM c.dating_reference' INTO n;
    IF n > 0 THEN missing := missing || 'dating_reference (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_confidence_id IS NOT NULL AND m.dating_confidence_id IS DISTINCT FROM c.dating_confidence_id' INTO n;
    IF n > 0 THEN missing := missing || 'dating_confidence_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.dating_note IS NOT NULL AND m.dating_note IS DISTINCT FROM c.dating_note' INTO n;
    IF n > 0 THEN missing := missing || 'dating_note (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.codex_legendiers_usable IS NOT NULL AND m.codex_legendiers_usable IS DISTINCT FROM c.codex_legendiers_usable' INTO n;
    IF n > 0 THEN missing := missing || 'codex_legendiers_usable (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.codex_composite IS NOT NULL AND m.codex_composite IS DISTINCT FROM c.codex_composite' INTO n;
    IF n > 0 THEN missing := missing || 'codex_composite (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.codex_legendiers_entry_code IS NOT NULL AND m.codex_legendiers_entry_code IS DISTINCT FROM c.codex_legendiers_entry_code' INTO n;
    IF n > 0 THEN missing := missing || 'codex_legendiers_entry_code (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.codex_notes IS NOT NULL AND m.codex_notes IS DISTINCT FROM c.codex_notes' INTO n;
    IF n > 0 THEN missing := missing || 'codex_notes (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.vernacular_region_id IS NOT NULL AND m.vernacular_region_id IS DISTINCT FROM c.vernacular_region_id' INTO n;
    IF n > 0 THEN missing := missing || 'vernacular_region_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_archdiocese_id IS NOT NULL AND m.origin_archdiocese_id IS DISTINCT FROM c.origin_archdiocese_id' INTO n;
    IF n > 0 THEN missing := missing || 'origin_archdiocese_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_diocese_id IS NOT NULL AND m.origin_diocese_id IS DISTINCT FROM c.origin_diocese_id' INTO n;
    IF n > 0 THEN missing := missing || 'origin_diocese_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_diocese_confidence_rating_id IS NOT NULL AND m.origin_diocese_confidence_rating_id IS DISTINCT FROM c.origin_diocese_confidence_rating_id' INTO n;
    IF n > 0 THEN missing := missing || 'origin_diocese_confidence_rating_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_institution_id IS NOT NULL AND m.origin_institution_id IS DISTINCT FROM c.origin_institution_id' INTO n;
    IF n > 0 THEN missing := missing || 'origin_institution_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_institution_confidence_rating_id IS NOT NULL AND m.origin_institution_confidence_rating_id IS DISTINCT FROM c.origin_institution_confidence_rating_id' INTO n;
    IF n > 0 THEN missing := missing || 'origin_institution_confidence_rating_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.provenance_early_institute_id IS NOT NULL AND m.provenance_early_institute_id IS DISTINCT FROM c.provenance_early_institute_id' INTO n;
    IF n > 0 THEN missing := missing || 'provenance_early_institute_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.provenance_early_confidence_id IS NOT NULL AND m.provenance_early_confidence_id IS DISTINCT FROM c.provenance_early_confidence_id' INTO n;
    IF n > 0 THEN missing := missing || 'provenance_early_confidence_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.provenance_later_institute_id IS NOT NULL AND m.provenance_later_institute_id IS DISTINCT FROM c.provenance_later_institute_id' INTO n;
    IF n > 0 THEN missing := missing || 'provenance_later_institute_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.provenance_later_confidence_id IS NOT NULL AND m.provenance_later_confidence_id IS DISTINCT FROM c.provenance_later_confidence_id' INTO n;
    IF n > 0 THEN missing := missing || 'provenance_later_confidence_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.origin_or_provenance_secondary_reference IS NOT NULL AND m.origin_or_provenance_secondary_reference IS DISTINCT FROM c.origin_or_provenance_secondary_reference' INTO n;
    IF n > 0 THEN missing := missing || 'origin_or_provenance_secondary_reference (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.manuscript_type_id IS NOT NULL AND m.manuscript_type_id IS DISTINCT FROM c.manuscript_type_id' INTO n;
    IF n > 0 THEN missing := missing || 'manuscript_type_id (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.manuscript_type_note IS NOT NULL AND m.manuscript_type_note IS DISTINCT FROM c.manuscript_type_note' INTO n;
    IF n > 0 THEN missing := missing || 'manuscript_type_note (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.general_notes IS NOT NULL AND m.general_notes IS DISTINCT FROM c.general_notes' INTO n;
    IF n > 0 THEN missing := missing || 'general_notes (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM manuscript m JOIN codex c USING (codex_id)
        WHERE m.shelfmark IS NOT NULL AND m.shelfmark IS DISTINCT FROM c.shelfmark' INTO n;
    IF n > 0 THEN missing := missing || 'shelfmark (' || n || ' manuscripts)'; END IF;

    EXECUTE 'SELECT count(*) FROM edition e JOIN publication p USING (publication_id)
        WHERE e.publication_year IS NOT NULL AND e.publication_year IS DISTINCT FROM p.publication_year' INTO n;
    IF n > 0 THEN missing := missing || 'edition.publication_year (' || n || ' editions)'; END IF;

    EXECUTE 'SELECT count(*) FROM edition e JOIN publication p USING (publication_id)
        WHERE e.reference IS NOT NULL AND e.reference IS DISTINCT FROM p.reference' INTO n;
    IF n > 0 THEN missing := missing || 'edition.reference (' || n || ' editions)'; END IF;
    IF cardinality(missing) > 0 THEN
        RAISE EXCEPTION
            'refusing to drop: these values are not present on codex/publication: %. '
            'Re-run 009/010 or investigate before dropping.',
            array_to_string(missing, ', ');
    END IF;
END
$$;

-- ---------------------------------------------------------------- drop ----

ALTER TABLE public.manuscript
    DROP COLUMN manuscript_preservation_status_id,
    DROP COLUMN location_id,
    DROP COLUMN manuscript_holding_institution_id,
    DROP COLUMN height,
    DROP COLUMN width,
    DROP COLUMN dating_century,
    DROP COLUMN dating_range_start,
    DROP COLUMN dating_range_end,
    DROP COLUMN dating_reference,
    DROP COLUMN dating_confidence_id,
    DROP COLUMN dating_note,
    DROP COLUMN codex_legendiers_usable,
    DROP COLUMN codex_composite,
    DROP COLUMN codex_legendiers_entry_code,
    DROP COLUMN codex_notes,
    DROP COLUMN vernacular_region_id,
    DROP COLUMN origin_archdiocese_id,
    DROP COLUMN origin_diocese_id,
    DROP COLUMN origin_diocese_confidence_rating_id,
    DROP COLUMN origin_institution_id,
    DROP COLUMN origin_institution_confidence_rating_id,
    DROP COLUMN provenance_early_institute_id,
    DROP COLUMN provenance_early_confidence_id,
    DROP COLUMN provenance_later_institute_id,
    DROP COLUMN provenance_later_confidence_id,
    DROP COLUMN origin_or_provenance_secondary_reference,
    DROP COLUMN manuscript_type_id,
    DROP COLUMN manuscript_type_note,
    DROP COLUMN general_notes,
    DROP COLUMN shelfmark,
    DROP COLUMN codex_number,
    DROP COLUMN codex_copy_amount,
    DROP COLUMN codex_multiple_copies;

ALTER TABLE public.edition
    DROP COLUMN publication_year,
    DROP COLUMN reference;
