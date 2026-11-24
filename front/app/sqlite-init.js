// @ts-check
/**
 * Wraps sqlite-wasm's init so the single-file build can hand it the wasm
 * binary from an inline <script id="hagio-wasm" type="application/octet-stream">
 * (base64) instead of fetching sqlite3.wasm next to index.mjs.
 *
 * Only the composed file maps "@sqlite.org/sqlite-wasm" to this module (and
 * "sqlite-wasm-real" to the vendored index.mjs). The decomposed version maps
 * "@sqlite.org/sqlite-wasm" straight to the vendored file and never loads this.
 */
import sqlite3InitModule from "sqlite-wasm-real";

export { sqlite3Worker1Promiser } from "sqlite-wasm-real";

/** @param {string} base64 */
function decodeBase64(base64) {
    const clean = base64.replace(/\s+/g, "");
    // @ts-ignore Uint8Array.fromBase64 is newer than the TS lib in use.
    if (typeof Uint8Array.fromBase64 === "function") return Uint8Array.fromBase64(clean);
    const binary = atob(clean);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return bytes;
}

export default function init(args = {}) {
    const inline = document.getElementById("hagio-wasm");
    if (inline?.textContent) return sqlite3InitModule({ ...args, wasmBinary: decodeBase64(inline.textContent) });
    return sqlite3InitModule(args);
}
