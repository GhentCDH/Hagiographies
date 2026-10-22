-- 021: relabel author_milieu columns.
--
-- Part of the October 2026 relabelling (naming rules in AGENTS.md):
-- content columns carry their table name, lookup value columns are named
-- after their table, many-to-many junctions are <a>__<b>. Constraint, index
-- and sequence names follow so they match what PostgreSQL/SQLAlchemy would
-- generate for the new names. Renames only: no data is touched, and FKs,
-- grants, comments and Mathesar's per-column settings carry over.
--
-- Every call is guarded (see 018): it is a no-op when the rename already
-- happened, so the file is safe on a database renamed by hand in Mathesar.

SELECT hagio_admin.rename_column('author_milieu', 'label', 'author_milieu');
SELECT hagio_admin.rename_column('author_milieu', 'note', 'author_milieu_note');
SELECT hagio_admin.rename_constraint('author_milieu', 'author_milieu_label_key', 'author_milieu_author_milieu_key');
