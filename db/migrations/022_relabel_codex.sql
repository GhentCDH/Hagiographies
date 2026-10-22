-- 022: relabel codex columns.
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

SELECT hagio_admin.rename_column('codex', 'name', 'codex_unique_identifier');
SELECT hagio_admin.rename_column('codex', 'shelfmark', 'codex_shelfmark');
SELECT hagio_admin.rename_column('codex', 'height', 'codex_height');
SELECT hagio_admin.rename_column('codex', 'width', 'codex_width');
SELECT hagio_admin.rename_column('codex', 'dating_century', 'codex_dating_by_century');
SELECT hagio_admin.rename_column('codex', 'dating_range_start', 'codex_dating_range_start');
SELECT hagio_admin.rename_column('codex', 'dating_range_end', 'codex_dating_range_end');
SELECT hagio_admin.rename_column('codex', 'dating_reference', 'codex_dating_reference');
SELECT hagio_admin.rename_column('codex', 'dating_note', 'codex_dating_note');
SELECT hagio_admin.rename_column('codex', 'codex_notes', 'codex_contents_note');
SELECT hagio_admin.rename_column('codex', 'general_notes', 'codex_general_note');
SELECT hagio_admin.rename_column('codex', 'origin_or_provenance_secondary_reference', 'codex_origin_or_provenance_secondary_reference');
SELECT hagio_admin.rename_column('codex', 'manuscript_type_note', 'codex_type_selection_note');
SELECT hagio_admin.rename_column('codex', 'manuscript_preservation_status_id', 'codex_preservation_status_id');
SELECT hagio_admin.rename_column('codex', 'manuscript_holding_institution_id', 'codex_holding_institution_id');
SELECT hagio_admin.rename_column('codex', 'manuscript_type_id', 'codex_type_id');
SELECT hagio_admin.rename_column('codex', 'origin_diocese_confidence_rating_id', 'origin_diocese_confidence_id');
SELECT hagio_admin.rename_column('codex', 'origin_institution_confidence_rating_id', 'origin_institution_confidence_id');
SELECT hagio_admin.rename_column('codex', 'provenance_early_institute_id', 'provenance_early_institution_id');
SELECT hagio_admin.rename_column('codex', 'provenance_later_institute_id', 'provenance_later_institution_id');
SELECT hagio_admin.rename_constraint('codex', 'codex_manuscript_holding_institution_id_fkey', 'codex_codex_holding_institution_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_manuscript_preservation_status_id_fkey', 'codex_codex_preservation_status_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_manuscript_type_id_fkey', 'codex_codex_type_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_name_key', 'codex_codex_unique_identifier_key');
SELECT hagio_admin.rename_constraint('codex', 'codex_origin_diocese_confidence_rating_id_fkey', 'codex_origin_diocese_confidence_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_origin_institution_confidence_rating_id_fkey', 'codex_origin_institution_confidence_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_provenance_early_institute_id_fkey', 'codex_provenance_early_institution_id_fkey');
SELECT hagio_admin.rename_constraint('codex', 'codex_provenance_later_institute_id_fkey', 'codex_provenance_later_institution_id_fkey');
