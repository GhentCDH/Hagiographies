-- 014: directories become rows, and links can point at them.
--
-- Two changes that belong together.
--
-- First, links must be able to name a folder, not just a file: "the folder of
-- scans for this manuscript" is a thing researchers want in the database. Folders
-- therefore need their own stable UUIDs, served at /d/<uuid> the way files are
-- served at /f/<uuid>.
--
-- Second, 013 recorded where a file lives as a string, hagio_admin.file.relative_path,
-- and said the app rewrites it. That worked, but it means renaming one folder
-- rewrites every descendant row, and the app carries a pile of string surgery to
-- keep those paths right. Here a folder becomes a row in hagio_admin.directory
-- with a parent_id, and file points at one with directory_id. Renaming a folder is
-- then one UPDATE of one name, moving it is one UPDATE of one parent_id, and
-- nothing below it changes at all.
--
-- Full paths are derived from the tree by the directory_path and file_path views,
-- so there is exactly one truth about where something lives.
--
-- This migration is deliberately ADDITIVE. The binary running in production only
-- knows about relative_path, and it must keep working between this migration and
-- the deploy that follows it. So relative_path stays, and the new columns stay
-- nullable. 015 tightens them and drops the old column once the new binary is
-- live.
--
-- Deliberately NOT done here:
--
--   * directory rows are never deleted, for the same reason file rows are not: a
--     /d/ link may already be in the database. A folder that vanishes from the
--     share gets missing_since set.
--   * 013's single file_reference table is replaced by one table per source link
--     table. It recorded which row pointed at a file as a table NAME in a text
--     column plus an integer id, which is a foreign key in spirit and nothing in
--     fact: no constraint stopped a source_id that matched no row, and every
--     query had to filter on a string. One table per source gives a real FK to
--     the source row, and ON DELETE CASCADE then handles a deleted link row
--     without the trigger having to.
--
--     file_reference is derived data, rebuilt from the link tables by the trigger
--     and the backfill below, so replacing it loses nothing that cannot be
--     recomputed. That is why it can simply be dropped.

-- ----------------------------------------------------------- directory -------

CREATE TABLE hagio_admin.directory (
    directory_id  uuid NOT NULL DEFAULT gen_random_uuid(),
    parent_id     uuid,
    name          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    missing_since timestamptz
);

ALTER TABLE ONLY hagio_admin.directory
    ADD CONSTRAINT directory_pkey PRIMARY KEY (directory_id);

ALTER TABLE ONLY hagio_admin.directory
    ADD CONSTRAINT directory_parent_id_fkey FOREIGN KEY (parent_id)
    REFERENCES hagio_admin.directory(directory_id);

-- The share root is the one row with no parent and no name. Everything else has
-- both.
ALTER TABLE ONLY hagio_admin.directory
    ADD CONSTRAINT directory_root_shape_check
    CHECK ((parent_id IS NULL) = (name IS NULL));

-- NULLS NOT DISTINCT is load-bearing, not a flourish: a plain UNIQUE treats
-- (NULL, NULL) as distinct from itself, so it would happily allow a second root.
-- Needs PostgreSQL 15 or newer; the servers run 17.
ALTER TABLE ONLY hagio_admin.directory
    ADD CONSTRAINT directory_parent_id_name_key
    UNIQUE NULLS NOT DISTINCT (parent_id, name);

CREATE INDEX ix_directory_parent_id
    ON hagio_admin.directory USING btree (parent_id);

COMMENT ON TABLE hagio_admin.directory
    IS 'One folder on the network share, tracked by UUIDv4 and linkable at /d/<directory_id>. A tree: parent_id points at the folder above, and the single row with parent_id IS NULL is the share root itself.';
COMMENT ON COLUMN hagio_admin.directory.directory_id
    IS 'UUIDv4. The stable identity of the folder: it is what appears in the URL, so it survives renames and moves.';
COMMENT ON COLUMN hagio_admin.directory.parent_id
    IS 'The folder this one sits in. NULL only for the share root. Moving a folder is an update of this column and nothing else.';
COMMENT ON COLUMN hagio_admin.directory.name
    IS 'The folder''s own name, not its path. NULL only for the share root. Renaming a folder is an update of this column and nothing else.';
COMMENT ON COLUMN hagio_admin.directory.missing_since
    IS 'When a scan first found this folder gone from the share. NULL while it is present. The row is kept regardless, because /d/ links to this directory_id may already exist in the database.';

INSERT INTO hagio_admin.directory (parent_id, name) VALUES (NULL, NULL);

-- --------------------------------------------------------------- paths -------

-- Paths are derived, never stored. These two views are the only place that knows
-- how a path is spelled, which is what makes a rename a single-row update.

CREATE VIEW hagio_admin.directory_path AS
WITH RECURSIVE walk AS (
    SELECT d.directory_id, ''::text AS relative_path
    FROM hagio_admin.directory d
    WHERE d.parent_id IS NULL
  UNION ALL
    SELECT d.directory_id,
           CASE WHEN w.relative_path = '' THEN d.name
                ELSE w.relative_path || '/' || d.name
           END
    FROM hagio_admin.directory d
    JOIN walk w ON d.parent_id = w.directory_id
)
SELECT directory_id, relative_path FROM walk;

COMMENT ON VIEW hagio_admin.directory_path
    IS 'Every folder with its path relative to the share root, walked down from the root. The root itself is the empty string.';

-- ------------------------------------------------------ file.directory_id ----

-- Nullable, and relative_path stays NOT NULL-free rather than being dropped,
-- because the binary in production writes only relative_path and has to survive
-- until it is replaced. 015 does the tightening.
ALTER TABLE hagio_admin.file ALTER COLUMN relative_path DROP NOT NULL;

ALTER TABLE hagio_admin.file ADD COLUMN directory_id uuid;
ALTER TABLE hagio_admin.file ADD COLUMN name text;

ALTER TABLE ONLY hagio_admin.file
    ADD CONSTRAINT file_directory_id_fkey FOREIGN KEY (directory_id)
    REFERENCES hagio_admin.directory(directory_id);

-- Added now rather than in 015 because the new binary needs it as an ON CONFLICT
-- target from its very first request. Safe while the columns are nullable: under
-- the default NULLS DISTINCT the old binary's (NULL, NULL) rows never collide.
ALTER TABLE ONLY hagio_admin.file
    ADD CONSTRAINT file_directory_id_name_key UNIQUE (directory_id, name);

CREATE INDEX ix_file_directory_id
    ON hagio_admin.file USING btree (directory_id);

COMMENT ON COLUMN hagio_admin.file.directory_id
    IS 'The folder this file sits in. Moving a file is an update of this column.';
COMMENT ON COLUMN hagio_admin.file.name
    IS 'The file''s own name, not its path. Renaming a file is an update of this column.';
COMMENT ON COLUMN hagio_admin.file.relative_path
    IS 'DEPRECATED, dropped by migration 015. Superseded by directory_id plus name; read hagio_admin.file_path instead.';

CREATE VIEW hagio_admin.file_path AS
SELECT f.file_id,
       f.directory_id,
       CASE WHEN p.relative_path = '' THEN f.name
            ELSE p.relative_path || '/' || f.name
       END AS relative_path
FROM hagio_admin.file f
JOIN hagio_admin.directory_path p USING (directory_id);

COMMENT ON VIEW hagio_admin.file_path
    IS 'Every file with its path relative to the share root, assembled from the directory tree. Replaces the old hagio_admin.file.relative_path column.';

-- ------------------------------------------------------------ backfill -------

-- Rebuild the tree from the paths 013 recorded. Two steps: work out every folder
-- that those paths imply, then point each file at the right one.
--
-- A plain temp table rather than ON COMMIT DROP, so this file also runs under a
-- psql -f that is not wrapped in a transaction.

CREATE TEMP TABLE ancestor_path AS
WITH file_dirs AS (
    SELECT DISTINCT
           CASE WHEN relative_path LIKE '%/%'
                THEN regexp_replace(relative_path, '/[^/]*$', '')
                ELSE ''
           END AS dir
    FROM hagio_admin.file
    WHERE relative_path IS NOT NULL
),
-- A file at a/b/c.pdf implies both 'a' and 'a/b', so expand every folder path
-- into all of its own prefixes.
expanded AS (
    SELECT DISTINCT array_to_string(s.parts[1:n], '/') AS dir
    FROM (
        SELECT string_to_array(dir, '/') AS parts
        FROM file_dirs
        WHERE dir <> ''
    ) s,
    generate_series(1, cardinality(s.parts)) AS n
)
SELECT dir, cardinality(string_to_array(dir, '/')) AS depth FROM expanded;

-- One level per pass, each resolving its parent through directory_path, which
-- sees the rows the previous pass inserted. A recursive CTE cannot do this: they
-- are not allowed to modify data.
DO $$
DECLARE
    max_depth int;
    d         int;
BEGIN
    SELECT coalesce(max(depth), 0) INTO max_depth FROM ancestor_path;

    FOR d IN 1..max_depth LOOP
        INSERT INTO hagio_admin.directory (parent_id, name)
        SELECT parent.directory_id, seg.name
        FROM (
            SELECT DISTINCT
                   array_to_string((string_to_array(a.dir, '/'))[1:d - 1], '/') AS parent_path,
                   (string_to_array(a.dir, '/'))[d] AS name
            FROM ancestor_path a
            WHERE a.depth >= d
        ) seg
        JOIN hagio_admin.directory_path parent
             ON parent.relative_path = seg.parent_path
        ON CONFLICT (parent_id, name) DO NOTHING;
    END LOOP;
END
$$;

UPDATE hagio_admin.file f
SET directory_id = p.directory_id,
    name = regexp_replace(f.relative_path, '^.*/', ''),
    updated_at = now()
FROM hagio_admin.directory_path p
WHERE f.relative_path IS NOT NULL
  AND p.relative_path = CASE WHEN f.relative_path LIKE '%/%'
                             THEN regexp_replace(f.relative_path, '/[^/]*$', '')
                             ELSE ''
                        END;

-- ------------------------------------------------------------ guard ----------

DO $$
DECLARE
    stragglers text;
    mismatched text;
BEGIN
    SELECT string_agg(relative_path, ', ')
    INTO stragglers
    FROM hagio_admin.file
    WHERE relative_path IS NOT NULL
      AND (directory_id IS NULL OR name IS NULL);

    IF stragglers IS NOT NULL THEN
        RAISE EXCEPTION
            'could not place these files in the directory tree: %. '
            'Investigate before continuing; the tree must be complete.',
            stragglers;
    END IF;

    -- The strongest check available that the tree really reproduces the paths it
    -- was built from.
    SELECT string_agg(f.relative_path || ' -> ' || p.relative_path, ', ')
    INTO mismatched
    FROM hagio_admin.file f
    JOIN hagio_admin.file_path p USING (file_id)
    WHERE f.relative_path IS NOT NULL
      AND p.relative_path <> f.relative_path;

    IF mismatched IS NOT NULL THEN
        RAISE EXCEPTION
            'the rebuilt tree disagrees with the recorded paths: %.',
            mismatched;
    END IF;
END
$$;

DROP TABLE ancestor_path;

-- Folders holding no files anywhere below them leave no trace in the paths above,
-- so they are not in the tree yet. The app's first full scan adds them.

-- -------------------------------------------------- reference tables ---------

-- One table per source, so both ends are real foreign keys: the source row, and
-- whichever of file or directory the URL named.
--
-- The target is an exclusive arc, a nullable FK each with a CHECK that exactly one
-- is set. That is still two real constraints; the thing 013 got wrong was the
-- source side, where the table was named in a text column.

DROP VIEW hagio_admin.file_reference_unresolved;
DROP TABLE hagio_admin.file_reference;

CREATE TABLE hagio_admin.manuscript_link_reference (
    manuscript_link_id integer NOT NULL,
    file_id            uuid,
    directory_id       uuid,
    url                text NOT NULL,
    updated_at         timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ONLY hagio_admin.manuscript_link_reference
    ADD CONSTRAINT manuscript_link_reference_pkey PRIMARY KEY (manuscript_link_id);

-- The point of the redesign: a real FK to the row that holds the link, so a
-- deleted link takes its reference with it and the trigger needs no DELETE branch.
ALTER TABLE ONLY hagio_admin.manuscript_link_reference
    ADD CONSTRAINT manuscript_link_reference_manuscript_link_id_fkey
    FOREIGN KEY (manuscript_link_id)
    REFERENCES public.manuscript_link(manuscript_link_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.manuscript_link_reference
    ADD CONSTRAINT manuscript_link_reference_file_id_fkey FOREIGN KEY (file_id)
    REFERENCES hagio_admin.file(file_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.manuscript_link_reference
    ADD CONSTRAINT manuscript_link_reference_directory_id_fkey FOREIGN KEY (directory_id)
    REFERENCES hagio_admin.directory(directory_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.manuscript_link_reference
    ADD CONSTRAINT manuscript_link_reference_target_check
    CHECK ((file_id IS NULL) <> (directory_id IS NULL));

CREATE INDEX ix_manuscript_link_reference_file_id
    ON hagio_admin.manuscript_link_reference USING btree (file_id);
CREATE INDEX ix_manuscript_link_reference_directory_id
    ON hagio_admin.manuscript_link_reference USING btree (directory_id);

CREATE TABLE hagio_admin.edition_link_reference (
    edition_link_id integer NOT NULL,
    file_id         uuid,
    directory_id    uuid,
    url             text NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ONLY hagio_admin.edition_link_reference
    ADD CONSTRAINT edition_link_reference_pkey PRIMARY KEY (edition_link_id);

ALTER TABLE ONLY hagio_admin.edition_link_reference
    ADD CONSTRAINT edition_link_reference_edition_link_id_fkey
    FOREIGN KEY (edition_link_id)
    REFERENCES public.edition_link(edition_link_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.edition_link_reference
    ADD CONSTRAINT edition_link_reference_file_id_fkey FOREIGN KEY (file_id)
    REFERENCES hagio_admin.file(file_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.edition_link_reference
    ADD CONSTRAINT edition_link_reference_directory_id_fkey FOREIGN KEY (directory_id)
    REFERENCES hagio_admin.directory(directory_id) ON DELETE CASCADE;

ALTER TABLE ONLY hagio_admin.edition_link_reference
    ADD CONSTRAINT edition_link_reference_target_check
    CHECK ((file_id IS NULL) <> (directory_id IS NULL));

CREATE INDEX ix_edition_link_reference_file_id
    ON hagio_admin.edition_link_reference USING btree (file_id);
CREATE INDEX ix_edition_link_reference_directory_id
    ON hagio_admin.edition_link_reference USING btree (directory_id);

COMMENT ON TABLE hagio_admin.manuscript_link_reference
    IS 'Which manuscript_link rows point at a file or folder on the share. Derived, never edited by hand: maintained by a trigger on public.manuscript_link. Answers "what cites this file?" and "which files are unused?".';
COMMENT ON TABLE hagio_admin.edition_link_reference
    IS 'Which edition_link rows point at a file or folder on the share. Derived, never edited by hand: maintained by a trigger on public.edition_link.';
COMMENT ON COLUMN hagio_admin.manuscript_link_reference.file_id
    IS 'The file this link points at, for an /f/ URL. Exactly one of file_id and directory_id is set.';
COMMENT ON COLUMN hagio_admin.manuscript_link_reference.directory_id
    IS 'The folder this link points at, for a /d/ URL. Exactly one of file_id and directory_id is set.';
COMMENT ON COLUMN hagio_admin.manuscript_link_reference.url
    IS 'The URL as stored in the source row, for debugging. The authoritative target is file_id or directory_id.';
COMMENT ON COLUMN hagio_admin.edition_link_reference.file_id
    IS 'The file this link points at, for an /f/ URL. Exactly one of file_id and directory_id is set.';
COMMENT ON COLUMN hagio_admin.edition_link_reference.directory_id
    IS 'The folder this link points at, for a /d/ URL. Exactly one of file_id and directory_id is set.';
COMMENT ON COLUMN hagio_admin.edition_link_reference.url
    IS 'The URL as stored in the source row, for debugging. The authoritative target is file_id or directory_id.';

-- ---------------------------------------------------------- extraction -------

-- The /f/ and /d/ URLs differ by one letter, so the regex lives in one place and
-- the two public functions differ only in which segment they ask for. Both read
-- the same file_link_host table: it is the same host serving both.

CREATE FUNCTION hagio_admin.link_uuid(candidate text, segment text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    -- Both halves must match: the /<segment>/<uuid> shape AND a configured host.
    -- Anything else is just some other URL a researcher put in the cell (the
    -- Légendiers and catalogue links already in these columns). The port is
    -- stripped, the host lowercased, and a trailing path, query or fragment
    -- (e.g. '?download=1') is tolerated.
    SELECT (m[2])::uuid
    FROM regexp_match(
             btrim(candidate),
             '^https?://([^/:]+)(?::[0-9]+)?/' || segment ||
             '/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:[/?#].*)?$'
         ) AS m
    WHERE EXISTS (
        SELECT 1 FROM hagio_admin.file_link_host h WHERE h.host = lower(m[1])
    );
$$;

COMMENT ON FUNCTION hagio_admin.link_uuid(text, text)
    IS 'The UUID a URL names under /<segment>/, or NULL if it is not that shape on a configured host. Says nothing about whether the UUID exists.';

CREATE OR REPLACE FUNCTION hagio_admin.file_id_from_url(candidate text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    SELECT hagio_admin.link_uuid(candidate, 'f');
$$;

CREATE FUNCTION hagio_admin.directory_id_from_url(candidate text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    SELECT hagio_admin.link_uuid(candidate, 'd');
$$;

COMMENT ON FUNCTION hagio_admin.directory_id_from_url(text)
    IS 'The directory_id a URL points at, or NULL if it is not a /d/<uuid> URL on a configured host. Says nothing about whether that directory_id exists.';

-- -------------------------------------------------------------- trigger ------

-- Resolving what a URL names is the shared half; writing it is per table, because
-- each reference table has its own real foreign key to its own source.

CREATE FUNCTION hagio_admin.resolve_link_target(
    candidate text,
    OUT wanted_file uuid,
    OUT wanted_dir uuid
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    wanted_file := hagio_admin.file_id_from_url(candidate);
    IF wanted_file IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM hagio_admin.file f WHERE f.file_id = wanted_file
    ) THEN
        wanted_file := NULL;
    END IF;

    IF wanted_file IS NOT NULL THEN
        RETURN;
    END IF;

    wanted_dir := hagio_admin.directory_id_from_url(candidate);
    IF wanted_dir IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM hagio_admin.directory d WHERE d.directory_id = wanted_dir
    ) THEN
        wanted_dir := NULL;
    END IF;
END
$$;

COMMENT ON FUNCTION hagio_admin.resolve_link_target(text)
    IS 'What a link URL names: an existing file, an existing folder, or neither. A UUID that does not exist comes back NULL, so the caller records nothing rather than rejecting the edit.';

-- SECURITY DEFINER is load-bearing, not decoration: the researchers edit these
-- columns through Mathesar as hagiographies_editor, which has no USAGE on
-- hagio_admin. Without it every such edit would fail with "permission denied for
-- schema hagio_admin".
--
-- Neither trigger handles DELETE. It no longer has to: the FK from the reference
-- table to the link table cascades, which is a nice dividend of using a real
-- foreign key instead of an integer and a table name.
--
-- Neither trigger raises either. A UUID that does not exist is recorded as
-- unresolved (see the view below) rather than rejected: a researcher pasting a
-- typo'd link should get their edit saved and a chance to notice, not an error
-- dialog from a table they cannot see.

CREATE OR REPLACE FUNCTION hagio_admin.sync_manuscript_link_reference()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    target record;
BEGIN
    SELECT * INTO target FROM hagio_admin.resolve_link_target(NEW.url::text);

    IF target.wanted_file IS NULL AND target.wanted_dir IS NULL THEN
        DELETE FROM hagio_admin.manuscript_link_reference
        WHERE manuscript_link_id = NEW.manuscript_link_id;
    ELSE
        INSERT INTO hagio_admin.manuscript_link_reference
            (manuscript_link_id, file_id, directory_id, url)
        VALUES (NEW.manuscript_link_id, target.wanted_file, target.wanted_dir,
                NEW.url::text)
        ON CONFLICT (manuscript_link_id) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            directory_id = EXCLUDED.directory_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;  -- AFTER trigger; the return value is ignored
END
$$;

CREATE OR REPLACE FUNCTION hagio_admin.sync_edition_link_reference()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    target record;
BEGIN
    SELECT * INTO target FROM hagio_admin.resolve_link_target(NEW.url::text);

    IF target.wanted_file IS NULL AND target.wanted_dir IS NULL THEN
        DELETE FROM hagio_admin.edition_link_reference
        WHERE edition_link_id = NEW.edition_link_id;
    ELSE
        INSERT INTO hagio_admin.edition_link_reference
            (edition_link_id, file_id, directory_id, url)
        VALUES (NEW.edition_link_id, target.wanted_file, target.wanted_dir,
                NEW.url::text)
        ON CONFLICT (edition_link_id) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            directory_id = EXCLUDED.directory_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;
END
$$;

COMMENT ON FUNCTION hagio_admin.sync_manuscript_link_reference()
    IS 'Keeps hagio_admin.manuscript_link_reference in step with manuscript_link.url, for both /f/ file links and /d/ folder links.';
COMMENT ON FUNCTION hagio_admin.sync_edition_link_reference()
    IS 'Keeps hagio_admin.edition_link_reference in step with edition_link.url, for both /f/ file links and /d/ folder links.';

-- 013's triggers and its one shared function go: the reference tables they wrote
-- to no longer exist.
DROP TRIGGER manuscript_link_sync_file_reference ON public.manuscript_link;
DROP TRIGGER edition_link_sync_file_reference ON public.edition_link;
DROP FUNCTION hagio_admin.sync_file_reference();

CREATE TRIGGER manuscript_link_sync_reference
    AFTER INSERT OR UPDATE OF url ON public.manuscript_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.sync_manuscript_link_reference();

CREATE TRIGGER edition_link_sync_reference
    AFTER INSERT OR UPDATE OF url ON public.edition_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.sync_edition_link_reference();

-- ----------------------------------------------------------------- view ------

CREATE VIEW hagio_admin.link_reference_unresolved AS
WITH links AS (
    SELECT 'manuscript_link' AS source_table, l.manuscript_link_id AS source_id,
           l.url::text AS url
    FROM public.manuscript_link l
  UNION ALL
    SELECT 'edition_link' AS source_table, l.edition_link_id AS source_id,
           l.url::text AS url
    FROM public.edition_link l
),
wanted AS (
    SELECT source_table, source_id, url,
           hagio_admin.file_id_from_url(url) AS file_id,
           hagio_admin.directory_id_from_url(url) AS directory_id
    FROM links
)
SELECT source_table,
       source_id,
       url,
       CASE WHEN file_id IS NOT NULL THEN 'file' ELSE 'directory' END AS kind,
       coalesce(file_id, directory_id) AS target_id
FROM wanted
WHERE (file_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM hagio_admin.file f WHERE f.file_id = wanted.file_id))
   OR (directory_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM hagio_admin.directory d WHERE d.directory_id = wanted.directory_id));

COMMENT ON VIEW hagio_admin.link_reference_unresolved
    IS 'Link rows that look like one of our links but name a UUID that does not exist: typos, or files and folders whose row was never created. kind says which of the two shapes the URL used. Naming the source table in a text column is fine here, unlike in a stored table: this is a report over both, not a relationship.';

-- ------------------------------------------------------------- backfill ------

-- Rebuild both tables from the link columns. This is also what makes dropping
-- 013's file_reference safe: everything in it is recomputed here.

INSERT INTO hagio_admin.manuscript_link_reference
    (manuscript_link_id, file_id, directory_id, url)
SELECT l.manuscript_link_id, t.wanted_file, t.wanted_dir, l.url::text
FROM public.manuscript_link l
CROSS JOIN LATERAL hagio_admin.resolve_link_target(l.url::text) AS t
WHERE t.wanted_file IS NOT NULL OR t.wanted_dir IS NOT NULL
ON CONFLICT (manuscript_link_id) DO NOTHING;

INSERT INTO hagio_admin.edition_link_reference
    (edition_link_id, file_id, directory_id, url)
SELECT l.edition_link_id, t.wanted_file, t.wanted_dir, l.url::text
FROM public.edition_link l
CROSS JOIN LATERAL hagio_admin.resolve_link_target(l.url::text) AS t
WHERE t.wanted_file IS NOT NULL OR t.wanted_dir IS NOT NULL
ON CONFLICT (edition_link_id) DO NOTHING;
