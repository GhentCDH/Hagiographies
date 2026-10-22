-- 045: relabel text columns.
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

SELECT hagio_admin.rename_column('text', 'identifier', 'text_unique_identifier');
SELECT hagio_admin.rename_column('text', 'title', 'text_title');
SELECT hagio_admin.rename_column('text', 'approximate_token_count', 'text_approximate_token_count');
SELECT hagio_admin.rename_column('text', 'reecriture', 'text_reecriture');
SELECT hagio_admin.rename_column('text', 'reecriture_text_id', 'reecriture_of_text_id');
SELECT hagio_admin.rename_column('text', 'reecriture_note', 'text_reecriture_note');
SELECT hagio_admin.rename_column('text', 'dating_range_start', 'text_dating_range_start');
SELECT hagio_admin.rename_column('text', 'dating_range_stop', 'text_dating_range_end');
SELECT hagio_admin.rename_column('text', 'dating_range', 'text_dating_quarter_century');
SELECT hagio_admin.rename_column('text', 'dating_note', 'text_dating_note');
SELECT hagio_admin.rename_column('text', 'author_in_destinary_institution', 'text_author_in_destinatary_institution');
SELECT hagio_admin.rename_column('text', 'creation_note', 'text_creation_note');
SELECT hagio_admin.rename_column('text', 'destinary_archdiocese_id', 'destinatary_archdiocese_id');
SELECT hagio_admin.rename_column('text', 'destinary_diocese_id', 'destinatary_diocese_id');
SELECT hagio_admin.rename_column('text', 'destinary_institution_id', 'destinatary_institution_id');
SELECT hagio_admin.rename_column('text', 'destinary_note', 'text_destinatary_note');
SELECT hagio_admin.rename_column('text', 'reference', 'text_reference');
SELECT hagio_admin.rename_column('text', 'general_note', 'text_general_note');
SELECT hagio_admin.rename_constraint('text', 'text_destinary_archdiocese_id_fkey', 'text_destinatary_archdiocese_id_fkey');
SELECT hagio_admin.rename_constraint('text', 'text_destinary_diocese_id_fkey', 'text_destinatary_diocese_id_fkey');
SELECT hagio_admin.rename_constraint('text', 'text_destinary_institution_id_fkey', 'text_destinatary_institution_id_fkey');
SELECT hagio_admin.rename_constraint('text', 'text_reecriture_text_id_fkey', 'text_reecriture_of_text_id_fkey');
SELECT hagio_admin.rename_index('ix_text_identifier', 'ix_text_text_unique_identifier');
