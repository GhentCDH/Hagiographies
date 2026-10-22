-- 050: manuscript_link.url → manuscript_link_url, edition_link.url → edition_link_url.
--
-- The rest of the October 2026 relabelling (019–049) is plain renames, which
-- PostgreSQL carries through FKs, views, grants and the triggers' UPDATE OF
-- clauses by itself. These two columns are different: the file explorer's
-- trigger functions from 014 read them as NEW.url inside PL/pgSQL, and function
-- bodies are stored as text. A bare rename would make every insert or update on
-- either link table fail at runtime. So the renames and the replacement
-- functions go in one migration, i.e. one transaction.
--
-- The functions below are 014's, unchanged except for the column name. The
-- hagio_admin.*_link_reference tables keep their own url column: that is
-- hagio_admin's naming, not public's.

SELECT hagio_admin.rename_column('manuscript_link', 'url', 'manuscript_link_url');
SELECT hagio_admin.rename_column('edition_link', 'url', 'edition_link_url');

CREATE OR REPLACE FUNCTION hagio_admin.sync_manuscript_link_reference()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    target record;
BEGIN
    SELECT * INTO target
    FROM hagio_admin.resolve_link_target(NEW.manuscript_link_url::text);

    IF target.wanted_file IS NULL AND target.wanted_dir IS NULL THEN
        DELETE FROM hagio_admin.manuscript_link_reference
        WHERE manuscript_link_id = NEW.manuscript_link_id;
    ELSE
        INSERT INTO hagio_admin.manuscript_link_reference
            (manuscript_link_id, file_id, directory_id, url)
        VALUES (NEW.manuscript_link_id, target.wanted_file, target.wanted_dir,
                NEW.manuscript_link_url::text)
        ON CONFLICT (manuscript_link_id) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            directory_id = EXCLUDED.directory_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;  -- AFTER trigger; the return value is ignored
END
$function$;

CREATE OR REPLACE FUNCTION hagio_admin.sync_edition_link_reference()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    target record;
BEGIN
    SELECT * INTO target
    FROM hagio_admin.resolve_link_target(NEW.edition_link_url::text);

    IF target.wanted_file IS NULL AND target.wanted_dir IS NULL THEN
        DELETE FROM hagio_admin.edition_link_reference
        WHERE edition_link_id = NEW.edition_link_id;
    ELSE
        INSERT INTO hagio_admin.edition_link_reference
            (edition_link_id, file_id, directory_id, url)
        VALUES (NEW.edition_link_id, target.wanted_file, target.wanted_dir,
                NEW.edition_link_url::text)
        ON CONFLICT (edition_link_id) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            directory_id = EXCLUDED.directory_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;
END
$function$;
