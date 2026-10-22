-- 025: relabel edition columns.
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

SELECT hagio_admin.rename_column('edition', 'identifier_per_text', 'edition_unique_identifier');
SELECT hagio_admin.rename_column('edition', 'page_numbers', 'edition_page_numbers');
SELECT hagio_admin.rename_column('edition', 'reprint', 'edition_reprint');
SELECT hagio_admin.rename_column('edition', 'reprint_identical', 'edition_reprint_identical');
SELECT hagio_admin.rename_column('edition', 'reprint_of', 'edition_reprint_of_note');
SELECT hagio_admin.rename_column('edition', 'collation_done', 'edition_collation_done');
SELECT hagio_admin.rename_column('edition', 'general_notes', 'edition_general_note');
SELECT hagio_admin.rename_index('ix_edition_identifier_per_text', 'ix_edition_edition_unique_identifier');
