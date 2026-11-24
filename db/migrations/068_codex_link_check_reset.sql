-- 068: editing a codex link's URL or type clears its IIIF check result.
--
-- codex_link_checked_at / codex_link_check_note (067) describe the URL that
-- was fetched. Once a researcher changes the URL or the link type in
-- Mathesar, that result no longer applies, so it is cleared. The link then
-- reads as never checked, and just db_iiif_check --only unchecked picks it up.
--
-- The trigger function lives in hagio_admin, like the file explorer's, so that
-- public holds research data only. A BEFORE trigger only edits NEW, so it
-- needs no SECURITY DEFINER; editors fire it like any trigger on the table.

CREATE OR REPLACE FUNCTION hagio_admin.reset_codex_link_check()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    IF NEW.codex_link_url IS DISTINCT FROM OLD.codex_link_url
       OR NEW.codex_link_type_id IS DISTINCT FROM OLD.codex_link_type_id THEN
        NEW.codex_link_checked_at := NULL;
        NEW.codex_link_check_note := NULL;
    END IF;
    RETURN NEW;
END
$function$;

COMMENT ON FUNCTION hagio_admin.reset_codex_link_check()
    IS 'Clears codex_link_checked_at/_check_note when a link''s URL or type changes (migration 068).';

DROP TRIGGER IF EXISTS codex_link_reset_check ON public.codex_link;
CREATE TRIGGER codex_link_reset_check
    BEFORE UPDATE OF codex_link_url, codex_link_type_id ON public.codex_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.reset_codex_link_check();
