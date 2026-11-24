// @ts-check
/**
 * UGent shell for the Hagiographies browser: a Pihka UI plugin that replaces
 * the header, footer, front page and static-page renderer. It matches the
 * prop contracts of the defaults it overrides (front/vendor/pihka/pihka/core/ui/defaults):
 *
 *   control/header  { crumbs, lang, languages, onLangChange, search, menu }  (app.js Layout)
 *   control/footer  { footer, lang }                                        (app.js Layout)
 *   page/home       { perspectives, store, lang }                           (app.js App, home route)
 *   page/static     { item, lang }                                          (app.js App, /:lang/page/:id)
 *
 * Stylesheet: theme/ugent.css is linked from index.html after Pico and base.css
 * (so it wins the cascade before first paint); it is not registered here.
 */
import { h, Fragment } from "preact";
import { useEffect, useRef } from "preact/hooks";
import {
    buildPath,
    localize,
    registeredComponent,
    useQuery,
    useRouter,
} from "../vendor/pihka/pihka/core/ui/index.js";
import { preferredView } from "../vendor/pihka/pihka/core/ui/runtime/perspectives.js";
import config from "./config.js";
import dataset, { citeDataset } from "./dataset.js";
import { datasetInfo } from "./dataset-info.js";

const GlobalSearchInput = registeredComponent("control", "global-search");
const ThemeToggle = registeredComponent("control", "theme");
const LangSwitcher = registeredComponent("control", "language");

const asset = (path) => new URL(path, import.meta.url).href;
const LOGO_GHENTCDH = asset("./assets/logos/ghentcdh_logo_blue_text_transparent_bg_landscape.svg");
const LOGO_GHENTCDH_DARK = asset("./assets/logos/ghentcdh_logo_white_text_transparent_bg_landscape.svg");

/** GhentCDH landscape logo: blue text in light mode, white text in dark mode (see ugent.css). */
const ghentcdhLogo = (height, extra = {}) => [
    h("img", { class: "logo-light", src: LOGO_GHENTCDH, alt: "Ghent Centre for Digital Humanities", height, width: Math.round(height * 190 / 102), ...extra }),
    h("img", { class: "logo-dark", src: LOGO_GHENTCDH_DARK, alt: "", "aria-hidden": "true", height, width: Math.round(height * 190 / 102), ...extra }),
];
const PIHKA_URL = "https://github.com/GhentCDH/Pihka";

const SITE_TITLE = "Hagiographies";
const SITE_SUBTITLE = "M-PATCH prototype corpus";

const external = { target: "_blank", rel: "noopener noreferrer" };
const isExternal = (href) => /^https?:\/\//i.test(href || "");

/** Plain text of a crumb (string or a Preact link vnode). */
function crumbText(crumb) {
    if (crumb == null || typeof crumb === "boolean") return "";
    if (typeof crumb === "string" || typeof crumb === "number") return String(crumb);
    const children = crumb.props?.children;
    return Array.isArray(children) ? children.map(crumbText).join("") : crumbText(children);
}

/** Move focus to <main> (hash routing rules out a plain #fragment skip link). */
function skipToMain(event) {
    const main = /** @type {HTMLElement|null} */ (document.querySelector("#app > main"));
    if (!main) return;
    event.preventDefault();
    main.setAttribute("tabindex", "-1");
    main.focus();
}

/** Configured perspectives from config.js, in config order: the header tabs. */
function navPerspectives() {
    const list = Array.isArray(config?.perspectives) ? config.perspectives : [];
    return list.filter((p) => p && p.id && p.nav !== false);
}

// ─── control/header ──────────────────────────────────────────────────────

/**
 * UGent header: blue top rule, GhentCDH logo, site title, global search and
 * theme toggle, then a tab bar (Home, perspectives, static pages) and a
 * breadcrumb for detail routes. Also keeps document.title in step with the
 * route.
 */
export function Header({ crumbs = null, lang, languages = null, onLangChange = null, search = null, menu = [] }) {
    const route = useRouter();
    const current = route?.perspective || null;
    const crumbList = (crumbs || []).filter((c) => c != null && c !== false);

    const titleParts = crumbList.map(crumbText).filter(Boolean).reverse();
    const docTitle = [...titleParts, SITE_TITLE].join(" | ");
    useEffect(() => {
        document.title = docTitle;
    }, [docTitle]);

    const tab = (key, href, label, active) =>
        h("li", { key },
            h("a", {
                href,
                ...(isExternal(href) ? external : {}),
                ...(active ? { "aria-current": "page" } : {}),
            }, label),
        );

    return h("header", { class: "ugent-header" },
        h("a", { class: "skip-link", href: "#", onClick: skipToMain }, "Skip to main content"),
        h("div", { class: "ugent-header-bar container-fluid" },
            h("a", { class: "ugent-brand", href: buildPath("/") },
                h("strong", null, SITE_TITLE),
                h("small", null, SITE_SUBTITLE),
            ),
            h("div", { class: "ugent-header-tools" },
                search && h(GlobalSearchInput, { lang: search.lang, value: search.value, key: search.value }),
                h(ThemeToggle, null),
                Array.isArray(languages) && languages.length > 1 &&
                    h(LangSwitcher, { lang, languages, onChange: onLangChange }),
            ),
        ),
        h("nav", { class: "ugent-tabs", "aria-label": "Main" },
            h("ul", { class: "container-fluid" },
                tab("home", buildPath("/"), "Home", !current),
                ...navPerspectives().map((p) =>
                    tab(`p-${p.id}`, buildPath(`/${p.id}`), localize(p.label, lang, p.name || p.id), current === p.id),
                ),
                ...(menu || []).map((item, i) => {
                    const href = typeof item.href === "string" ? item.href : buildPath(`/${lang}/page/${item.id}`);
                    const active = current === "page" && route?.id === item.id;
                    return tab(`m-${item.id || i}`, href, localize(item.label, lang, item.id || item.href), active);
                }),
            ),
        ),
        crumbList.length > 1 && h("nav", { class: "ugent-crumbs container-fluid", "aria-label": "Breadcrumb" },
            h("ol", null,
                crumbList.map((crumb, i) =>
                    h("li", { key: i, ...(i === crumbList.length - 1 ? { "aria-current": "location" } : {}) }, crumb),
                ),
            ),
        ),
    );
}

// ─── control/footer ──────────────────────────────────────────────────────

/**
 * UGent footer: text on the left (M-PATCH line, licence line from `footer.credits`, links from
 * `footer.links`, "Powered by Pihka"), the GhentCDH logo on the right. Keeps Pihka's .site-footer class so
 * base.css's desktop table layout still places it below the viewport.
 */
export function SiteFooter({ footer = null, lang = "en" }) {
    const credits = footer ? localize(footer.credits, lang, "") : "";
    const links = Array.isArray(footer?.links) ? footer.links : [];
    // The logo is exactly as tall as the footer text: copy the text column's
    // height into --footer-text-h whenever it changes (wrapping, font load).
    const footerRef = useRef(null);
    useEffect(() => {
        const el = footerRef.current;
        const text = el?.querySelector(".ugent-footer-text");
        if (!text || typeof ResizeObserver !== "function") return;
        const observer = new ResizeObserver(([entry]) =>
            el.style.setProperty("--footer-text-h", `${Math.round(entry.borderBoxSize?.[0]?.blockSize ?? text.offsetHeight)}px`));
        observer.observe(text);
        return () => observer.disconnect();
    }, []);
    return h("footer", { class: "site-footer ugent-footer", ref: footerRef },
        h("div", { class: "ugent-footer-inner container-fluid" },
            h("div", { class: "ugent-footer-text" },
                h("p", null,
                    h("strong", null, SITE_TITLE), ` (${SITE_SUBTITLE}), version ${dataset.version}. `,
                    "A dataset of the ", h("a", { href: dataset.project.url, ...external }, "M-PATCH"),
                    " project, Ghent University, funded by the Research Foundation – Flanders (FWO, I004326N).",
                ),
                credits && h("p", { dangerouslySetInnerHTML: { __html: credits } }),
                links.length > 0 && h("nav", { class: "footer-links", "aria-label": "Footer" },
                    h("ul", null, links.map((link, i) =>
                        h("li", { key: i },
                            h("a", { href: link.href, ...(isExternal(link.href) ? external : {}) },
                                localize(link.label, lang, link.href)),
                        ),
                    )),
                ),
                h("p", { class: "powered-by" }, "Powered by ", h("a", { href: PIHKA_URL, ...external }, "Pihka"), "."),
            ),
            h("div", { class: "ugent-footer-logos" },
                h("a", { href: "https://www.ghentcdh.ugent.be", ...external, class: "logo-ghentcdh" },
                    ...ghentcdhLogo(56, { loading: "lazy" })),
            ),
        ),
    );
}

// ─── page/home ───────────────────────────────────────────────────────────

const number = new Intl.NumberFormat("en");

function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "unknown";
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB (${number.format(bytes)} bytes)` : `${number.format(bytes)} bytes`;
}

/** Descriptions for the entity tiles, keyed by perspective id or table. */
const TILE_TEXT = {
    text: "Hagiographic works, with dating, author and places.",
    texts: "Hagiographic works, with dating, author and places.",
    manuscript: "Copies of a text in a codex, with folio ranges.",
    manuscripts: "Copies of a text in a codex, with folio ranges.",
    codex: "Physical books: shelfmark, holding institution, images.",
    codices: "Physical books: shelfmark, holding institution, images.",
    edition: "Printed editions and the manuscripts they used.",
    editions: "Printed editions and the manuscripts they used.",
    publication: "Books and journal volumes that contain editions.",
    publications: "Books and journal volumes that contain editions.",
    location: "Places, with coordinates where known.",
    locations: "Places, with coordinates where known.",
    places: "Places, with coordinates where known.",
    institution: "Holding and historical institutions.",
    institutions: "Holding and historical institutions.",
};

function tileText(p) {
    const configured = navPerspectives().find((c) => c.id === p.id);
    return localize(configured?.description, "en", "") || TILE_TEXT[p.id] || TILE_TEXT[p.table] || "";
}

function EntityTiles({ perspectives, store, lang }) {
    const counts = useQuery(
        () => Promise.all(perspectives.map((p) =>
            store.queryTable(p.table, { pageSize: 1 }).then((r) => r.totalRows, () => null))),
        [store, perspectives],
    );
    return h("ul", { class: "entity-tiles", role: "list" },
        perspectives.map((p, i) => {
            const count = counts.data?.[i];
            const label = localize(p.label, lang, p.name);
            return h("li", { key: p.id },
                h("a", { class: "entity-tile", href: buildPath(`/${lang}/${p.id}/${preferredView(p) || "table"}`) },
                    h("span", { class: "entity-tile-count" },
                        count == null ? (counts.loading ? "…" : "–") : number.format(count)),
                    h("span", { class: "entity-tile-name" }, label),
                    tileText(p) && h("span", { class: "entity-tile-text" }, tileText(p)),
                ),
            );
        }),
    );
}

function DatasetBox() {
    const info = useQuery(() => datasetInfo, []);
    const doi = dataset.doi && dataset.doi !== "TBD"
        ? h("a", { href: /^https?:/.test(dataset.doi) ? dataset.doi : `https://doi.org/${dataset.doi}`, ...external }, dataset.doi)
        : "to be assigned";
    const repository = dataset.repository && dataset.repository !== "TBD"
        ? h("a", { href: dataset.repository, ...external }, dataset.repository)
        : "to be announced";
    const sha = info.data?.sha256;
    const row = (term, value) => h(Fragment, null, h("dt", null, term), h("dd", null, value));
    return h("section", { class: "dataset-box", "aria-labelledby": "dataset-box-title" },
        h("h2", { id: "dataset-box-title" }, "This dataset"),
        h("dl", null,
            row("Title", dataset.title),
            row("Version", dataset.version),
            row("Export date", dataset.exportDate || "not set (development build)"),
            row("Licence", h(Fragment, null,
                "Data ", h("a", { href: dataset.licence.dataUrl, ...external }, dataset.licence.data),
                ", code ", h("a", { href: dataset.licence.codeUrl, ...external }, dataset.licence.code),
                ". ", dataset.licence.excluded, ".")),
            row("DOI", doi),
            row("Repository", repository),
            row("File size", info.loading ? "…" : formatBytes(info.data?.bytes)),
            row("SHA-256", info.loading ? "…" : sha ? h("code", { class: "hash" }, sha) : "not available"),
        ),
        h("p", { class: "dataset-box-note" },
            "The SHA-256 is computed in your browser from the database this page opened. ",
            "Compare it with the checksum published next to the deposited .sqlite file."),
    );
}

function CiteBox() {
    return h("section", { class: "cite-box", "aria-labelledby": "cite-box-title" },
        h("h2", { id: "cite-box-title" }, "How to cite"),
        h("p", null, "If you use this dataset, please cite it:"),
        h("blockquote", { class: "citation" }, citeDataset(dataset)),
        h("p", null, "For the M-PATCH approach, cite:"),
        h("blockquote", { class: "citation" }, dataset.paper.text, " ",
            h("a", { href: dataset.paper.url, ...external }, dataset.paper.url)),
    );
}

/**
 * Front page: M-PATCH intro, entity tiles with live counts, the dataset
 * facts box and the citation. Auto-generated table cards (kind "table")
 * go in a collapsed list below the tiles.
 */
export function Home({ perspectives = [], store, lang = "en" }) {
    const configured = perspectives.filter((p) => p.kind === "perspective");
    const tables = perspectives.filter((p) => p.kind !== "perspective");
    // Tiles in config.js order (loadPerspectives sorts them by name).
    const order = navPerspectives().map((p) => p.id);
    const rank = (p) => (order.includes(p.id) ? order.indexOf(p.id) : order.length);
    const tiles = (configured.length > 0 ? configured : tables).slice().sort((a, b) => rank(a) - rank(b));
    const aboutHref = buildPath(`/${lang}/page/about-data`);
    return h("div", { class: "home" },
        h("section", { class: "intro", "aria-labelledby": "intro-title" },
            h("p", { class: "eyebrow" }, "M-PATCH prototype corpus"),
            h("h1", { id: "intro-title" }, "Hagiographies"),
            h("p", null,
                "Medieval Latin hagiographic texts, the manuscripts that transmit them, ",
                "the codices that hold those manuscripts, and their printed editions."),
            h("p", null,
                h("a", { href: dataset.project.url, ...external }, "M-PATCH"),
                " builds a reusable, modular infrastructure for the multidisciplinary annotation ",
                "of historical texts in all their material forms: digitised images through IIIF, ",
                "transcriptions and linked annotations. It is tested on this prototype corpus of ",
                "tenth-century Latin hagiographies from Lotharingia: about 190 texts, 1,600 ",
                "manuscripts and 780 editions."),
            h("p", null,
                "This browser is the static, citable companion of one dataset version. Everything ",
                "runs in your browser, from the SQLite file embedded in this page. ",
                h("a", { href: aboutHref }, "About the data"), "."),
        ),
        h("section", { class: "browse", "aria-labelledby": "browse-title" },
            h("h2", { id: "browse-title" }, "Browse"),
            h(EntityTiles, { perspectives: tiles, store, lang }),
            configured.length > 0 && tables.length > 0 && h("details", { class: "all-tables" },
                h("summary", null, `All tables (${tables.length})`),
                h("ul", { class: "table-list" },
                    tables.map((p) => h("li", { key: p.id },
                        h("a", { href: buildPath(`/${lang}/${p.id}/${preferredView(p) || "table"}`) },
                            localize(p.label, lang, p.name))))),
            ),
        ),
        h("div", { class: "home-facts" },
            h(DatasetBox, null),
            h(CiteBox, null),
        ),
    );
}

// ─── page/static ─────────────────────────────────────────────────────────

/**
 * Static menu page rendered from inline HTML only: `item.html` is a string,
 * a { lang: html } map, or a function (lang) => html. Never fetches, so it
 * works from file:// and in the single-file build.
 */
export function StaticPage({ item, lang }) {
    const raw = typeof item?.html === "function" ? item.html(lang) : localize(item?.html, lang, "");
    useEffect(() => {
        window.scrollTo(0, 0);
    }, [item?.id]);
    if (!raw) {
        return h("article", { class: "static-page" }, h("p", null, "This page has no content."));
    }
    return h("article", { class: "static-page", dangerouslySetInnerHTML: { __html: raw } });
}

/** Pihka UI plugin entry point. */
export function register(api) {
    api.registerComponent({ kind: "control", id: "header", component: Header });
    api.registerComponent({ kind: "control", id: "footer", component: SiteFooter });
    api.registerComponent({ kind: "page", id: "home", component: Home });
    api.registerComponent({ kind: "page", id: "static", component: StaticPage });
}
