-- 015: drop hagio_admin.file.relative_path, now that the tree replaces it.
--
-- The destructive half of 014. Only run this once the new binary is live: the old
-- one writes relative_path and nothing else, so dropping the column while it is
-- still serving would break every request it handles.
--
-- What makes it safe to drop is that hagio_admin.file_path reproduces the same
-- string from directory_id and name. 014 proved that for every row at the moment
-- it rebuilt the tree, which is the moment it could be proved; the guard here
-- checks the one thing still worth checking, that every file is in the tree at
-- all. Same shape as 011's refusal to drop the hoisted columns until it could see
-- their values on codex and publication.
--
-- It deliberately does NOT insist the two still agree. Once the new binary is
-- live, a folder rename updates one directory row and touches no file rows, so
-- relative_path goes stale by design and every path under that folder diverges.
-- That divergence is the feature working, not a fault, so it is reported and not
-- refused.
--
-- If the guard fires because a file has no directory_id, it is almost certainly a
-- row the old binary added between 014 and the deploy. Restart the app so its
-- startup scan adopts it, or run `just files_rescan`, then run this again.

-- --------------------------------------------------------------- guard -------

DO $$
DECLARE
    stragglers text;
    diverged   bigint;
BEGIN
    SELECT string_agg(coalesce(relative_path, file_id::text), ', ')
    INTO stragglers
    FROM hagio_admin.file
    WHERE directory_id IS NULL OR name IS NULL;

    IF stragglers IS NOT NULL THEN
        RAISE EXCEPTION
            'refusing to drop: these files are not in the directory tree: %. '
            'Rescan the share so they are adopted, then run this again.',
            stragglers;
    END IF;

    SELECT count(*)
    INTO diverged
    FROM hagio_admin.file f
    JOIN hagio_admin.file_path p USING (file_id)
    WHERE f.relative_path IS NOT NULL
      AND p.relative_path <> f.relative_path;

    IF diverged > 0 THEN
        RAISE NOTICE
            '% files have moved since relative_path was last written, which is '
            'expected: the tree is the truth now and the column is what we are '
            'dropping.',
            diverged;
    END IF;
END
$$;

-- ---------------------------------------------------------------- drop -------

ALTER TABLE hagio_admin.file ALTER COLUMN directory_id SET NOT NULL;
ALTER TABLE hagio_admin.file ALTER COLUMN name SET NOT NULL;

-- 013 created this index solely for the `relative_path LIKE 'olddir/%'` rewrite
-- that a folder rename used to need. A rename is now one row and the index has no
-- remaining reader.
DROP INDEX hagio_admin.ix_file_relative_path_prefix;

ALTER TABLE hagio_admin.file DROP CONSTRAINT file_relative_path_key;
ALTER TABLE hagio_admin.file DROP COLUMN relative_path;

COMMENT ON TABLE hagio_admin.file
    IS 'One file on the network share, tracked by UUIDv4 and served at /f/<file_id>. Where it lives is directory_id plus name; hagio_admin.file_path assembles the full path. Maintained by the file-explorer web app; a complete inventory of the share except for the directories it is configured to exclude.';
