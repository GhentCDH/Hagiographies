// @ts-check
/**
 * Composition root of the Hagiographies browser. It replaces Pihka's main.js
 * and bootstrap loading: configuration, plugins and pages are imported
 * statically, so nothing is fetched at runtime except the database (decomposed
 * build only) and the IIIF manifests and images (always, from their holders).
 * That keeps the single-file build working from file://.
 */
import { openDataset } from "../vendor/pihka/pihka/core/engine/index.js";
import { createComponentRegistry } from "../vendor/pihka/pihka/core/ui/registry/index.js";
import { installPlugin, mountUI, showStatus } from "../vendor/pihka/pihka/core/ui/index.js";
import * as defaults from "../vendor/pihka/pihka/core/ui/defaults/index.js";
import { normalizeEngineConfig } from "../vendor/pihka/pihka/bootstrap.js";
import * as iiifViewer from "../vendor/pihka/pihka/extensions/iiif-viewer/iiif-viewer-component.js";
import * as pointMap from "../vendor/pihka/pihka/extensions/point_map/point-map-component.js";
import * as geoFilterEngine from "../vendor/pihka/pihka/extensions/geo-filter/geo-filter-engine.js";
import * as geoFilter from "../vendor/pihka/pihka/extensions/geo-filter/geo-filter-component.js";
import * as embedded from "./datasource-embedded.js";
import * as shell from "./shell.js";
import config from "./config.js";
import { menu, footer } from "./pages/index.js";
import { installA11yPatches } from "./a11y-patches.js";

const DATABASE_URL = new URL("./database/hagiographies.sqlite", import.meta.url).href;

async function main() {
    const element = /** @type {HTMLElement} */ (document.getElementById("app"));
    const registry = createComponentRegistry();
    installPlugin(registry, defaults);
    const status = (message, error = null) => showStatus({ element, registry, message, error });
    status("Loading…");
    let session;
    try {
        session = await openDataset({
            databaseUrl: DATABASE_URL,
            config: normalizeEngineConfig(config),
            plugins: [embedded, geoFilterEngine],
            onProgress: ({ phase }) =>
                status(
                    {
                        downloading: "Reading the database…",
                        loading: "Opening the database…",
                        indexing: "Indexing for search…",
                    }[phase] || "Loading…",
                ),
        });
        for (const plugin of [iiifViewer, pointMap, geoFilter, shell]) installPlugin(registry, plugin);
        registry.seal();
        installA11yPatches(element);
        const ui = await mountUI({ element, registry, ...session, config, footer, menu });
        window.addEventListener("pagehide", function dispose(event) {
            if (event.persisted) return;
            window.removeEventListener("pagehide", dispose);
            ui.unmount();
            session.close().catch((error) => console.warn("[hagiographies] cleanup failed:", error));
        });
    } catch (error) {
        await session?.close().catch(() => {});
        console.error("[hagiographies] startup failed:", error);
        status(null, error);
    }
}

main();
