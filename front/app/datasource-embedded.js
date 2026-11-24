// @ts-check
/**
 * Engine plugin: the "embedded" datasource.
 *
 * Reads the database bytes from an inline <script id="hagio-db"
 * type="application/octet-stream"> (base64, single-file build) or, when that
 * element is absent, fetches the configured database URL (decomposed build).
 * The bytes go to Pihka's own download DataSource through a blob: URL, which
 * also works from file://. Once open, the in-memory copy is shaped for the
 * public browser with PREPARE_SQL (see prepare.js); the deposited file itself
 * is never changed.
 */
import { DataSource } from "../vendor/pihka/pihka/core/engine/datasource.js";
import { PREPARE_SQL } from "./prepare.js";
import { publishDatasetInfo } from "./dataset-info.js";

/** @param {string} base64 */
async function decodeBase64(base64) {
    const res = await fetch(`data:application/octet-stream;base64,${base64.replace(/\s+/g, "")}`);
    return new Uint8Array(await res.arrayBuffer());
}

class EmbeddedSource extends EventTarget {
    /** @type {DataSource|null} */
    #inner = null;
    #blobUrl = "";
    capabilities = { readOnly: false };
    ready;

    /** @param {string} url */
    constructor(url) {
        super();
        this.ready = this.#init(url);
    }

    /** @param {string} url */
    async #init(url) {
        await Promise.resolve(); // let openDataset attach its listeners first
        this.dispatchEvent(new CustomEvent("downloading"));
        const inline = document.getElementById("hagio-db");
        /** @type {Uint8Array} */
        let bytes;
        if (inline?.textContent) {
            bytes = await decodeBase64(inline.textContent);
        } else {
            const res = await fetch(url);
            if (!res.ok) throw new Error(`Fetching ${url} failed: ${res.status} ${res.statusText}`);
            bytes = new Uint8Array(await res.arrayBuffer());
        }
        publishDatasetInfo(bytes, inline ? "embedded" : "fetched");
        this.#blobUrl = URL.createObjectURL(new Blob([bytes], { type: "application/vnd.sqlite3" }));
        const inner = new DataSource(this.#blobUrl);
        inner.addEventListener("loading", (event) =>
            this.dispatchEvent(new CustomEvent("loading", { detail: /** @type {CustomEvent} */ (event).detail })),
        );
        this.#inner = inner;
        await inner.ready;
        URL.revokeObjectURL(this.#blobUrl);
        await inner.exec(PREPARE_SQL);
        this.dispatchEvent(new CustomEvent("ready"));
    }

    /** @param {string} sql @param {Object} [options] */
    exec(sql, options) {
        if (!this.#inner) throw new Error("Embedded datasource not ready");
        return this.#inner.exec(sql, options);
    }

    metadata() {
        if (!this.#inner) throw new Error("Embedded datasource not ready");
        return this.#inner.metadata();
    }

    async close() {
        await this.#inner?.close();
        this.#inner = null;
    }
}

export function register(api) {
    api.registerDataSource("embedded", (url) => new EmbeddedSource(url));
}
