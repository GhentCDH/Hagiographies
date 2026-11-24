// @ts-check
/**
 * Pihka configuration for the Hagiographies browser.
 *
 * config.generated.js (front/tools/gen_config.py) supplies a label for every
 * table and column plus generic column types (url, long notes, Mathesar's
 * number grouping). This file adds the hand-written parts and wins on merge:
 * perspectives, facets, table visibility and column overrides.
 *
 * Pihka semantics this relies on (core/ui/runtime/*, core/engine/*):
 * - Perspective ids equal their table names, so the FK links Pihka renders as
 *   /<referenced table>/<id> land on the configured perspective.
 * - Configured facets support only "range" (numeric columns) and
 *   "dropdown"/"checkbox"/"values" (one value per row). Plain (non-FK)
 *   columns must use "dropdown" or "checkbox": "values" on them is not
 *   restored from the URL (core/ui/defaults/filter-codecs.js).
 * - A facet on a hidden column is dropped (core/ui/runtime/presentation.js),
 *   so facet columns stay visible.
 * - Hidden tables still label FKs but lose their detail links and are left
 *   out of related-record sections. Junction and link tables therefore stay
 *   visible; the home page shows only configured perspectives.
 */
import generated from "./config.generated.js";

const noGrouping = { type: "number", format: { useGrouping: false } };

/** Lookup tables: FK labels only, no own card, page or related section. */
const LOOKUPS = [
    "author_milieu", "codex_link_type", "codex_preservation_status", "codex_type",
    "dating_confidence", "edition_link_type", "manuscript__manuscript_type",
    "manuscript_link_type", "origin_confidence", "provenance_confidence", "repertory",
    "text_form", "text_source_subtype", "text_source_type", "vernacular_region",
];

/** Hand-written table settings, deep-merged over the generated ones. */
const tables = {
    text: {
        label: "Texts",
        columns: {
            text_unique_identifier: { label: "Text" },
            text_form_id: { label: "Form" },
            text_reecriture: { label: "Réécriture" },
            reecriture_of_text_id: { label: "Réécriture of" },
            text_dating_range_start: { label: "Dated from", ...noGrouping },
            text_dating_range_end: { label: "Dated to", ...noGrouping },
            text_dating_quarter_century: { label: "Quarter century" },
            text_approximate_token_count: { label: "Approx. tokens" },
            text_repertories: { label: "Repertories", type: "list" },
        },
    },
    codex: {
        label: "Codices",
        options: { point_map: { clustering: true } },
        columns: {
            codex_unique_identifier: { label: "Codex" },
            codex_holding_institution_id: { label: "Holding institution" },
            location_id: { label: "Location" },
            codex_type_id: { label: "Codex type" },
            codex_dating_by_century: { label: "Century", ...noGrouping },
            codex_dating_range_start: { label: "Dated from", ...noGrouping },
            codex_dating_range_end: { label: "Dated to", ...noGrouping },
            codex_iiif_manifest: { label: "IIIF", type: "iiif", fts: false },
            codex_has_iiif: { label: "Has IIIF images" },
            codex_manuscript_count: { label: "Texts in codex" },
        },
    },
    manuscript: {
        label: "Manuscripts",
        columns: {
            manuscript_unique_identifier: { label: "Manuscript" },
            codex_holding_institution_id: { label: "Holding institution (codex)" },
            codex_type_id: { label: "Codex type" },
            codex_dating_by_century: { label: "Century (codex)", ...noGrouping },
            text_source_subtype_id: { label: "Source subtype (text)" },
            manuscript_edition_count: { label: "Used by editions" },
        },
    },
    edition: {
        label: "Editions",
        columns: {
            edition_unique_identifier: { label: "Edition" },
            edition_publication_year: { label: "Publication year", ...noGrouping },
            reprint_of_edition_id: { label: "Reprint of" },
            edition_manuscript_count: { label: "Manuscripts used" },
        },
    },
    publication: {
        label: "Publications",
        columns: {
            publication_unique_identifier: { label: "Publication" },
            publication_full_reference: { type: "text", maxWords: 30 },
            publication_edition_count: { label: "Editions" },
        },
    },
    location: {
        label: "Places",
        options: { point_map: { clustering: false } },
        columns: {
            location_name: { label: "Place" },
            location_codex_count: { label: "Codices" },
        },
    },
    codex_holding_institution: {
        label: "Holding institutions",
        columns: { codex_holding_institution_codex_count: { label: "Codices" } },
    },
    institution: { label: "Institutions" },
    diocese: { label: "Dioceses" },
    archdiocese: { label: "Archdioceses" },
    author: {
        label: "Authors",
        columns: {
            author_milieu_id: { label: "Milieu" },
            author_text_count: { label: "Texts" },
        },
    },
    codex_link: { label: "Codex links", columns: { codex_link_type_id: { label: "Link type" } } },
    edition_link: { label: "Edition links", columns: { edition_link_type_id: { label: "Link type" } } },
    manuscript_link: { label: "Manuscript links", columns: { manuscript_link_type_id: { label: "Link type" } } },
    text__repertory: { label: "Repertory entries" },
    edition__edition: { label: "Consulted editions" },
    edition__manuscript: { label: "Manuscripts used by editions" },
    manuscript__manuscript: { label: "Related manuscripts" },
    ...Object.fromEntries(LOOKUPS.map((t) => [t, { hidden: true }])),
};

const dropdown = (field, label) => ({ field, type: "dropdown", ...(label ? { label } : {}) });
const checkbox = (field, label) => ({ field, type: "checkbox", ...(label ? { label } : {}) });
const range = (field, label) => ({ field, type: "range", ...(label ? { label } : {}) });

/** Shared perspective defaults; allowed_views is left out so Pihka offers
 * every list view the table supports (map only where lat/lon exist). */
const perspective = (id, label, default_sort, facets, extra = {}) => ({
    id, label, table: id, default_sort, default_view: "table", page_size: 50, facets, ...extra,
});

const perspectives = [
    perspective("text", "Texts", "text_unique_identifier", [
        dropdown("text_form_id"),
        dropdown("text_source_type_id"),
        dropdown("text_source_subtype_id"),
        range("text_dating_range_start"),
        range("text_dating_range_end"),
        dropdown("text_dating_quarter_century"),
        dropdown("dating_confidence_id"),
        dropdown("author_id"),
        checkbox("text_author_in_destinatary_institution"),
        dropdown("creation_archdiocese_id"),
        dropdown("creation_diocese_id"),
        dropdown("creation_institution_id"),
        dropdown("destinatary_archdiocese_id"),
        dropdown("destinatary_diocese_id"),
        dropdown("destinatary_institution_id"),
        checkbox("text_reecriture"),
        range("text_manuscript_count", "Number of manuscripts"),
        range("text_edition_count", "Number of editions"),
    ]),
    perspective("codex", "Codices", "codex_unique_identifier", [
        checkbox("codex_has_iiif"),
        dropdown("codex_holding_institution_id"),
        dropdown("location_id"),
        dropdown("codex_type_id"),
        dropdown("codex_preservation_status_id"),
        range("codex_dating_by_century"),
        range("codex_dating_range_start"),
        range("codex_dating_range_end"),
        dropdown("dating_confidence_id"),
        dropdown("vernacular_region_id"),
        dropdown("origin_archdiocese_id"),
        dropdown("origin_diocese_id"),
        dropdown("origin_institution_id"),
        dropdown("provenance_early_institution_id"),
        dropdown("provenance_later_institution_id"),
        checkbox("codex_legendiers_usable"),
        checkbox("codex_composite"),
        range("codex_manuscript_count", "Number of texts"),
    ]),
    perspective("manuscript", "Manuscripts", "manuscript_unique_identifier", [
        dropdown("text_id"),
        dropdown("text_source_subtype_id"),
        dropdown("codex_id"),
        dropdown("codex_holding_institution_id"),
        dropdown("codex_type_id"),
        range("codex_dating_by_century"),
        range("manuscript_edition_count", "Number of editions using it"),
    ]),
    perspective("edition", "Editions", "edition_unique_identifier", [
        dropdown("text_id"),
        dropdown("publication_id"),
        range("edition_publication_year"),
        checkbox("edition_reprint"),
        checkbox("edition_collation_done"),
        range("edition_manuscript_count", "Number of manuscripts used"),
    ]),
    perspective("publication", "Publications", "publication_unique_identifier", [
        range("publication_year"),
        range("publication_edition_count", "Number of editions"),
    ]),
    perspective("location", "Places", "location_name", [
        range("location_codex_count", "Number of codices"),
    ]),
    perspective("codex_holding_institution", "Holding institutions", "codex_holding_institution_name", [
        range("codex_holding_institution_codex_count", "Number of codices"),
    ], { nav: false }),
    perspective("institution", "Institutions", "institution_name", [dropdown("location_id")], { nav: false }),
    perspective("diocese", "Dioceses", "diocese_name", [dropdown("location_id")], { nav: false }),
    perspective("archdiocese", "Archdioceses", "archdiocese_name", [dropdown("location_id")], { nav: false }),
    perspective("author", "Authors", "author_name", [
        dropdown("author_milieu_id"),
        range("author_text_count", "Number of texts"),
    ]),
];

function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Recursive merge; `over` wins, arrays and scalars are replaced. */
function merge(base, over) {
    const out = { ...base };
    for (const [key, value] of Object.entries(over)) {
        out[key] = isPlainObject(value) && isPlainObject(base[key]) ? merge(base[key], value) : value;
    }
    return out;
}

const config = {
    defaultLanguage: "en",
    languages: ["en"],
    datasource: { type: "embedded" },
    enrichment: { fts: "trigram" },
    perspectives,
    tables: merge(generated.tables, tables),
};

export default config;
