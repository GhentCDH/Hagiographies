-- 033: relabel manuscript_holding_institution → codex_holding_institution.
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

SELECT hagio_admin.rename_table('manuscript_holding_institution', 'codex_holding_institution');
SELECT hagio_admin.rename_column('codex_holding_institution', 'manuscript_holding_institution_id', 'codex_holding_institution_id');
SELECT hagio_admin.rename_column('codex_holding_institution', 'name', 'codex_holding_institution_name');
SELECT hagio_admin.rename_constraint('codex_holding_institution', 'manuscript_holding_institution_name_key', 'codex_holding_institution_codex_holding_institution_name_key');
SELECT hagio_admin.rename_constraint('codex_holding_institution', 'manuscript_holding_institution_pkey', 'codex_holding_institution_pkey');
SELECT hagio_admin.rename_sequence('manuscript_holding_institutio_manuscript_holding_institutio_seq', 'codex_holding_institution_codex_holding_institution_id_seq');
