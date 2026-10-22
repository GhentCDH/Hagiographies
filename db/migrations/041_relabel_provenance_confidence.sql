-- 041: relabel provenance_confidence columns.
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

SELECT hagio_admin.rename_column('provenance_confidence', 'label', 'provenance_confidence');
SELECT hagio_admin.rename_column('provenance_confidence', 'note', 'provenance_confidence_note');
SELECT hagio_admin.rename_constraint('provenance_confidence', 'provenance_confidence_label_key', 'provenance_confidence_provenance_confidence_key');
