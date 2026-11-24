# Tasks: `front/`, a static browser for the Hagiographies SQLite export

**Goal:** a no-build browser for `data/hagiographies_full_export.sqlite`, made from Pihka core and extensions in UGent house style. It offers faceted perspectives (texts, codices, manuscripts, editions, places), embedded IIIF viewers and maps. It is composed into one `hagiographies.html` that ships next to the `.sqlite` on a research data repository, as its human-readable metadata.

Full plan: `~/.claude/plans/have-a-look-at-async-island.md`.

**Done means:**
- `just front_serve` serves the decomposed version (`front/index.html`). Every perspective loads, facets and search work, a codex with an IIIF manifest shows TIFY images, and the map renders. There are no console errors.
- `just front_compose` writes `front/dist/hagiographies.html` + `hagiographies.sqlite` + `SHA256SUMS` + `README.txt`.
- The HTML works from `file://`, and its only network requests go to IIIF hosts.
- No `files.m-patch.ugent.be` link or `Placeholder *` link is visible anywhere in the UI.
- The only fonts are UGent Panno (display) and Arial (text). Light and dark mode both work. The layout works at 360 px. The Lighthouse accessibility score is at least 95.
- The front page has M-PATCH info, an about-the-data page and Credits (M-PATCH team, GhentCDH, FWO I004326N, third-party notices). Data is CC BY 4.0 and code is MIT; Panno and the logos are excluded.
- Pihka submodule files are unmodified (`git -C front/vendor/pihka status` is clean).
- CLAUDE.md, `front/README.md` and the justfile are updated.

**Stop and ask only when:**
- I can't continue without the user's input;
- a failure can't be explained;
- before anything destructive: `db_clone_qas` (overwrites the local DB), force-push, changes outside this repo (including Pihka upstream);
- before a release build (DOI, credits names).

**Out of scope / constraints:**
- No build step, bundler or transpiler for the decomposed version. `compose.py` only inlines and rewrites.
- Never edit `front/vendor/pihka`. Customise only through `register(api)` plugins and our own composition root. Record any Pihka gaps under Discovered.
- No fonts other than UGent Panno and Arial. No Pico amber accent, no rounded corners, no centred titles, no pill buttons, no gradients.
- English only (v1).
- `public` schema, migrations and `model.py` are not touched.

---

## Plan

### 0. Setup
- [x] Branch `feat/front`, submodule `front/vendor/pihka` at d1cc57f. Verify: `git -C front/vendor/pihka log -1`.
- [ ] Blocked on user: refresh the export (`db_clone_qas` → `pg_export_sqlite`). The local export still has the pre-065 Mirador-wrapped manifest URLs; the SQL handles both forms meanwhile.

### 1. Data and config (subagent A)
- [x] `front/app/prepare.js` (was prepare.sql): in-memory preparation run after the DB opens:
  - delete restricted links (`files.m-patch.ugent.be`) and `Placeholder *` links;
  - add derived columns (`codex_iiif_manifest`, has-IIIF flag, counts).

  Evidence: before/after counts per link type.
- [x] `front/tools/gen_config.py` → `front/app/config.generated.json` from Mathesar `record_summaries.json` + `column_display.json`. `front/app/config.js` holds the perspectives, facets, column types and hidden lookup tables. Evidence: every facet query, run with sqlite3.

### 2. Theme, shell and pages (subagent B, parallel with 1)
- [x] `front/app/theme/ugent.css`: port the IPEMArchive tokens, Panno `@font-face` and dark mode, and map them onto Pico variables. Copy fonts and logos into `front/app/assets/`.
- [x] `front/app/shell.js`: Pihka plugin overriding `control/header`, `control/footer`, `page/home`, `page/static`.
- [x] `front/app/pages/{about-data,credits}.js`, the home content, and `front/app/dataset.json`.

### 3. Composition root (me, after 1 and 2)
- [x] `front/index.html`, `front/app/main.js`, `front/app/datasource-embedded.js`, `front/app/sqlite-init.js`. Wire in `iiif-viewer`, `point_map` and `geo-filter`. Verify: `just front_serve`, chrome-devtools, no console errors.

### 4. Single file (subagent C, after 3)
- [x] `front/tools/compose.py`:
  - module graph → Blob importmap;
  - rewrite `import.meta.url`;
  - virtual FS plus fetch, stylesheet and worker shims;
  - inline the wasm, DB, fonts and PMTiles (deduplicated).

  Verify: `just front_compose`, open from `file://`.

### 5. Verification and docs
- [x] chrome-devtools pass over both builds (perspectives, facets, FTS, IIIF from Gallica and Adore, map, dark mode, 360 px, Lighthouse accessibility).
- [x] Assert there are no restricted links in the UI, and that the embedded DB sha256 matches `SHA256SUMS`.
- [x] justfile `front_*` recipes, `.gitignore`, `front/README.md`, CLAUDE.md.
- [ ] `/code-review` of the branch, fix merge-blocking issues.

## Discovered
- Pihka gaps (upstream issues, not patched):
  - m2m facets are dropped when facets are configured (`core/ui/runtime/facets.js:42-51`).
  - Junctions with extra columns don't qualify as m2m (`data-store.js:367`), so there is no repertory facet.
  - Hidden tables are excluded from related records (`presentation.js:37`).
  - Perspectives are sorted by id (`perspectives.js:69`).
  - A `values` facet on a non-FK column is not URL-restored (`filter-codecs.js:41-46`).
  - NULL facet values can't be selected (`data-store.js:322`).
  - Geo columns must be named exactly `latitude`/`longitude` (`point_map/js/geo.js:8-9`). Handled by derived columns in `prepare.js`.
- Data issues for the researchers:
  - `text_dating_range_end` has a maximum of 9000 (typo?).
  - `codex_dating_range_start`/`_end` have a minimum of 0.
  - 15 codices have two different IIIF manifests; the lowest link id is used.

- Pihka gaps, continued:
  - Map circle/marker colours are hard-coded amber (`point_map/js/map-view.js:207`).
  - The detail breadcrumb shows the row id rather than its label (`core/ui/defaults/app.js:151-154`).
  - A list view has no way to hide columns that the detail view shows.
  - Sortable `th` elements are click-only, with no keyboard access (`data-view-list-table.js:22`).
- `http.server` has no Range support, so the PMTiles basemap was blank. Fixed with `front/tools/serve.py`, used by `just front_serve`.
- Theme fix: list and search tables no longer break words anywhere; cells are 9–40ch, and notes are capped at 12 words.

- Layout: Pihka's fill-height workspace (inner scrollbars for the table, sidebar, map and viewer) is overridden in `ugent.css` with a single page scroll. Map and viewer heights are clamp(…dvh).

- The published DB is filtered: `compose.py` applies `PUBLIC_FILTER_SQL` (from `app/prepare.js`) plus VACUUM to the copy it embeds and deposits. The restricted host appears nowhere in the bytes; embedded and deposited copies are identical.

## Blocked on user
- `db_clone_qas` + `pg_export_sqlite` to refresh the export (destructive on the local Docker DB).
- Confirm the credits names taken from internal notes (Lien Hellebaut, Sibren Wieme, Miel Peeters, PhD researchers) before a release build.

## Unconfirmed
- Single file tested in Chrome only; not in Firefox or Safari. It needs `DecompressionStream` (Safari 16.4+).
- The third-party licence lines in `README.txt` (compose) were written from memory. Check them against Pihka's THIRD-PARTY-NOTICES, especially the OSM/Protomaps attribution.

## Log
- Single file (11.7 MB) verified from file:// in an isolated Chrome context:
  - home, credits, places map with the inline PMTiles basemap, and the geo-filter;
  - IIIF from Adore and Gallica (origin null is accepted);
  - facet and search;
  - no console errors, no requests except to IIIF hosts;
  - `SHA256SUMS` OK, 0 `files.m-patch` strings, `--release` refuses (DOI TBD, preview, dirty).
- User changes:
  - logo: the GhentCDH landscape logo only, in the footer on the right; the header is flat;
  - the provenance paragraph is removed;
  - the GhentCDH role is "software development and digital consultancy".
- Decomposed version verified in Chrome. Home with counts; texts table and facets; FTS search across 5 tables; codex 336 (Adore) and 729 (Gallica) IIIF load through TIFY; the codex map clusters on the PMTiles basemap; dark mode at 360 px.
- 2026-11-24 plan approved; branch and submodule created.
