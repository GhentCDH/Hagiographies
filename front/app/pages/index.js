// @ts-check
/**
 * Static pages and footer content, passed to mountUI({ menu, footer }).
 * Menu items carry inline `html`, so Pihka never fetches a page.
 */
import { menu as aboutData } from "./about-data.js";
import { menu as credits } from "./credits.js";

/** Pihka menu entries ({ id, label, html }), routed at #/:lang/page/:id. */
export const menu = [aboutData, credits];

/**
 * Footer content for shell.js's footer. Also valid for Pihka's default
 * footer shape (credits HTML + links).
 */
export const footer = {
    credits:
        "Data: CC BY 4.0. Code: MIT. The UGent Panno typeface and the GhentCDH logo are not covered by these licences.",
    links: [
        { label: "Ghent University", href: "https://www.ugent.be/en" },
        { label: "GhentCDH", href: "https://www.ghentcdh.ugent.be" },
        { label: "M-PATCH", href: "https://m-patch.ugent.be/en" },
    ],
};
