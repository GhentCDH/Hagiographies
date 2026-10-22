-- 036: relabel manuscript_preservation_status → codex_preservation_status.
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

SELECT hagio_admin.rename_table('manuscript_preservation_status', 'codex_preservation_status');
SELECT hagio_admin.rename_column('codex_preservation_status', 'manuscript_preservation_status_id', 'codex_preservation_status_id');
SELECT hagio_admin.rename_column('codex_preservation_status', 'label', 'codex_preservation_status');
SELECT hagio_admin.rename_constraint('codex_preservation_status', 'manuscript_preservation_status_label_key', 'codex_preservation_status_codex_preservation_status_key');
SELECT hagio_admin.rename_constraint('codex_preservation_status', 'manuscript_preservation_status_pkey', 'codex_preservation_status_pkey');
SELECT hagio_admin.rename_sequence('manuscript_preservation_statu_manuscript_preservation_statu_seq', 'codex_preservation_status_codex_preservation_status_id_seq');
