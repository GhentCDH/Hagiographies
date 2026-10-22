-- 037: relabel manuscript_relation → manuscript__manuscript.
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

SELECT hagio_admin.rename_table('manuscript_relation', 'manuscript__manuscript');
SELECT hagio_admin.rename_column('manuscript__manuscript', 'manuscript_relation_id', 'manuscript__manuscript_id');
SELECT hagio_admin.rename_column('manuscript__manuscript', 'manuscript_relationship_type_id', 'manuscript__manuscript_type_id');
SELECT hagio_admin.rename_column('manuscript__manuscript', 'note', 'manuscript__manuscript_note');
SELECT hagio_admin.rename_constraint('manuscript__manuscript', 'manuscript_relation_manuscript_id_fkey', 'manuscript__manuscript_manuscript_id_fkey');
SELECT hagio_admin.rename_constraint('manuscript__manuscript', 'manuscript_relation_manuscript_relationship_type_id_fkey', 'manuscript__manuscript_manuscript__manuscript_type_id_fkey');
SELECT hagio_admin.rename_constraint('manuscript__manuscript', 'manuscript_relation_pkey', 'manuscript__manuscript_pkey');
SELECT hagio_admin.rename_constraint('manuscript__manuscript', 'manuscript_relation_related_manuscript_id_fkey', 'manuscript__manuscript_related_manuscript_id_fkey');
SELECT hagio_admin.rename_index('ix_manuscript_relation_manuscript_id', 'ix_manuscript__manuscript_manuscript_id');
SELECT hagio_admin.rename_index('ix_manuscript_relation_related_manuscript_id', 'ix_manuscript__manuscript_related_manuscript_id');
SELECT hagio_admin.rename_sequence('manuscript_relation_manuscript_relation_id_seq', 'manuscript__manuscript_manuscript__manuscript_id_seq');
