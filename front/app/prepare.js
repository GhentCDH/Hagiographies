// @ts-check
/**
 * In-memory preparation of the Hagiographies SQLite export, run by our
 * embedded datasource right after the database opens and BEFORE Pihka reads
 * its metadata. The published .sqlite file is never changed.
 *
 * Why SQL on real tables instead of views: Pihka derives FK facets, FK labels
 * and "related records" from PRAGMA foreign_key_list, which views do not have.
 * Columns added here with ALTER TABLE ... REFERENCES are real FKs.
 *
 * Runs once per fresh in-memory copy (ALTER TABLE ADD COLUMN is not
 * re-runnable). SQLite notes: ADD COLUMN cannot be PRIMARY KEY/UNIQUE, a
 * REFERENCES column must default to NULL, NOT NULL needs a non-NULL default.
 *
 * Sections:
 *   1. remove restricted and placeholder links (never shown in the UI)
 *   2. normalise 'IIIF manifest' codex links to bare manifest URLs
 *   3. display tweaks: Yes/No flags, readable lookup labels, `label` columns
 *   4. derived columns (IIIF manifest, counts, coordinates, codex attributes
 *      copied onto manuscripts and editions as real FKs)
 */
/**
 * Section 1 on its own: remove restricted and placeholder links. front/tools/
 * compose.py runs exactly this SQL (then VACUUM) on the copy it embeds and
 * deposits, so the published .sqlite never contains those URLs. It stays in
 * PREPARE_SQL too, for the decomposed build, which opens the raw export.
 * Keep it plain SQL inside the String.raw template: compose.py extracts it
 * with a regex.
 */
export const PUBLIC_FILTER_SQL = String.raw`
-- 1. Restricted (files.m-patch.ugent.be, VPN-only share) and placeholder links.
DELETE FROM codex_link
 WHERE codex_link_url LIKE '%files.m-patch.ugent.be%'
    OR codex_link_type_id IN (SELECT codex_link_type_id FROM codex_link_type
                              WHERE codex_link_type LIKE 'Placeholder%');
DELETE FROM edition_link
 WHERE edition_link_url LIKE '%files.m-patch.ugent.be%'
    OR edition_link_type_id IN (SELECT edition_link_type_id FROM edition_link_type
                                WHERE edition_link_type LIKE 'Placeholder%');
DELETE FROM manuscript_link
 WHERE manuscript_link_url LIKE '%files.m-patch.ugent.be%'
    OR manuscript_link_type_id IN (SELECT manuscript_link_type_id FROM manuscript_link_type
                                   WHERE manuscript_link_type LIKE 'Placeholder%');
-- The placeholder types are now unused; drop them so no lookup shows them.
DELETE FROM codex_link_type WHERE codex_link_type LIKE 'Placeholder%';
DELETE FROM edition_link_type WHERE edition_link_type LIKE 'Placeholder%';
DELETE FROM manuscript_link_type WHERE manuscript_link_type LIKE 'Placeholder%';
`;

export const PREPARE_SQL = PUBLIC_FILTER_SQL + String.raw`
-- 2. 'IIIF manifest' links hold the bare manifest URL (migration 065). Older
-- exports wrap it in a viewer URL (...?iiif-content=<manifest>): unwrap and
-- URL-decode, then drop exact duplicates the unwrapping created.
UPDATE codex_link
   SET codex_link_url = trim(
         replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(
           substr(codex_link_url, instr(codex_link_url, 'iiif-content=') + 13),
           '%3A', ':'), '%3a', ':'), '%2F', '/'), '%2f', '/'),
           '%3F', '?'), '%3f', '?'), '%3D', '='), '%3d', '='), '%26', '&'), '%25', '%'))
 WHERE instr(codex_link_url, 'iiif-content=') > 0
   AND codex_link_type_id IN (SELECT codex_link_type_id FROM codex_link_type
                              WHERE codex_link_type = 'IIIF manifest');
DELETE FROM codex_link
 WHERE codex_link_id IN (
       SELECT a.codex_link_id
         FROM codex_link a
         JOIN codex_link b
           ON b.codex_id = a.codex_id
          AND b.codex_link_type_id = a.codex_link_type_id
          AND b.codex_link_url = a.codex_link_url
          AND b.codex_link_id < a.codex_link_id
        WHERE a.codex_link_note IS NULL OR a.codex_link_note = coalesce(b.codex_link_note, ''));

-- 3a. Boolean flags: 1/0 -> 'Yes'/'No' so facets and cells read naturally.
-- (Stored as TEXT in INTEGER-declared columns; never configure them as range.)
UPDATE codex SET codex_legendiers_usable = CASE codex_legendiers_usable WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE codex SET codex_composite = CASE codex_composite WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE text SET text_reecriture = CASE text_reecriture WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE text SET text_author_in_destinatary_institution =
       CASE text_author_in_destinatary_institution WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE edition SET edition_reprint = CASE edition_reprint WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE edition SET edition_reprint_identical = CASE edition_reprint_identical WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE edition SET edition_collation_done = CASE edition_collation_done WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;
UPDATE edition__manuscript SET edition__manuscript_likely_use_of_a_copy =
       CASE edition__manuscript_likely_use_of_a_copy WHEN 1 THEN 'Yes' WHEN 0 THEN 'No' END;

-- 3b. Code-valued lookups ('A', 'G', ...) show their meaning as FK labels.
UPDATE dating_confidence SET dating_confidence = dating_confidence || ' – ' || dating_confidence_note
 WHERE dating_confidence_note IS NOT NULL AND length(dating_confidence) <= 2;
UPDATE origin_confidence SET origin_confidence = origin_confidence || ' – ' || origin_confidence_note
 WHERE origin_confidence_note IS NOT NULL AND length(origin_confidence) <= 2;
UPDATE provenance_confidence SET provenance_confidence = provenance_confidence || ' – ' || provenance_confidence_note
 WHERE provenance_confidence_note IS NOT NULL AND length(provenance_confidence) <= 2;
UPDATE vernacular_region SET vernacular_region = vernacular_region_note
 WHERE vernacular_region_note IS NOT NULL AND length(vernacular_region) <= 2;

-- 3c. A column named "label" wins Pihka's FK display-column choice
-- (data-store.js #loadFkOptions), so references show more than a bare code.
-- Hidden in the config; the identifier columns stay untouched.
ALTER TABLE text ADD COLUMN label TEXT;
UPDATE text SET label = text_unique_identifier
       || CASE WHEN text_title IS NOT NULL AND text_title <> '' THEN ' – ' || text_title ELSE '' END;
ALTER TABLE manuscript ADD COLUMN label TEXT;
UPDATE manuscript SET label = manuscript_unique_identifier || coalesce(
       ' (' || (SELECT codex_unique_identifier FROM codex WHERE codex.codex_id = manuscript.codex_id)
            || coalesce(', ' || manuscript_folio_or_page_range, '') || ')', '');
ALTER TABLE edition ADD COLUMN label TEXT;
UPDATE edition SET label = edition_unique_identifier || coalesce(
       ' (' || (SELECT publication_unique_identifier FROM publication
                 WHERE publication.publication_id = edition.publication_id) || ')', '');

-- 4a. Codex: IIIF manifest, counts, coordinates of its (holding) location.
ALTER TABLE codex ADD COLUMN codex_iiif_manifest TEXT;
UPDATE codex SET codex_iiif_manifest = (
       SELECT l.codex_link_url FROM codex_link l
         JOIN codex_link_type t ON t.codex_link_type_id = l.codex_link_type_id
        WHERE l.codex_id = codex.codex_id AND t.codex_link_type = 'IIIF manifest'
          AND l.codex_link_url LIKE 'http%'
        ORDER BY l.codex_link_id LIMIT 1);
ALTER TABLE codex ADD COLUMN codex_has_iiif TEXT;
UPDATE codex SET codex_has_iiif = CASE WHEN codex_iiif_manifest IS NULL THEN 'No' ELSE 'Yes' END;
ALTER TABLE codex ADD COLUMN codex_manuscript_count INTEGER;
UPDATE codex SET codex_manuscript_count =
       (SELECT count(*) FROM manuscript m WHERE m.codex_id = codex.codex_id);
-- point_map / geo-filter only detect columns named exactly lat/latitude and
-- lon/lng/longitude (extensions/point_map/js/geo.js).
ALTER TABLE codex ADD COLUMN latitude REAL;
ALTER TABLE codex ADD COLUMN longitude REAL;
UPDATE codex SET
       latitude  = (SELECT location_latitude  FROM location l WHERE l.location_id = codex.location_id),
       longitude = (SELECT location_longitude FROM location l WHERE l.location_id = codex.location_id);

-- 4b. Text: counts and repertories (the junction carries url/note columns, so
-- Pihka does not detect it as many-to-many; the list is display-only).
ALTER TABLE text ADD COLUMN text_manuscript_count INTEGER;
UPDATE text SET text_manuscript_count = (SELECT count(*) FROM manuscript m WHERE m.text_id = text.text_id);
ALTER TABLE text ADD COLUMN text_edition_count INTEGER;
UPDATE text SET text_edition_count = (SELECT count(*) FROM edition e WHERE e.text_id = text.text_id);
ALTER TABLE text ADD COLUMN text_repertories TEXT;
UPDATE text SET text_repertories = (
       SELECT group_concat(repertory_name, '|') FROM (
              SELECT DISTINCT r.repertory_name FROM text__repertory tr
                JOIN repertory r ON r.repertory_id = tr.repertory_id
               WHERE tr.text_id = text.text_id ORDER BY r.repertory_name));

-- 4c. Manuscript (text copy): codex and text attributes as real FKs/values,
-- so the Manuscripts perspective can facet on them.
ALTER TABLE manuscript ADD COLUMN codex_holding_institution_id INTEGER
      REFERENCES codex_holding_institution (codex_holding_institution_id);
ALTER TABLE manuscript ADD COLUMN codex_type_id INTEGER REFERENCES codex_type (codex_type_id);
ALTER TABLE manuscript ADD COLUMN codex_dating_by_century INTEGER;
ALTER TABLE manuscript ADD COLUMN text_source_subtype_id INTEGER
      REFERENCES text_source_subtype (text_source_subtype_id);
ALTER TABLE manuscript ADD COLUMN manuscript_edition_count INTEGER;
UPDATE manuscript SET
       codex_holding_institution_id = (SELECT c.codex_holding_institution_id FROM codex c WHERE c.codex_id = manuscript.codex_id),
       codex_type_id                = (SELECT c.codex_type_id FROM codex c WHERE c.codex_id = manuscript.codex_id),
       codex_dating_by_century      = (SELECT c.codex_dating_by_century FROM codex c WHERE c.codex_id = manuscript.codex_id),
       text_source_subtype_id       = (SELECT t.text_source_subtype_id FROM text t WHERE t.text_id = manuscript.text_id),
       manuscript_edition_count     = (SELECT count(*) FROM edition__manuscript em WHERE em.manuscript_id = manuscript.manuscript_id);

-- 4d. Edition: publication year and number of manuscripts used.
ALTER TABLE edition ADD COLUMN edition_publication_year INTEGER;
UPDATE edition SET edition_publication_year =
       (SELECT p.publication_year FROM publication p WHERE p.publication_id = edition.publication_id);
ALTER TABLE edition ADD COLUMN edition_manuscript_count INTEGER;
UPDATE edition SET edition_manuscript_count =
       (SELECT count(*) FROM edition__manuscript em WHERE em.edition_id = edition.edition_id);

-- 4e. Publication, places, institutions, authors: counts and coordinates.
ALTER TABLE publication ADD COLUMN publication_edition_count INTEGER;
UPDATE publication SET publication_edition_count =
       (SELECT count(*) FROM edition e WHERE e.publication_id = publication.publication_id);
ALTER TABLE location ADD COLUMN latitude REAL;
ALTER TABLE location ADD COLUMN longitude REAL;
ALTER TABLE location ADD COLUMN location_codex_count INTEGER;
UPDATE location SET latitude = location_latitude, longitude = location_longitude,
       location_codex_count = (SELECT count(*) FROM codex c WHERE c.location_id = location.location_id);
ALTER TABLE institution ADD COLUMN latitude REAL;
ALTER TABLE institution ADD COLUMN longitude REAL;
UPDATE institution SET
       latitude  = (SELECT location_latitude  FROM location l WHERE l.location_id = institution.location_id),
       longitude = (SELECT location_longitude FROM location l WHERE l.location_id = institution.location_id);
ALTER TABLE codex_holding_institution ADD COLUMN codex_holding_institution_codex_count INTEGER;
UPDATE codex_holding_institution SET codex_holding_institution_codex_count =
       (SELECT count(*) FROM codex c WHERE c.codex_holding_institution_id = codex_holding_institution.codex_holding_institution_id);
ALTER TABLE author ADD COLUMN author_text_count INTEGER;
UPDATE author SET author_text_count = (SELECT count(*) FROM text t WHERE t.author_id = author.author_id);
`;
