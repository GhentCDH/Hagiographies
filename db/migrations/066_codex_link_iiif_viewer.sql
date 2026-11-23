-- 066: every IIIF manifest gets a Theseus viewer link; the Mirador embed links go.
--
-- A new codex_link_type 'IIIF viewer' holds a link that opens the codex's
-- manifest in the Theseus viewer:
--   https://theseusviewer.org/?iiif-content=<manifest URL>
-- The manifest is percent-encoded where it matters inside a query value
-- ('%', '&', '?', '#', '=', '+', space); the viewer decodes it again.
-- One viewer link is added per 'IIIF manifest' link (after 065: per codex and
-- manifest). ON CONFLICT DO NOTHING keeps the migration idempotent.
-- Manifests added later get theirs from the IIIF check (just db_iiif_check).
--
-- The 'IIIF webpage' and 'IIIF of microfilm webpage' types held 128 projectmirador.org
-- embed links on PRD (2026-11-23), each wrapping a manifest that the same codex
-- already has as an 'IIIF manifest' link. They are replaced by the Theseus
-- link (decision 2026-11-23): deleted, and any note they carry is appended to
-- the codex's viewer link for that manifest, so no note is lost.
--
-- It refuses rather than guesses: a Mirador link whose manifest is not an
-- 'IIIF manifest' link on the same codex is listed and aborts the migration.

INSERT INTO public.codex_link_type (codex_link_type, codex_link_type_note)
SELECT 'IIIF viewer', 'Opens the codex''s IIIF manifest in the Theseus viewer (theseusviewer.org). One per IIIF manifest link; added by migration 066 and by the IIIF check.'
 WHERE NOT EXISTS (SELECT 1 FROM public.codex_link_type WHERE codex_link_type = 'IIIF viewer');

DO $$
DECLARE
    manifest_type int;
    viewer_type int;
    added bigint;
    removed bigint;
    orphans text;
BEGIN
    SELECT codex_link_type_id INTO manifest_type
      FROM public.codex_link_type WHERE codex_link_type = 'IIIF manifest';
    SELECT codex_link_type_id INTO viewer_type
      FROM public.codex_link_type WHERE codex_link_type = 'IIIF viewer';
    IF manifest_type IS NULL THEN
        RAISE EXCEPTION 'codex_link_type ''IIIF manifest'' not found';
    END IF;

    INSERT INTO public.codex_link (codex_id, codex_link_type_id, codex_link_url)
    SELECT codex_id, viewer_type,
           'https://theseusviewer.org/?iiif-content=' ||
           replace(replace(replace(replace(replace(replace(replace(
               codex_link_url::text, '%', '%25'), '&', '%26'), '?', '%3F'), '#', '%23'),
               '=', '%3D'), '+', '%2B'), ' ', '%20')
      FROM public.codex_link
     WHERE codex_link_type_id = manifest_type
    ON CONFLICT (codex_id, codex_link_type_id, codex_link_url) DO NOTHING;
    GET DIAGNOSTICS added = ROW_COUNT;

    -- The Mirador embed links in the two webpage types, with their manifest.
    CREATE TEMP TABLE mirador_link ON COMMIT DROP AS
    SELECT l.codex_link_id, l.codex_id, nullif(btrim(l.codex_link_note), '') AS note,
           regexp_replace(btrim(l.codex_link_url::text),
                          '^[^?]*\?(.*&)?(iiif-content|manifest)=', '', 'i') AS manifest
      FROM public.codex_link l
      JOIN public.codex_link_type t USING (codex_link_type_id)
     WHERE t.codex_link_type IN ('IIIF webpage', 'IIIF of microfilm webpage')
       AND l.codex_link_url::text ~* '^https?://(www\.)?projectmirador\.org/.*[?&](iiif-content|manifest)=https?:';

    SELECT string_agg(format('codex_link %s (codex %s): %s', r.codex_link_id, r.codex_id, r.manifest), E'\n')
      INTO orphans
      FROM mirador_link r
     WHERE NOT EXISTS (SELECT 1 FROM public.codex_link m
                        WHERE m.codex_id = r.codex_id
                          AND m.codex_link_type_id = manifest_type
                          AND m.codex_link_url::text = r.manifest);
    IF orphans IS NOT NULL THEN
        RAISE EXCEPTION E'Mirador links whose manifest is no IIIF manifest link on the same codex; add it in Mathesar first:\n%', orphans;
    END IF;

    UPDATE public.codex_link v
       SET codex_link_note = concat_ws(' | ', nullif(btrim(v.codex_link_note), ''), n.notes)
      FROM (SELECT codex_id, manifest, string_agg(DISTINCT note, ' | ' ORDER BY note) AS notes
              FROM mirador_link WHERE note IS NOT NULL
             GROUP BY 1, 2) n
     WHERE v.codex_id = n.codex_id
       AND v.codex_link_type_id = viewer_type
       AND v.codex_link_url::text = 'https://theseusviewer.org/?iiif-content=' ||
           replace(replace(replace(replace(replace(replace(replace(
               n.manifest, '%', '%25'), '&', '%26'), '?', '%3F'), '#', '%23'),
               '=', '%3D'), '+', '%2B'), ' ', '%20');

    DELETE FROM public.codex_link l USING mirador_link r WHERE l.codex_link_id = r.codex_link_id;
    GET DIAGNOSTICS removed = ROW_COUNT;

    RAISE NOTICE 'codex_link: % Theseus viewer links added, % Mirador links replaced', added, removed;
END
$$;
