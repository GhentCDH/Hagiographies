# front/: Hagiographies browser

A static browser for the SQLite export of the Hagiographies database (M-PATCH prototype corpus). It has:
- faceted perspectives: texts, codices, manuscripts, editions, publications, places and authors;
- full-text search;
- IIIF viewers (TIFY) for digitised codices;
- maps;
- pages that explain the data and credit the people behind it.

It is built from [Pihka](https://github.com/GhentCDH/Pihka) (GhentCDH) in UGent house style.

It comes in two forms:

| | What | For |
|---|---|---|
| **Decomposed** | `front/index.html` plus plain ES modules in `front/app/` and the Pihka submodule. No build step. | Development: edit a file, reload. |
| **Single file** | `front/dist/hagiographies.html`. Everything is inlined, including the database, the sqlite wasm, fonts and the basemap. | Shipping next to `hagiographies.sqlite` on a research data repository. Opens with a double-click (`file://`). |

The only network traffic either form makes is to the IIIF holders (Gallica, Adore, e-codices, …), for manifests and images.

## Use

```sh
git submodule update --init front/vendor/pihka   # once
just front_serve          # http://localhost:9162/ — links data/hagiographies_full_export.sqlite in
just front_config         # after changing the Mathesar record summaries / column display JSON
just front_compose        # → front/dist/: hagiographies.html, hagiographies.sqlite, SHA256SUMS, README.txt
just front_compose --release   # refuses while the DOI is TBD, the version is a preview or the tree is dirty
```

`front_serve` uses `tools/serve.py`, a stdlib server with HTTP Range support. The PMTiles basemap needs Range requests, and `python -m http.server` does not answer them.

## Releasing a dataset version

1. Refresh the export from the curated database: `just db_clone_qas` (or a PRD clone), then `just pg_export_sqlite`. This overwrites the local Docker database.
2. In `app/dataset.js`, set `version` and, once the repository has reserved it, `doi`.
3. Commit, then run `just front_compose --release`.
4. Deposit the four files in `front/dist/` as one version on the repository: `hagiographies.html`, `hagiographies.sqlite`, `SHA256SUMS` and `README.txt`. The `.sqlite` there is the **public copy**: compose removes restricted (`files.m-patch.ugent.be`) and placeholder links, then VACUUMs, and the HTML embeds that same copy. The page shows the sha256 of the database it embeds, so readers can match the two files.

## How it is put together

- **`app/main.js`** is the composition root and replaces Pihka's `main.js`. Config, plugins and pages are imported statically; nothing is fetched at runtime except the database (decomposed form only).
- **`app/datasource-embedded.js`** is an engine plugin, the `embedded` datasource. It reads the database from an inline base64 block (single file) or fetches it (decomposed). It hands the database to Pihka's DataSource through a `blob:` URL, then runs `app/prepare.js` on the **in-memory copy**:
  - it removes restricted links (`files.m-patch.ugent.be`) and placeholder links;
  - it unwraps IIIF manifest URLs;
  - it adds derived columns: `label`, counts, `latitude`/`longitude` for the map, and `codex_iiif_manifest` for the viewer.

  The deposited `.sqlite` is never changed.
- **`app/config.js`** holds the perspectives, facets and labels. Column labels come from `config.generated.js`, which `tools/gen_config.py` builds from the Mathesar JSON in `utils/mathesar/`, so names never drift from what researchers see in Mathesar.
- **`app/shell.js`** contains the UGent header, footer, front page and static pages, as Pihka `register(api)` overrides.
- **`app/theme/ugent.css`** is the UGent house style, ported from IPEMArchive: UGent Panno for display text, Arial for reading text, and no other fonts. It maps onto Pico/Pihka variables and supports light and dark mode.
- **`app/sqlite-init.js`**: in the single file, it gives sqlite-wasm its binary from an inline block (`wasmBinary`).
- **`app/a11y-patches.js`** holds small accessibility repairs for Pihka markup.
- **`tools/compose.py`** builds the single file, using the Python stdlib only. No bundler, no transpiler: every module is kept verbatim apart from rewritten import specifiers, and loaded from a `blob:` import map at startup.
- **`vendor/pihka`** is a git submodule and is **never edited**. Gaps found in Pihka are listed in `TASKS.md` (Discovered) as upstream issues.

## Licences

- Data: CC BY 4.0. Code in `front/`: MIT.
- Pihka: MIT. TIFY: AGPL-3.0 (source: https://github.com/tify-iiif-viewer/tify). MapLibre GL JS and PMTiles: BSD-3. SQLite Wasm: Apache-2.0 (SQLite itself is public domain). Preact: MIT.
- **Not covered:** the UGent Panno typeface and the GhentCDH logo remain the property of Ghent University.
- IIIF images are loaded live from their holding institutions and stay under those institutions' terms.
