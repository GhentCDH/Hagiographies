// @ts-check
/**
 * Facts about this dataset version, shown on the front page and in the
 * credits. `exportDate` is filled in by the compose step (front/tools/compose.py);
 * `doi` and `repository` stay "TBD" until the deposit exists.
 */
export default {
    title:
        "Hagiographies: medieval Latin hagiographic texts, manuscripts and editions (M-PATCH prototype corpus)",
    shortTitle: "Hagiographies",
    version: "0.1.0-preview",
    /** ISO date (YYYY-MM-DD) of the SQLite export; null in the decomposed build. */
    exportDate: globalThis.__HAGIO_BUILD__?.exportDate ?? null,
    /** Build facts injected by compose.py (exportDate, builtAt, sha256, gitCommit, pihkaCommit); null when decomposed. */
    build: globalThis.__HAGIO_BUILD__ ?? null,
    publisher: "Ghent University",
    creators: ["M-PATCH project team, Ghent University"],
    licence: {
        data: "CC BY 4.0",
        dataUrl: "https://creativecommons.org/licenses/by/4.0/",
        code: "MIT",
        codeUrl: "https://opensource.org/license/mit",
        excluded:
            "UGent Panno fonts and the GhentCDH logo are not covered by these licences",
    },
    doi: "TBD",
    repository: "TBD",
    project: {
        name: "M-PATCH",
        url: "https://m-patch.ugent.be/en",
        grant: "FWO I004326N",
    },
    /** Recommended citation for the dataset; doi/version are substituted by citeDataset(). */
    citation:
        "M-PATCH project team (2026). Hagiographies: medieval Latin hagiographic texts, manuscripts and editions (M-PATCH prototype corpus) (Version {version}) [Data set]. Ghent University. {doi}",
    /** Article describing the M-PATCH approach. */
    paper: {
        text:
            "Breitbarth, A., Birkholz, J. M., Six, J., & Vanderputten, S. (2026). Towards multidisciplinary annotation of fluid historical corpora using linked data. Journal of Open Humanities Data, 12.",
        url: "https://biblio.ugent.be/publication/01KRNZ8WSCSKK1Y3BT7K5QWT2E",
    },
};

/** The dataset citation with version and DOI filled in. */
export function citeDataset(ds) {
    const doi = ds.doi && ds.doi !== "TBD"
        ? (/^https?:/.test(ds.doi) ? ds.doi : `https://doi.org/${ds.doi}`)
        : "DOI to be assigned.";
    return ds.citation.replace("{version}", ds.version).replace("{doi}", doi);
}
