-- 067: when a codex link was last checked, and what the check found.
--
-- Filled by the IIIF check (just db_iiif_check), which fetches every
-- 'IIIF manifest' link politely (at most one request per second per host) and
-- does a light format check. Empty for links that were never checked; the
-- other link types are not checked (yet).
--
-- codex_link_note stays the researchers' own note; the check never writes it.

ALTER TABLE public.codex_link ADD COLUMN IF NOT EXISTS codex_link_checked_at timestamp with time zone;
ALTER TABLE public.codex_link ADD COLUMN IF NOT EXISTS codex_link_check_note character varying;

COMMENT ON COLUMN public.codex_link.codex_link_checked_at
    IS 'When the IIIF check last fetched this link (empty: never checked)';
COMMENT ON COLUMN public.codex_link.codex_link_check_note
    IS 'Result of the last IIIF check: OK (IIIF v2/v3), HTTP error, unreachable, not JSON, not a IIIF manifest, …';
