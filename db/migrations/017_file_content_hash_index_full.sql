-- 017: widen the content-hash index to every row.
--
-- 016 indexed content_hash only WHERE missing_since IS NOT NULL, because a
-- relocation candidate was looked up solely among the rows a scan had already
-- flagged missing. A browse of a directory has no such sweep behind it: when a
-- file was moved over SMB, its old row is still marked present until the folder
-- it left is scanned. To adopt that row on the destination listing, the matcher
-- now probes present rows too, checking whether each one is still at its
-- recorded path. The partial index cannot serve a query that does not constrain
-- missing_since, so it is replaced by a plain one over the whole column.

DROP INDEX IF EXISTS hagio_admin.ix_file_content_hash;

CREATE INDEX IF NOT EXISTS ix_file_content_hash
    ON hagio_admin.file (content_hash);