-- 038: relabel manuscript_relationship_type → manuscript__manuscript_type.
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

SELECT hagio_admin.rename_table('manuscript_relationship_type', 'manuscript__manuscript_type');
SELECT hagio_admin.rename_column('manuscript__manuscript_type', 'manuscript_relationship_type_id', 'manuscript__manuscript_type_id');
SELECT hagio_admin.rename_column('manuscript__manuscript_type', 'label', 'manuscript__manuscript_type');
SELECT hagio_admin.rename_column('manuscript__manuscript_type', 'note', 'manuscript__manuscript_type_note');
SELECT hagio_admin.rename_constraint('manuscript__manuscript_type', 'manuscript_relationship_type_label_key', 'manuscript__manuscript_type_manuscript__manuscript_type_key');
SELECT hagio_admin.rename_constraint('manuscript__manuscript_type', 'manuscript_relationship_type_pkey', 'manuscript__manuscript_type_pkey');
SELECT hagio_admin.rename_sequence('manuscript_relationship_type_manuscript_relationship_type_i_seq', 'manuscript__manuscript_type_manuscript__manuscript_type_id_seq');
