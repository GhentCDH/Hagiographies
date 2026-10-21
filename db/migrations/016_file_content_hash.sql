-- 016: a content hash per file, so a file edited directly on the share (moved
-- or renamed over SMB) can be recognised by its bytes and keep its file_id.
--
-- Identity is the file_id (013), never the path: /f/<uuid> links and the
-- manuscript_link_reference / edition_link_reference rows all key on file_id.
-- An in-app move already keeps the file_id by relocating the row in place
-- (UPDATE ... WHERE file_id = ...). A direct edit on the share does not go
-- through the app, so the scanner used to see the old location as gone and the
-- new one as a brand-new file, minting a fresh file_id and breaking the pasted
-- link. With a content hash the scanner can match the new location back to the
-- one missing row that has the same bytes and relocate it instead.
--
-- The hash is blake3 (256 bits), stored raw as bytea. Collisions are not a
-- real concern at that width, so a hash match is treated as a content match.
--
-- Nullable: existing rows stay NULL until the file-explorer's next scan reads
-- each file once and backfills it. Nothing in the database depends on it; it is
-- read and written only by the app.
--
-- The index is partial on the rows the matcher actually probes -- files that
-- are missing_since something -- because that is the only pool a relocation
-- candidate is looked up against. Present files are never a match target.

ALTER TABLE hagio_admin.file
    ADD COLUMN IF NOT EXISTS content_hash bytea;

COMMENT ON COLUMN hagio_admin.file.content_hash
    IS 'blake3 (32 bytes) of the file contents. Written by the file-explorer scan/upload. Used to relocate a row to a file moved or renamed directly on the share, keeping its file_id. NULL until first scanned.';

CREATE INDEX IF NOT EXISTS ix_file_content_hash
    ON hagio_admin.file (content_hash)
    WHERE missing_since IS NOT NULL;
