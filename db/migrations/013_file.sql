-- 013: tracked files on the network share, and their links from the database.
--
-- The scanned manuscript and edition images live on a UGent network share, not
-- in the database. Job students need to put working links to them into
-- manuscript_link.url and edition_link.url from Mathesar, without mounting the
-- share. file-explorer/ (an Axum + Svelte web app deployed at
-- https://files.m-patch.ugent.be) is the managed interface over that share;
-- this migration is the database half of it.
--
-- Three tables, all in hagio_admin rather than public, for the reason already
-- stated in db/src/hagio_db/migrate.py: public holds research data and nothing
-- else, so Mathesar shows the researchers their tables and not our plumbing.
-- hagiographies_editor has no USAGE on hagio_admin (007_editor_role_grants.sql)
-- and therefore cannot see any of this, which is deliberate. Students reach
-- files through the web app, not through Mathesar.
--
-- Every file is addressed by a UUIDv4 and served at /f/<uuid>. The UUID, not
-- the path, is what goes into the database, so renaming or moving a file on the
-- share, or renaming a whole top-level directory, does not break a single
-- link already pasted into Mathesar. hagio_admin.file.relative_path is then
-- free to change, and the app rewrites it.
--
-- Deliberately NOT done here:
--
--   * No grants. The web app connects as the owner role
--     (hagiographies_admin on the servers). A dedicated app role would be
--     tidier, but the migration runner has NOCREATEROLE and cannot create one,
--     and the app already sits behind Caddy authentication. If a role is ever
--     created by hand, grant it USAGE on hagio_admin plus DML on these tables
--     in a later migration.
--   * No view in public exposing file_reference to the researchers. Add one if
--     they ask to see it in Mathesar.
--   * file rows are never deleted, not even when the file vanishes from the
--     share: a link to it may already be in the database, and a dangling
--     file_reference is more useful than a silently missing one. missing_since
--     records the disappearance instead.

-- ---------------------------------------------------------------- file -------

CREATE TABLE hagio_admin.file (
    file_id       uuid NOT NULL DEFAULT gen_random_uuid(),
    relative_path text NOT NULL,
    size_bytes    bigint,
    content_type  text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    missing_since timestamptz
);

ALTER TABLE ONLY hagio_admin.file
    ADD CONSTRAINT file_pkey PRIMARY KEY (file_id);

ALTER TABLE ONLY hagio_admin.file
    ADD CONSTRAINT file_relative_path_key UNIQUE (relative_path);

-- text_pattern_ops so the directory-rename rewrite
--   ... WHERE relative_path LIKE 'olddir/%'
-- and the per-directory listing queries can use an index. The default
-- collation-aware operator class cannot serve a LIKE prefix match.
CREATE INDEX ix_file_relative_path_prefix
    ON hagio_admin.file USING btree (relative_path text_pattern_ops);

COMMENT ON TABLE hagio_admin.file
    IS 'One file on the network share, tracked by UUIDv4 and served at /f/<file_id>. Maintained by the file-explorer web app; a complete inventory of the share except for the directories it is configured to exclude.';
COMMENT ON COLUMN hagio_admin.file.file_id
    IS 'UUIDv4. The stable identity of the file: it is what appears in the URL, so it survives renames and moves.';
COMMENT ON COLUMN hagio_admin.file.relative_path
    IS 'Where the file currently lives, as a POSIX path relative to the network share root, without a leading slash. Rewritten on every rename and move.';
COMMENT ON COLUMN hagio_admin.file.size_bytes
    IS 'Size in bytes as of the last scan.';
COMMENT ON COLUMN hagio_admin.file.content_type
    IS 'MIME type guessed from the file extension as of the last scan.';
COMMENT ON COLUMN hagio_admin.file.missing_since
    IS 'When a scan first found relative_path gone. NULL while the file is present. The row is kept regardless, because links to this file_id may already exist in the database.';

-- ------------------------------------------------------- file_link_host ------

-- Which hosts count as "one of our file links". The trigger below runs inside
-- the database and cannot read the app's config.toml, so the configured hosts
-- are mirrored here: the app reconciles this table against its `link_hosts`
-- setting at startup (insert missing, delete no-longer-configured). Seeded with
-- the production host so the trigger is already correct before the app first
-- boots. Multiple rows are supported: dev and production, or a future rename
-- of the public hostname with an overlap period.

CREATE TABLE hagio_admin.file_link_host (
    host text NOT NULL
);

ALTER TABLE ONLY hagio_admin.file_link_host
    ADD CONSTRAINT file_link_host_pkey PRIMARY KEY (host);

COMMENT ON TABLE hagio_admin.file_link_host
    IS 'Hosts whose /f/<uuid> URLs are recognised as links to hagio_admin.file. Reconciled from the file-explorer app''s `link_hosts` setting at startup.';
COMMENT ON COLUMN hagio_admin.file_link_host.host
    IS 'Lowercase hostname, no scheme and no port, e.g. ''files.m-patch.ugent.be''.';

INSERT INTO hagio_admin.file_link_host (host) VALUES ('files.m-patch.ugent.be');

-- ------------------------------------------------------- file_reference ------

CREATE TABLE hagio_admin.file_reference (
    file_reference_id bigint NOT NULL,
    file_id           uuid NOT NULL,
    source_table      text NOT NULL,
    source_id         integer NOT NULL,
    source_column     text NOT NULL,
    url               text NOT NULL,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE SEQUENCE hagio_admin.file_reference_file_reference_id_seq
    AS bigint START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;

ALTER SEQUENCE hagio_admin.file_reference_file_reference_id_seq
    OWNED BY hagio_admin.file_reference.file_reference_id;

ALTER TABLE ONLY hagio_admin.file_reference
    ALTER COLUMN file_reference_id
    SET DEFAULT nextval('hagio_admin.file_reference_file_reference_id_seq'::regclass);

ALTER TABLE ONLY hagio_admin.file_reference
    ADD CONSTRAINT file_reference_pkey PRIMARY KEY (file_reference_id);

ALTER TABLE ONLY hagio_admin.file_reference
    ADD CONSTRAINT file_reference_source_key
    UNIQUE (source_table, source_id, source_column);

ALTER TABLE ONLY hagio_admin.file_reference
    ADD CONSTRAINT file_reference_file_id_fkey FOREIGN KEY (file_id)
    REFERENCES hagio_admin.file(file_id) ON DELETE CASCADE;

CREATE INDEX ix_file_reference_file_id
    ON hagio_admin.file_reference USING btree (file_id);

COMMENT ON TABLE hagio_admin.file_reference
    IS 'Which database rows link to which file. Derived, never edited by hand: maintained by triggers on public.manuscript_link and public.edition_link. Answers "what cites this file?" and "which files are unused?".';
COMMENT ON COLUMN hagio_admin.file_reference.source_table
    IS 'The referencing table, unqualified: ''manuscript_link'' or ''edition_link''. Not an FK, since Postgres has no cross-table reference type.';
COMMENT ON COLUMN hagio_admin.file_reference.source_id
    IS 'Primary key of the referencing row (manuscript_link_id / edition_link_id).';
COMMENT ON COLUMN hagio_admin.file_reference.source_column
    IS 'The referencing column, always ''url'' today; present so a second linking column would not need a schema change.';
COMMENT ON COLUMN hagio_admin.file_reference.url
    IS 'The URL as stored in the source row, for debugging. The authoritative link is file_id.';

-- ----------------------------------------------------------- extraction ------

CREATE FUNCTION hagio_admin.file_id_from_url(candidate text)
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    -- Both halves must match: the /f/<uuid> shape AND a configured host.
    -- Anything else is just some other URL a researcher put in the cell (the
    -- Légendiers and catalogue links already in these columns), not a link to
    -- one of our files. The port is stripped, the host lowercased, and a
    -- trailing path, query or fragment (e.g. '?download=1') is tolerated.
    SELECT (m[2])::uuid
    FROM regexp_match(
             btrim(candidate),
             '^https?://([^/:]+)(?::[0-9]+)?/f/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?:[/?#].*)?$'
         ) AS m
    WHERE EXISTS (
        SELECT 1 FROM hagio_admin.file_link_host h WHERE h.host = lower(m[1])
    );
$$;

COMMENT ON FUNCTION hagio_admin.file_id_from_url(text)
    IS 'The file_id a URL points at, or NULL if it is not a /f/<uuid> URL on a configured host. Says nothing about whether that file_id exists.';

-- -------------------------------------------------------------- trigger ------

-- SECURITY DEFINER is load-bearing, not decoration: the researchers edit these
-- columns through Mathesar as hagiographies_editor, which has no USAGE on
-- hagio_admin. Without it every such edit would fail with "permission denied
-- for schema hagio_admin". search_path is pinned for the same reason it always
-- is on a SECURITY DEFINER function.
--
-- The trigger never raises. An unknown file_id is recorded as unresolved (see
-- the view below) rather than rejected: a researcher pasting a typo'd link
-- should get their edit saved and a chance to notice, not an error dialog from
-- a table they cannot see.
--
-- TG_ARGV[0] names the source table's primary key column, so one function
-- serves both triggers without dynamic SQL.

CREATE FUNCTION hagio_admin.sync_file_reference()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    id_column text := TG_ARGV[0];
    row_id    integer;
    candidate text;
    target    uuid;
BEGIN
    IF TG_OP = 'DELETE' THEN
        row_id := (to_jsonb(OLD) ->> id_column)::integer;
    ELSE
        row_id := (to_jsonb(NEW) ->> id_column)::integer;
        candidate := NEW.url::text;
    END IF;

    target := hagio_admin.file_id_from_url(candidate);

    IF target IS NULL OR NOT EXISTS (
        SELECT 1 FROM hagio_admin.file f WHERE f.file_id = target
    ) THEN
        DELETE FROM hagio_admin.file_reference
        WHERE source_table = TG_TABLE_NAME
          AND source_id = row_id
          AND source_column = 'url';
    ELSE
        INSERT INTO hagio_admin.file_reference
            (file_id, source_table, source_id, source_column, url)
        VALUES (target, TG_TABLE_NAME, row_id, 'url', candidate)
        ON CONFLICT (source_table, source_id, source_column) DO UPDATE
        SET file_id = EXCLUDED.file_id,
            url = EXCLUDED.url,
            updated_at = now();
    END IF;

    RETURN NULL;  -- AFTER trigger; the return value is ignored
END
$$;

COMMENT ON FUNCTION hagio_admin.sync_file_reference()
    IS 'Keeps hagio_admin.file_reference in step with a link table''s url column. Attach as an AFTER row trigger with the source table''s primary key column name as the sole argument.';

CREATE TRIGGER manuscript_link_sync_file_reference
    AFTER INSERT OR DELETE OR UPDATE OF url ON public.manuscript_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.sync_file_reference('manuscript_link_id');

CREATE TRIGGER edition_link_sync_file_reference
    AFTER INSERT OR DELETE OR UPDATE OF url ON public.edition_link
    FOR EACH ROW
    EXECUTE FUNCTION hagio_admin.sync_file_reference('edition_link_id');

-- ----------------------------------------------------------------- view ------

CREATE VIEW hagio_admin.file_reference_unresolved AS
SELECT 'manuscript_link' AS source_table,
       l.manuscript_link_id AS source_id,
       'url' AS source_column,
       l.url::text AS url,
       hagio_admin.file_id_from_url(l.url::text) AS file_id
FROM public.manuscript_link l
WHERE hagio_admin.file_id_from_url(l.url::text) IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM hagio_admin.file f
      WHERE f.file_id = hagio_admin.file_id_from_url(l.url::text)
  )
UNION ALL
SELECT 'edition_link' AS source_table,
       l.edition_link_id AS source_id,
       'url' AS source_column,
       l.url::text AS url,
       hagio_admin.file_id_from_url(l.url::text) AS file_id
FROM public.edition_link l
WHERE hagio_admin.file_id_from_url(l.url::text) IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM hagio_admin.file f
      WHERE f.file_id = hagio_admin.file_id_from_url(l.url::text)
  );

COMMENT ON VIEW hagio_admin.file_reference_unresolved
    IS 'Link rows that look like one of our file links but name a file_id that does not exist: typos, or files whose row was never created. The actionable complement to file_reference.';

-- ------------------------------------------------------------- backfill ------

-- Correct on day one rather than only from the first edit onwards. Expect zero
-- rows at first: hagio_admin.file is empty here, and the 2775 manuscript_link
-- and 671 edition_link rows presently hold Légendiers and catalogue URLs. It
-- costs one pass and means the table is never quietly incomplete.

INSERT INTO hagio_admin.file_reference
    (file_id, source_table, source_id, source_column, url)
SELECT hagio_admin.file_id_from_url(l.url::text),
       'manuscript_link', l.manuscript_link_id, 'url', l.url::text
FROM public.manuscript_link l
WHERE hagio_admin.file_id_from_url(l.url::text) IN (
    SELECT file_id FROM hagio_admin.file
)
ON CONFLICT (source_table, source_id, source_column) DO NOTHING;

INSERT INTO hagio_admin.file_reference
    (file_id, source_table, source_id, source_column, url)
SELECT hagio_admin.file_id_from_url(l.url::text),
       'edition_link', l.edition_link_id, 'url', l.url::text
FROM public.edition_link l
WHERE hagio_admin.file_id_from_url(l.url::text) IN (
    SELECT file_id FROM hagio_admin.file
)
ON CONFLICT (source_table, source_id, source_column) DO NOTHING;
