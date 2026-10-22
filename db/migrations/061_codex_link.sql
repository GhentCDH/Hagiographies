-- 061: manuscript_link → codex_link: the links belong to the codex, not the copy.
--
-- The workbook stored its catalogue, Légendiers, IIIF and scan links on every
-- text copy (manuscript) of a codex, so the same codex link was repeated once
-- per copy. On PRD (2026-10-22): 3890 rows, but only 2390 distinct
-- (codex, type, url). This migration
--
--   1. renames the table and its columns (codex_link_id, codex_link_type_id,
--      codex_link_url, codex_link_note);
--   2. replaces manuscript_id with codex_id, taken from manuscript.codex_id;
--   3. merges the repeats: one row per (codex, type, url) is kept (lowest id),
--      and the distinct non-empty notes of the group are joined with ' | ',
--      so no note is lost;
--   4. adds UNIQUE (codex_id, codex_link_type_id, codex_link_url);
--   5. renames the file explorer's side to match: hagio_admin.codex_link_reference,
--      hagio_admin.sync_codex_link_reference() and its trigger. The function
--      body names the columns, so it is replaced, not just renamed. The
--      file-explorer binary reads codex_link_reference and must be deployed
--      together with this migration.
--
-- Reference rows of merged-away copies are removed by their ON DELETE CASCADE.
-- Their kept twin has the same URL and so keeps its own reference.
--
-- It refuses rather than guesses: a link whose manuscript has no codex aborts
-- the migration and is listed (PRD had none).

-- ------------------------------------------------------------- renames ------

SELECT hagio_admin.rename_table('manuscript_link', 'codex_link');
SELECT hagio_admin.rename_column('codex_link', 'manuscript_link_id', 'codex_link_id');
SELECT hagio_admin.rename_column('codex_link', 'manuscript_link_type_id', 'codex_link_type_id');
SELECT hagio_admin.rename_column('codex_link', 'manuscript_link_url', 'codex_link_url');
SELECT hagio_admin.rename_column('codex_link', 'manuscript_link_note', 'codex_link_note');
SELECT hagio_admin.rename_constraint('codex_link', 'manuscript_link_pkey', 'codex_link_pkey');
SELECT hagio_admin.rename_constraint('codex_link', 'manuscript_link_manuscript_link_type_id_fkey', 'codex_link_codex_link_type_id_fkey');
SELECT hagio_admin.rename_sequence('manuscript_link_manuscript_link_id_seq', 'codex_link_codex_link_id_seq');

-- ------------------------------------------------ manuscript_id → codex_id ---

ALTER TABLE public.codex_link ADD COLUMN codex_id integer;

UPDATE public.codex_link l
   SET codex_id = m.codex_id
  FROM public.manuscript m
 WHERE m.manuscript_id = l.manuscript_id;

DO $$
DECLARE
    orphans text;
BEGIN
    SELECT string_agg(format('codex_link %s (manuscript %s)', l.codex_link_id,
                             m.manuscript_unique_identifier), E'\n')
      INTO orphans
      FROM public.codex_link l
      LEFT JOIN public.manuscript m ON m.manuscript_id = l.manuscript_id
     WHERE l.codex_id IS NULL;
    IF orphans IS NOT NULL THEN
        RAISE EXCEPTION E'links on manuscripts without a codex; give them a codex in Mathesar first:\n%', orphans;
    END IF;
END
$$;

-- -------------------------------------------------- merge repeated links ----

DO $$
DECLARE
    removed bigint;
BEGIN
    CREATE TEMP TABLE codex_link_group ON COMMIT DROP AS
    SELECT codex_id, codex_link_type_id, codex_link_url::text AS url,
           min(codex_link_id) AS keep_id,
           string_agg(DISTINCT nullif(btrim(codex_link_note), ''), ' | '
                      ORDER BY nullif(btrim(codex_link_note), '')) AS notes
      FROM public.codex_link
     GROUP BY 1, 2, 3
    HAVING count(*) > 1;

    UPDATE public.codex_link l
       SET codex_link_note = g.notes
      FROM codex_link_group g
     WHERE l.codex_link_id = g.keep_id
       AND l.codex_link_note IS DISTINCT FROM g.notes;

    DELETE FROM public.codex_link l
     USING codex_link_group g
     WHERE l.codex_id = g.codex_id
       AND l.codex_link_type_id = g.codex_link_type_id
       AND l.codex_link_url::text = g.url
       AND l.codex_link_id <> g.keep_id;
    GET DIAGNOSTICS removed = ROW_COUNT;
    RAISE NOTICE 'codex_link: % repeated rows merged into their codex-level link', removed;
END
$$;

ALTER TABLE public.codex_link ALTER COLUMN codex_id SET NOT NULL;
ALTER TABLE public.codex_link
    ADD CONSTRAINT codex_link_codex_id_fkey FOREIGN KEY (codex_id) REFERENCES public.codex (codex_id);
CREATE INDEX ix_codex_link_codex_id ON public.codex_link (codex_id);
COMMENT ON COLUMN public.codex_link.codex_id
    IS 'The codex this link describes (moved from manuscript level in migration 061)';

-- Drops its FK and ix_manuscript_link_manuscript_id with it.
ALTER TABLE public.codex_link DROP COLUMN manuscript_id;

ALTER TABLE public.codex_link
    ADD CONSTRAINT codex_link_codex_id_codex_link_type_id_codex_link_url_key
    UNIQUE (codex_id, codex_link_type_id, codex_link_url);

-- ------------------------------------------- file explorer (hagio_admin) ----

ALTER TABLE hagio_admin.manuscript_link_reference RENAME TO codex_link_reference;
ALTER TABLE hagio_admin.codex_link_reference RENAME COLUMN manuscript_link_id TO codex_link_id;
ALTER TABLE hagio_admin.codex_link_reference
    RENAME CONSTRAINT manuscript_link_reference_pkey TO codex_link_reference_pkey;
ALTER TABLE hagio_admin.codex_link_reference
    RENAME CONSTRAINT manuscript_link_reference_target_check TO codex_link_reference_target_check;
ALTER TABLE hagio_admin.codex_link_reference
    RENAME CONSTRAINT manuscript_link_reference_file_id_fkey TO codex_link_reference_file_id_fkey;
ALTER TABLE hagio_admin.codex_link_reference
    RENAME CONSTRAINT manuscript_link_reference_directory_id_fkey TO codex_link_reference_directory_id_fkey;
ALTER TABLE hagio_admin.codex_link_reference
    RENAME CONSTRAINT manuscript_link_reference_manuscript_link_id_fkey TO codex_link_reference_codex_link_id_fkey;
ALTER INDEX hagio_admin.ix_manuscript_link_reference_file_id RENAME TO ix_codex_link_reference_file_id;
ALTER INDEX hagio_admin.ix_manuscript_link_reference_directory_id RENAME TO ix_codex_link_reference_directory_id;

COMMENT ON TABLE hagio_admin.codex_link_reference
    IS 'Which codex_link rows point at a file or folder on the share. Derived, never edited by hand: maintained by a trigger on public.codex_link. Answers "what cites this file?" and "which files are unused?".';

DROP TRIGGER manuscript_link_sync_reference ON public.codex_link;
DROP FUNCTION hagio_admin.sync_manuscript_link_reference();

-- 050's function, with the codex names.
CREATE FUNCTION hagio_admin.sync_codex_link_reference()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    target record;
BEGIN
    SELECT * INTO target
    FROM hagio_admin.resolve_link_target(NEW.codex_link_url::text);

    IF target.wanted_file IS NULL AND target.wanted_dir IS NULL THEN
        DELETE FROM hagio_admin.codex_link_reference
        WHERE codex_link_id = NEW.codex_link_id;
    ELSE
        INSERT INTO hagio_admin.codex_link_reference
            (codex_link_id, file_id, directory_id, url)
        VALUES (NEW.codex_link_id, target.wanted_file, target.wanted_dir,
                NEW.codex_link_url::text)
        ON CONFLICT (codex_link_id) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            directory_id = EXCLUDED.directory_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;  -- AFTER trigger; the return value is ignored
END
$function$;

COMMENT ON FUNCTION hagio_admin.sync_codex_link_reference()
    IS 'Keeps hagio_admin.codex_link_reference in step with codex_link.codex_link_url, for both /f/ file links and /d/ folder links.';

CREATE TRIGGER codex_link_sync_reference
    AFTER INSERT OR UPDATE OF codex_link_url ON public.codex_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.sync_codex_link_reference();

-- Same view, with the source table now called codex_link.
CREATE OR REPLACE VIEW hagio_admin.link_reference_unresolved AS
 WITH links AS (
         SELECT 'codex_link'::text AS source_table,
            l.codex_link_id AS source_id,
            l.codex_link_url::text AS url
           FROM public.codex_link l
        UNION ALL
         SELECT 'edition_link'::text AS source_table,
            l.edition_link_id AS source_id,
            l.edition_link_url::text AS url
           FROM public.edition_link l
        ), wanted AS (
         SELECT links.source_table,
            links.source_id,
            links.url,
            hagio_admin.file_id_from_url(links.url) AS file_id,
            hagio_admin.directory_id_from_url(links.url) AS directory_id
           FROM links
        )
 SELECT source_table,
    source_id,
    url,
        CASE
            WHEN file_id IS NOT NULL THEN 'file'::text
            ELSE 'directory'::text
        END AS kind,
    COALESCE(file_id, directory_id) AS target_id
   FROM wanted
  WHERE file_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM hagio_admin.file f
          WHERE f.file_id = wanted.file_id)) OR directory_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM hagio_admin.directory d
          WHERE d.directory_id = wanted.directory_id));
