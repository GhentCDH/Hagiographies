-- 065: IIIF manifest links hold the bare manifest URL, once per codex.
--
-- Some 'IIIF manifest' links wrap the manifest in a viewer URL, e.g.
--   https://projectmirador.org/embed/?iiif-content=https://gallica.bnf.fr/iiif/ark:/12148/btv1b10546174d/manifest.json
-- and several codices carry the same manifest more than once, wrapped and bare.
-- On PRD (2026-11-23): 244 'IIIF manifest' rows, 23 of them wrapped, but only 222
-- distinct (codex, manifest). One 'Legendiers entry' row is a wrapped manifest too.
--
-- This migration
--   1. unpacks the manifest from the viewer's iiif-content= or manifest= parameter,
--      decoding it when it is URL-encoded. Only a value that is itself an http(s)
--      URL counts, so a manifest's own query string (manifest?iiifVersion=3) is
--      left alone;
--   2. turns the wrapped 'Legendiers entry' row into an 'IIIF manifest' link;
--   3. merges the links that are now the same manifest on the same codex: the
--      lowest id is kept (an existing 'IIIF manifest' row before a converted one)
--      and the distinct non-empty notes are joined with ' | ', as in 061.
--
-- The existing UNIQUE (codex_id, codex_link_type_id, codex_link_url) from 061
-- then also covers the unpacked URLs: a manifest is unique per codex. The same
-- manifest on different codices is allowed (decision 2026-11-23) and reported by
-- the IIIF check (just db_iiif_check) for the researchers.
--
-- Merging happens before the URL update, otherwise an unpacked URL would clash
-- with its bare twin on that unique constraint. The update fires the file
-- explorer's codex_link_sync_reference trigger, which ignores external URLs.
--
-- Viewer links in 'IIIF webpage' / 'IIIF of microfilm webpage' are handled in 066.
-- It refuses rather than guesses: a missing link type aborts, as does a manifest
-- that is still wrapped afterwards.

DO $$
DECLARE
    manifest_type int;
    legendiers_type int;
    merged bigint;
    unpacked bigint;
    leftovers text;
BEGIN
    SELECT codex_link_type_id INTO manifest_type
      FROM public.codex_link_type WHERE codex_link_type = 'IIIF manifest';
    SELECT codex_link_type_id INTO legendiers_type
      FROM public.codex_link_type WHERE codex_link_type = 'Legendiers entry';
    IF manifest_type IS NULL OR legendiers_type IS NULL THEN
        RAISE EXCEPTION 'codex_link_type ''IIIF manifest'' or ''Legendiers entry'' not found';
    END IF;

    -- Every candidate with the URL it should end up with.
    CREATE TEMP TABLE iiif_manifest ON COMMIT DROP AS
    SELECT codex_link_id, codex_id, codex_link_type_id, codex_link_note,
           codex_link_url::text AS old_url, NULL::text AS new_url
      FROM public.codex_link
     WHERE codex_link_type_id = manifest_type
        OR (codex_link_type_id = legendiers_type
            AND codex_link_url::text ~* '[?&](iiif-content|manifest)=https?(:|%3A)');

    UPDATE iiif_manifest SET new_url =
        CASE WHEN btrim(old_url) ~* '[?&](iiif-content|manifest)=https?(:|%3A)'
             THEN regexp_replace(btrim(old_url), '^[^?]*\?(.*&)?(iiif-content|manifest)=', '', 'i')
             ELSE btrim(old_url)
        END;

    -- URL-encoded manifests (https%3A%2F%2F…): decode the usual suspects, '%25' last.
    UPDATE iiif_manifest
       SET new_url = replace(replace(replace(replace(replace(replace(replace(
                     new_url, '%3A', ':'), '%2F', '/'), '%3F', '?'), '%3D', '='),
                     '%26', '&'), '%23', '#'), '%25', '%')
     WHERE new_url ~* '^https?%3A';

    -- Merge per (codex, manifest).
    CREATE TEMP TABLE iiif_manifest_group ON COMMIT DROP AS
    SELECT codex_id, new_url,
           (array_agg(codex_link_id ORDER BY (codex_link_type_id = manifest_type) DESC,
                                             codex_link_id))[1] AS keep_id,
           string_agg(DISTINCT nullif(btrim(codex_link_note), ''), ' | '
                      ORDER BY nullif(btrim(codex_link_note), '')) AS notes,
           count(*) AS n
      FROM iiif_manifest
     GROUP BY codex_id, new_url;

    DELETE FROM public.codex_link l
     USING iiif_manifest m
      JOIN iiif_manifest_group g USING (codex_id, new_url)
     WHERE l.codex_link_id = m.codex_link_id
       AND m.codex_link_id <> g.keep_id;
    GET DIAGNOSTICS merged = ROW_COUNT;

    UPDATE public.codex_link l
       SET codex_link_url = g.new_url,
           codex_link_type_id = manifest_type,
           codex_link_note = CASE WHEN g.n > 1 THEN g.notes ELSE l.codex_link_note END
      FROM iiif_manifest_group g
     WHERE l.codex_link_id = g.keep_id
       AND (l.codex_link_url::text IS DISTINCT FROM g.new_url
            OR l.codex_link_type_id <> manifest_type
            OR (g.n > 1 AND l.codex_link_note IS DISTINCT FROM g.notes));
    GET DIAGNOSTICS unpacked = ROW_COUNT;

    RAISE NOTICE 'codex_link IIIF manifests: % rows merged into a twin, % rows unpacked or retyped', merged, unpacked;

    SELECT string_agg(format('codex_link %s: %s', codex_link_id, codex_link_url), E'\n')
      INTO leftovers
      FROM public.codex_link
     WHERE codex_link_type_id = manifest_type
       AND (codex_link_url::text ~* '[?&](iiif-content|manifest)=https?(:|%3A)'
            OR codex_link_url::text <> btrim(codex_link_url::text));
    IF leftovers IS NOT NULL THEN
        RAISE EXCEPTION E'IIIF manifest links still wrapped in a viewer URL:\n%', leftovers;
    END IF;
END
$$;
