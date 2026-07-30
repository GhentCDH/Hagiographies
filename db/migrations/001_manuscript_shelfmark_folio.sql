-- 001: the two MANUSCRIPTS columns that never made it into the database.
--
-- MANUSCRIPTS!Q 'Manuscript shelfmark' and MANUSCRIPTS!R 'Folio or page range'.
-- Column comments follow the convention the importer's excel_field() set, so
-- the source column stays visible in \d+ and in Mathesar.

ALTER TABLE public.manuscript ADD COLUMN shelfmark character varying;
ALTER TABLE public.manuscript ADD COLUMN folio_or_page_range character varying;

COMMENT ON COLUMN public.manuscript.shelfmark
    IS 'Excel MANUSCRIPTS → ''Manuscript shelfmark''';
COMMENT ON COLUMN public.manuscript.folio_or_page_range
    IS 'Excel MANUSCRIPTS → ''Folio or page range''';
