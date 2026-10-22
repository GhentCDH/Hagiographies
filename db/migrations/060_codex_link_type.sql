-- 060: manuscript_link_type → codex_link_type.
--
-- The link types (Légendiers entry, catalogue descriptions, IIIF manifests,
-- scans, …) describe the physical codex, not one text copy in it. 061 moves the
-- links themselves to codex level; this migration renames their lookup first.
-- 062 then creates a new, empty manuscript_link_type for copy-level links.
--
-- Renames only, through the guarded helpers from 018.

SELECT hagio_admin.rename_table('manuscript_link_type', 'codex_link_type');
SELECT hagio_admin.rename_column('codex_link_type', 'manuscript_link_type_id', 'codex_link_type_id');
SELECT hagio_admin.rename_column('codex_link_type', 'manuscript_link_type', 'codex_link_type');
SELECT hagio_admin.rename_column('codex_link_type', 'manuscript_link_type_note', 'codex_link_type_note');
SELECT hagio_admin.rename_constraint('codex_link_type', 'manuscript_link_type_pkey', 'codex_link_type_pkey');
SELECT hagio_admin.rename_constraint('codex_link_type', 'manuscript_link_type_manuscript_link_type_key', 'codex_link_type_codex_link_type_key');
SELECT hagio_admin.rename_sequence('manuscript_link_type_manuscript_link_type_id_seq', 'codex_link_type_codex_link_type_id_seq');
