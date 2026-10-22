-- 027: relabel edition__manuscripts → edition__manuscript.
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

SELECT hagio_admin.rename_table('edition__manuscripts', 'edition__manuscript');
SELECT hagio_admin.rename_column('edition__manuscript', 'edition__manuscripts_id', 'edition__manuscript_id');
SELECT hagio_admin.rename_column('edition__manuscript', 'likely_use_of_a_copy', 'edition__manuscript_likely_use_of_a_copy');
SELECT hagio_admin.rename_column('edition__manuscript', 'notes', 'edition__manuscript_note');
SELECT hagio_admin.rename_constraint('edition__manuscript', 'edition__manuscripts_edition_id_fkey', 'edition__manuscript_edition_id_fkey');
SELECT hagio_admin.rename_constraint('edition__manuscript', 'edition__manuscripts_manuscript_id_fkey', 'edition__manuscript_manuscript_id_fkey');
SELECT hagio_admin.rename_constraint('edition__manuscript', 'edition__manuscripts_pkey', 'edition__manuscript_pkey');
SELECT hagio_admin.rename_index('ix_edition__manuscripts_edition_id', 'ix_edition__manuscript_edition_id');
SELECT hagio_admin.rename_index('ix_edition__manuscripts_manuscript_id', 'ix_edition__manuscript_manuscript_id');
SELECT hagio_admin.rename_sequence('edition__manuscripts_edition__manuscripts_id_seq', 'edition__manuscript_edition__manuscript_id_seq');
