// @ts-check
/**
 * Facts about the database bytes actually loaded (size, sha256), published by
 * the embedded datasource once it has read them. The front page shows them so a
 * reader can match the page against the deposited .sqlite file.
 */

/** @type {(info: {bytes: number, sha256: string|null, source: "embedded"|"fetched"}) => void} */
let resolveInfo;

/** @type {Promise<{bytes: number, sha256: string|null, source: "embedded"|"fetched"}>} */
export const datasetInfo = new Promise((resolve) => {
    resolveInfo = resolve;
});

/** @param {Uint8Array} bytes @param {"embedded"|"fetched"} source */
export async function publishDatasetInfo(bytes, source) {
    let sha256 = null;
    try {
        const digest = await crypto.subtle.digest("SHA-256", bytes);
        sha256 = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
    } catch (error) {
        // crypto.subtle needs a secure context; file:// and localhost qualify.
        console.warn("[hagiographies] sha256 unavailable:", error);
    }
    resolveInfo({ bytes: bytes.byteLength, sha256, source });
}
