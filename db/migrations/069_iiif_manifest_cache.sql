-- 069: a cache of the IIIF manifests the codices link to.
--
-- One row per manifest URL (a manifest on several codices is cached once),
-- with the full JSON and a few fields extracted from it. Filled by the IIIF
-- check (just db_iiif_check) whenever a manifest checks out OK, and by
-- just db_iiif_cache_import for manifests fetched in a browser (Gallica refuses
-- non-browser clients). ETag / Last-Modified let the check re-fetch with a
-- conditional request; a 304 keeps the cached copy.
--
-- It lives in hagio_admin, not public: it is a cache, not research data, so
-- it stays out of Mathesar (no 400 KB JSON cells in the researchers' tables)
-- and out of the SQLite export. Join it to public.codex_link on the URL:
--   codex_link.codex_link_url::text = iiif_manifest_cache.manifest_url
-- There is no foreign key, as the URL is not unique in codex_link (the same
-- manifest may be on several codices) and the cache may outlive a link.

CREATE TABLE IF NOT EXISTS hagio_admin.iiif_manifest_cache (
    manifest_url  text PRIMARY KEY,
    manifest      jsonb NOT NULL,
    iiif_version  smallint CHECK (iiif_version IN (2, 3)),
    label         text,
    canvas_count  integer,
    http_status   smallint,
    etag          text,
    last_modified text,
    fetched_via   text NOT NULL CHECK (fetched_via IN ('checker', 'browser')),
    fetched_at    timestamp with time zone NOT NULL DEFAULT now()
);

COMMENT ON TABLE hagio_admin.iiif_manifest_cache
    IS 'Cached IIIF manifests linked from public.codex_link (type ''IIIF manifest''), keyed by URL (migration 069)';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.manifest_url IS 'The manifest URL as stored in codex_link.codex_link_url';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.manifest IS 'The manifest as fetched';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.iiif_version IS 'IIIF Presentation API version: 2 or 3';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.label IS 'The manifest''s label, flattened to text';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.canvas_count IS 'Number of canvases (pages/images)';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.http_status IS 'HTTP status of the fetch that stored this copy';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.etag IS 'ETag response header, for conditional re-fetches';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.last_modified IS 'Last-Modified response header, for conditional re-fetches';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.fetched_via IS 'checker: just db_iiif_check; browser: fetched in a browser and imported';
COMMENT ON COLUMN hagio_admin.iiif_manifest_cache.fetched_at IS 'When this copy was fetched';
