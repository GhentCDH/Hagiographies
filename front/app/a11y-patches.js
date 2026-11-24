// @ts-check
/**
 * Small accessibility repairs for Pihka markup we cannot change (the submodule
 * stays untouched). Each one is an upstream issue; drop it here once Pihka
 * fixes it.
 *
 * - The page-size <select> in the list toolbar has no accessible name
 *   (core/ui/defaults/faceted-view.js).
 */
const LABELS = [[".faceted-pagesize", "Rows per page"]];

function label(root) {
    for (const [selector, text] of LABELS)
        for (const el of root.querySelectorAll(`${selector}:not([aria-label])`)) el.setAttribute("aria-label", text);
}

export function installA11yPatches(root = document.body) {
    label(root);
    new MutationObserver(() => label(root)).observe(root, { childList: true, subtree: true });
}
