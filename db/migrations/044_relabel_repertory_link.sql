-- 044: relabel repertory_link → text__repertory.
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

SELECT hagio_admin.rename_table('repertory_link', 'text__repertory');
SELECT hagio_admin.rename_column('text__repertory', 'repertory_link_id', 'text__repertory_id');
SELECT hagio_admin.rename_column('text__repertory', 'url', 'text__repertory_url');
SELECT hagio_admin.rename_column('text__repertory', 'note', 'text__repertory_note');
SELECT hagio_admin.rename_constraint('text__repertory', 'repertory_link_pkey', 'text__repertory_pkey');
SELECT hagio_admin.rename_constraint('text__repertory', 'repertory_link_repertory_id_fkey', 'text__repertory_repertory_id_fkey');
SELECT hagio_admin.rename_constraint('text__repertory', 'repertory_link_text_id_fkey', 'text__repertory_text_id_fkey');
SELECT hagio_admin.rename_index('ix_repertory_link_repertory_id', 'ix_text__repertory_repertory_id');
SELECT hagio_admin.rename_index('ix_repertory_link_text_id', 'ix_text__repertory_text_id');
SELECT hagio_admin.rename_sequence('repertory_link_repertory_link_id_seq', 'text__repertory_text__repertory_id_seq');
