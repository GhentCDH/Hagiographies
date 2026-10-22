-- 043: relabel repertory columns.
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

SELECT hagio_admin.rename_column('repertory', 'name', 'repertory_name');
SELECT hagio_admin.rename_column('repertory', 'note', 'repertory_note');
SELECT hagio_admin.rename_constraint('repertory', 'repertory_name_key', 'repertory_repertory_name_key');
