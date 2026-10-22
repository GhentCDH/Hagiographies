-- 039: relabel manuscript_type → codex_type.
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

SELECT hagio_admin.rename_table('manuscript_type', 'codex_type');
SELECT hagio_admin.rename_column('codex_type', 'manuscript_type_id', 'codex_type_id');
SELECT hagio_admin.rename_column('codex_type', 'label', 'codex_type');
SELECT hagio_admin.rename_column('codex_type', 'note', 'codex_type_note');
SELECT hagio_admin.rename_constraint('codex_type', 'manuscript_type_label_key', 'codex_type_codex_type_key');
SELECT hagio_admin.rename_constraint('codex_type', 'manuscript_type_pkey', 'codex_type_pkey');
SELECT hagio_admin.rename_sequence('manuscript_type_manuscript_type_id_seq', 'codex_type_codex_type_id_seq');
