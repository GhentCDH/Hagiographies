#!/usr/bin/env python3
"""Compose the Hagiographies browser into one self-contained HTML file.

    uv run --no-project python front/tools/compose.py --db data/hagiographies_full_export.sqlite [--release]

Writes front/dist/: hagiographies.html, hagiographies.sqlite (the public copy
of --db: restricted and placeholder links removed with PUBLIC_FILTER_SQL from
app/prepare.js, then VACUUMed), SHA256SUMS and README.txt. The HTML embeds
that same public copy. Python 3 standard library only; nothing is
bundled or transpiled, files are only inlined and their import specifiers
rewritten.

How the single file works
-------------------------
* Module graph. Starting at front/app/main.js, every static ``import``/``export
  ... from``, side-effect ``import "x"`` and literal dynamic ``import("x")`` is
  resolved (relative paths to files, bare specifiers through index.html's import
  map) and rewritten to a canonical key ``front:/<path below front/>``. Files
  with identical bytes (the two vendored MapLibre/PMTiles copies) share one
  module. ``import.meta.url`` becomes the string literal of a virtual URL
  ``https://front.invalid/<path>`` (blob: URLs cannot be a base for relative
  URLs). Pihka's paths.js gets an expression instead, see PATHS_META below.
* The modules travel as one gzip'd JSON blob (base64) in the HTML. A classic
  bootstrap script inflates it (DecompressionStream), makes a Blob URL per
  module, injects an import map key -> blob URL and then imports
  ``front:/app/main.js``.
* Virtual file system. Non-module assets the app fetches or links at runtime
  (extension CSS, the PMTiles basemap, glyphs, marker, TIFY translations,
  app/assets) are inlined (deduplicated by sha256) and keyed by their virtual
  URL. The bootstrap wraps ``fetch`` (with HTTP Range support for PMTiles) and
  the src/href setters, setAttribute and innerHTML, so a front.invalid URL
  is answered from memory or swapped for a Blob URL before the browser sees it.
* CSS ``url(...)`` references (Panno fonts) become data: URIs; index.html's
  stylesheets are inlined as <style>.
* MapLibre's worker: its main module would derive the worker URL from
  import.meta.url; the bootstrap traps the ``globalThis.maplibregl`` assignment
  made by Pihka's maplibre-shim.js and calls ``setWorkerUrl`` with the Blob URL
  of the inlined maplibre-gl-worker.mjs. Tiles (pmtiles:// protocol) and glyphs
  are requested on the main thread, so the fetch wrapper covers them.
* sqlite3.wasm and the database are base64 in <script id="hagio-wasm"> and
  <script id="hagio-db">, read by app/sqlite-init.js and
  app/datasource-embedded.js.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import json
import mimetypes
import re
import shutil
import sqlite3
import subprocess
import tempfile
import sys
from pathlib import Path

FRONT = Path(__file__).resolve().parent.parent
REPO = FRONT.parent
PIHKA = FRONT / "vendor" / "pihka" / "pihka"
DIST = FRONT / "dist"
ENTRY = FRONT / "app" / "main.js"
VBASE = "https://front.invalid/"
KEY_PREFIX = "front:/"

SQLITE_REAL = PIHKA / "core/vendor/@sqlite.org/sqlite-wasm/dist/index.mjs"
SQLITE_WASM = SQLITE_REAL.parent / "sqlite3.wasm"
SQLITE_INIT = FRONT / "app" / "sqlite-init.js"
MAPLIBRE_WORKER = PIHKA / "extensions/point_map/vendor/maplibre-gl/dist/maplibre-gl-worker.mjs"
PATHS_JS = PIHKA / "core/ui/runtime/paths.js"
# Virtual paths served by the bootstrap's fetch wrapper. The worker gets a .cjs
# name on purpose: MapLibre then loads it as a classic worker by fetching its
# text and wrapping it in a Blob, which Chrome allows on a file:// page (a
# module worker from a blob: URL is refused there).
WORKER_VPATH = "/vendor/pihka/pihka/extensions/point_map/vendor/maplibre-gl/dist/maplibre-gl-worker.cjs"
# main.js's database URL; Pihka's export view links it for download.
DB_VPATH = "/app/database/hagiographies.sqlite"

# Pihka derives basePath from paths.js's location and, on load, rewrites any
# non-route path to `${basePath}/#route` (redirectLegacyPathUrl). For the
# single file, basePath must equal the page's own path, so import.meta.url in
# paths.js becomes "<page URL>/core/ui/runtime/paths.js": three levels up is
# the page itself.
PATHS_META = '(location.href.split("#")[0].split("?")[0] + "/core/ui/runtime/paths.js")'

# Non-module assets fetched or linked at runtime, relative to front/.
ASSET_GLOBS = [
    "vendor/pihka/pihka/extensions/iiif-viewer/css/*.css",
    "vendor/pihka/pihka/extensions/iiif-viewer/vendor/tify/dist/tify.css",
    "vendor/pihka/pihka/extensions/iiif-viewer/vendor/tify/dist/translations/*.json",
    "vendor/pihka/pihka/extensions/point_map/css/*.css",
    "vendor/pihka/pihka/extensions/point_map/assets/**/*",
    "vendor/pihka/pihka/extensions/point_map/vendor/maplibre-gl/dist/maplibre-gl.css",
    "vendor/pihka/pihka/extensions/geo-filter/css/*.css",
    "vendor/pihka/pihka/extensions/geo-filter/assets/**/*",
    "vendor/pihka/pihka/extensions/geo-filter/vendor/maplibre-gl/dist/maplibre-gl.css",
    "app/assets/**/*",
]
ASSET_SKIP_DIRS = {"fonts"}  # fonts only reach the page through CSS data: URIs
ASSET_SKIP_NAMES = {"README.md", ".DS_Store"}

CONTENT_TYPES = {
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".pbf": "application/x-protobuf",
    ".pmtiles": "application/vnd.pmtiles",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
}

# import x from "y" / import {a} from "y" / import "y" / export * from "y" / export {a} from "y"
STATIC_RE = re.compile(r"""(?<![\w$.])(import|export)(\s*(?:[^;'"`()]*?\bfrom\s*)?)(["'])([^"'`\n\\]+)\3""")
# import("y") with a literal argument
DYNAMIC_RE = re.compile(r"""(?<![\w$.])import(\s*\(\s*)(["'])([^"'`\n\\]+)\2(\s*\))""")
META_URL_RE = re.compile(r"(?<![\w$.])import\.meta\.url(?![\w$])")
META_RE = re.compile(r"(?<![\w$.])import\.meta(?![\w$.])")
CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+?)\1\s*\)""")


PREPARE_JS = FRONT / "app" / "prepare.js"
RESTRICTED = b"files.m-patch.ugent.be"


def public_db(db_path: Path) -> bytes:
    """Return the published copy of the export: PUBLIC_FILTER_SQL (the same
    statements the page runs in memory) applied to a temporary copy, then
    VACUUM so the deleted rows leave no trace in free pages. The source file
    is never touched."""
    match = re.search(r"export const PUBLIC_FILTER_SQL = String\.raw`(.*?)`;", PREPARE_JS.read_text(encoding="utf-8"), re.S)
    if not match:
        die(f"PUBLIC_FILTER_SQL not found in {rel(PREPARE_JS)}")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "public.sqlite"
        shutil.copyfile(db_path, copy)
        con = sqlite3.connect(copy)
        try:
            con.executescript(match.group(1))
            con.commit()
            con.execute("VACUUM")
        finally:
            con.close()
        data = copy.read_bytes()
    if RESTRICTED in data:
        die(f"{RESTRICTED.decode()} is still in the public database copy")
    return data


def die(message: str) -> None:
    print(f"compose: error: {message}", file=sys.stderr)
    sys.exit(1)


def rel(path: Path) -> str:
    return path.resolve().relative_to(FRONT).as_posix()


def key_of(path: Path) -> str:
    return KEY_PREFIX + rel(path)


def vurl_of(path: Path) -> str:
    from urllib.parse import quote

    return VBASE + quote(rel(path), safe="/@-._~")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def gz(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def json_for_html(value) -> str:
    """JSON that is safe inside a <script> element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def git(*args: str, cwd: Path = REPO) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


# --------------------------------------------------------------------------
# Module graph
# --------------------------------------------------------------------------


def read_bare_map() -> dict[str, Path]:
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="importmap">(.*?)</script>', html, re.S)
    if not m:
        die("front/index.html has no import map")
    imports = json.loads(m.group(1))["imports"]
    bare = {name: (FRONT / target).resolve() for name, target in imports.items()}
    # The composed file routes sqlite-wasm through app/sqlite-init.js (inline wasm).
    bare["@sqlite.org/sqlite-wasm"] = SQLITE_INIT.resolve()
    bare["sqlite-wasm-real"] = SQLITE_REAL.resolve()
    return bare


class Graph:
    def __init__(self, bare: dict[str, Path]):
        self.bare = bare
        self.modules: dict[str, str] = {}  # canonical key -> rewritten source
        self.alias: dict[str, str] = {}  # every key -> canonical key
        self.by_sha: dict[str, str] = {}
        self.raw_bytes = 0
        self.warnings: list[str] = []

    def resolve(self, spec: str, importer: Path) -> Path | None:
        if spec.startswith(("./", "../", "/")):
            target = (FRONT / spec[1:]) if spec.startswith("/") else (importer.parent / spec)
            target = target.resolve()
            return target if target.is_file() else None
        if spec in self.bare:
            return self.bare[spec]
        return None

    def add(self, path: Path) -> str:
        path = path.resolve()
        key = key_of(path)
        if key in self.alias:
            return self.alias[key]
        data = path.read_bytes()
        digest = sha256(data)
        if digest in self.by_sha:  # identical vendored copy: share one module instance
            self.alias[key] = self.by_sha[digest]
            return self.alias[key]
        self.alias[key] = key
        self.by_sha[digest] = key
        self.raw_bytes += len(data)
        self.modules[key] = ""  # placeholder, guards against cycles
        self.modules[key] = self.rewrite(path, data.decode("utf-8"))
        return key

    def target_key(self, spec: str, importer: Path) -> str | None:
        target = self.resolve(spec, importer)
        if target is None:
            # The regexes also see "import"/"export" inside strings of minified
            # code; only report specifiers that look like module specifiers.
            if re.fullmatch(r"(\.{0,2}/)?@?[\w-][\w.@/-]*", spec) and not spec.startswith(("http", "data:", "blob:")):
                self.warnings.append(f"{rel(importer)}: unresolved import specifier {spec!r} left as is")
            return None
        return self.add(target)

    def rewrite(self, path: Path, source: str) -> str:
        def static(m: re.Match) -> str:
            key = self.target_key(m.group(4), path)
            if key is None:
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}{m.group(3)}{key}{m.group(3)}"

        def dynamic(m: re.Match) -> str:
            key = self.target_key(m.group(3), path)
            if key is None:
                return m.group(0)
            return f"import{m.group(1)}{m.group(2)}{key}{m.group(2)}{m.group(4)}"

        source = re.sub(r"\n//# sourceMappingURL=\S*\s*$", "\n", source)
        source = STATIC_RE.sub(static, source)
        source = DYNAMIC_RE.sub(dynamic, source)
        literal = PATHS_META if path == PATHS_JS.resolve() else json.dumps(vurl_of(path))
        source = META_URL_RE.sub(lambda _m: literal, source)
        source = META_RE.sub(lambda _m: "({url:" + literal + "})", source)
        return source


def classic_worker(path: Path) -> str:
    """MapLibre's worker as a classic script.

    Chrome refuses module workers from blob: URLs on a file:// page, but runs
    classic ones. The worker bundle is self-contained and
    starts itself; its only module syntax is the trailing default export.
    """
    source = path.read_text(encoding="utf-8")
    source = re.sub(r"\n//# sourceMappingURL=\S*\s*$", "\n", source)
    source, n = re.subn(r";export\{\w+ as default\};\s*$", ";\n", source)
    if n != 1 or re.search(r"(?<![\w$.])(import|export)\s*[{*\"']", source):
        die(f"{rel(path)}: unexpected module syntax, cannot load it as a classic worker")
    return source


def check_syntax(modules: dict[str, str], scratch: Path) -> None:
    """Parse every rewritten module with node --check, when node is available."""
    node = shutil.which("node")
    if not node:
        print("compose: node not found, skipping the syntax check")
        return
    scratch.mkdir(parents=True, exist_ok=True)
    failures = []
    for i, (key, source) in enumerate(modules.items()):
        f = scratch / f"m{i}.mjs"
        f.write_text(source, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if r.returncode != 0:
            failures.append(f"{key}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'syntax error'}")
        f.unlink()
    if failures:
        die("rewritten modules do not parse:\n  " + "\n  ".join(failures))


# --------------------------------------------------------------------------
# CSS and assets
# --------------------------------------------------------------------------


class Stats:
    def __init__(self):
        self.fonts = 0
        self.css_images = 0


def inline_css(path: Path, stats: Stats) -> str:
    css = path.read_text(encoding="utf-8")
    if re.search(r"@import\s", css):
        die(f"{rel(path)}: @import is not supported by compose")

    def repl(m: re.Match) -> str:
        ref = m.group(2).strip()
        if ref.startswith(("data:", "#", "http:", "https:", "blob:")):
            return m.group(0)
        target = (path.parent / ref.split("?")[0].split("#")[0]).resolve()
        if not target.is_file():
            die(f"{rel(path)}: url({ref}) not found")
        data = target.read_bytes()
        uri = f"data:{content_type(target)};base64,{b64(data)}"
        if target.suffix.lower() in {".woff", ".woff2", ".ttf", ".otf"}:
            stats.fonts += len(uri)
        else:
            stats.css_images += len(uri)
        return f'url("{uri}")'

    return CSS_URL_RE.sub(repl, css)


def collect_assets(stats: Stats):
    """Return (vfs, blocks): vfs maps virtual path -> {id, type}; blocks id -> (enc, bytes, category)."""
    vfs: dict[str, dict] = {}
    blocks: dict[str, tuple[str, bytes, str]] = {}
    seen: set[Path] = set()
    for pattern in ASSET_GLOBS:
        for path in sorted(FRONT.glob(pattern)):
            if not path.is_file() or path in seen or path.name in ASSET_SKIP_NAMES:
                continue
            if ASSET_SKIP_DIRS & set(path.relative_to(FRONT).parts):
                continue
            seen.add(path)
            if path.suffix.lower() == ".css":
                data = inline_css(path, stats).encode("utf-8")
            else:
                data = path.read_bytes()
            digest = sha256(data)[:16]
            if digest not in blocks:
                packed = gz(data)
                category = "pmtiles" if path.suffix == ".pmtiles" else "other"
                if len(packed) < 0.9 * len(data):
                    blocks[digest] = ("gzip", packed, category)
                else:
                    blocks[digest] = ("raw", data, category)
            vfs["/" + rel(path)] = {"id": digest, "type": content_type(path)}
    return vfs, blocks


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

BOOTSTRAP_JS = r"""
(function () {
    "use strict";
    var VBASE = "https://front.invalid/";
    var manifest = JSON.parse(document.getElementById("hagio-manifest").textContent);

    function fail(error) {
        console.error("[hagiographies] bootstrap failed:", error);
        var app = document.getElementById("app");
        if (app) app.textContent = "This page could not start: " + (error && error.message || error) +
            ". It needs a current browser (Chrome, Edge, Firefox or Safari 16.4 or later).";
    }

    function fromBase64(text) {
        var clean = text.trim();
        if (typeof Uint8Array.fromBase64 === "function") return Uint8Array.fromBase64(clean);
        var binary = atob(clean);
        var bytes = new Uint8Array(binary.length);
        for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        return bytes;
    }

    function payload(element) {
        var bytes = fromBase64(element.textContent);
        if (element.dataset.enc !== "gzip") return Promise.resolve(bytes);
        var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
        return new Response(stream).arrayBuffer().then(function (buffer) { return new Uint8Array(buffer); });
    }

    // ---- virtual file system ------------------------------------------------
    var files = {}; // "/path" -> {blob, url, type}

    function lookup(url) {
        if (typeof url !== "string" || url.lastIndexOf(VBASE, 0) !== 0) return null;
        var path;
        try { path = decodeURIComponent(new URL(url).pathname); } catch (e) { return null; }
        var file = files[path];
        if (!file) console.warn("[hagiographies] not in the inlined file system:", url);
        return file || null;
    }

    function mapUrl(value) {
        var file = lookup(String(value));
        return file ? file.url : value;
    }

    function mapHtml(html) {
        return String(html).replace(/https:\/\/front\.invalid\/[^"'\s)<>]*/g, mapUrl);
    }

    function installShims() {
        var originalFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            var url = typeof input === "string" ? input : input instanceof URL ? input.href : input && input.url;
            var file = lookup(url);
            if (!file) return originalFetch(input, init);
            if (init && init.signal && init.signal.aborted) {
                return Promise.reject(new DOMException("The operation was aborted.", "AbortError"));
            }
            var headers = new Headers(init && init.headers || (input instanceof Request ? input.headers : undefined));
            var size = file.blob.size;
            var range = headers.get("range");
            if (range) {
                var m = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
                var start, end;
                if (m && m[1] !== "") {
                    start = +m[1];
                    end = m[2] !== "" ? Math.min(+m[2], size - 1) : size - 1;
                } else if (m && m[2] !== "") {
                    start = Math.max(0, size - +m[2]);
                    end = size - 1;
                }
                if (start === undefined || start >= size || end < start) {
                    return Promise.resolve(new Response(null, {
                        status: 416, statusText: "Range Not Satisfiable",
                        headers: { "Content-Range": "bytes */" + size },
                    }));
                }
                return Promise.resolve(new Response(file.blob.slice(start, end + 1, file.type), {
                    status: 206, statusText: "Partial Content",
                    headers: {
                        "Content-Type": file.type,
                        "Content-Length": String(end - start + 1),
                        "Content-Range": "bytes " + start + "-" + end + "/" + size,
                        "Accept-Ranges": "bytes",
                    },
                }));
            }
            return Promise.resolve(new Response(file.blob, {
                status: 200, statusText: "OK",
                headers: { "Content-Type": file.type, "Content-Length": String(size), "Accept-Ranges": "bytes" },
            }));
        };

        function wrapSetter(proto, prop, map) {
            var d = Object.getOwnPropertyDescriptor(proto, prop);
            if (!d || !d.set) return;
            Object.defineProperty(proto, prop, {
                configurable: true, enumerable: d.enumerable, get: d.get,
                set: function (value) { d.set.call(this, map.call(this, value)); },
            });
        }
        wrapSetter(HTMLImageElement.prototype, "src", mapUrl);
        wrapSetter(HTMLLinkElement.prototype, "href", mapUrl);
        wrapSetter(HTMLAnchorElement.prototype, "href", function (value) {
            var mapped = mapUrl(value);
            if (mapped !== value) this.dataset.hagioName = String(value).split(/[?#]/)[0].split("/").pop();
            return mapped;
        });
        wrapSetter(HTMLSourceElement.prototype, "src", mapUrl);
        wrapSetter(Element.prototype, "innerHTML", mapHtml);
        var setAttribute = Element.prototype.setAttribute;
        Element.prototype.setAttribute = function (name, value) {
            if (/^(src|href|xlink:href|srcset)$/i.test(name)) {
                var mapped = mapHtml(value);
                if (mapped !== String(value) && this instanceof HTMLAnchorElement) {
                    this.dataset.hagioName = String(value).split(/[?#]/)[0].split("/").pop();
                }
                value = mapped;
            }
            return setAttribute.call(this, name, value);
        };
        // A download link to an inlined file keeps the file's own name, not the Blob URL's id.
        document.addEventListener("click", function (event) {
            var a = event.target && event.target.closest && event.target.closest("a[data-hagio-name]");
            if (a && a.hasAttribute("download") && !a.getAttribute("download")) a.setAttribute("download", a.dataset.hagioName);
        }, true);
        var setAttributeNS = Element.prototype.setAttributeNS;
        Element.prototype.setAttributeNS = function (ns, name, value) {
            if (/(^|:)href$/i.test(name)) value = mapUrl(value);
            return setAttributeNS.call(this, ns, name, value);
        };
        var insertAdjacentHTML = Element.prototype.insertAdjacentHTML;
        Element.prototype.insertAdjacentHTML = function (position, html) {
            return insertAdjacentHTML.call(this, position, mapHtml(html));
        };
    }

    // MapLibre would derive its worker URL from import.meta.url. Hand it the
    // inlined worker instead, the moment Pihka's maplibre-shim publishes it.
    // The worker URL is a virtual .cjs URL (see compose.py, WORKER_VPATH).
    function trapMaplibre(workerUrl) {
        var value;
        Object.defineProperty(globalThis, "maplibregl", {
            configurable: true,
            get: function () { return value; },
            set: function (module) {
                value = module;
                try { if (module && module.setWorkerUrl) module.setWorkerUrl(workerUrl); }
                catch (e) { console.warn("[hagiographies] setWorkerUrl failed:", e); }
            },
        });
    }

    function start() {
        if (typeof DecompressionStream !== "function") throw new Error("DecompressionStream is not supported");
        var assetBlocks = {};
        document.querySelectorAll("script[data-asset]").forEach(function (el) { assetBlocks[el.dataset.asset] = el; });
        var ids = Object.keys(assetBlocks);
        return Promise.all([
            payload(document.getElementById("hagio-modules")),
            Promise.all(ids.map(function (id) { return payload(assetBlocks[id]); })),
        ]).then(function (results) {
            var sources = JSON.parse(new TextDecoder().decode(results[0]));
            var bytesById = {};
            ids.forEach(function (id, i) { bytesById[id] = results[1][i]; });
            var blobById = {};
            Object.keys(manifest.files).forEach(function (path) {
                var entry = manifest.files[path];
                var key = entry.id + "|" + entry.type;
                if (!blobById[key]) {
                    var blob = new Blob([bytesById[entry.id]], { type: entry.type });
                    blobById[key] = { blob: blob, url: URL.createObjectURL(blob), type: entry.type };
                }
                files[path] = blobById[key];
            });

            var dbElement = document.getElementById("hagio-db");
            var dbBlob = new Blob([fromBase64(dbElement.textContent)], { type: "application/vnd.sqlite3" });
            files[manifest.database] = { blob: dbBlob, url: URL.createObjectURL(dbBlob), type: dbBlob.type };

            var moduleUrls = {};
            Object.keys(sources).forEach(function (key) {
                moduleUrls[key] = URL.createObjectURL(new Blob([sources[key]], { type: "text/javascript" }));
            });
            var imports = {};
            Object.keys(manifest.modules).forEach(function (key) { imports[key] = moduleUrls[manifest.modules[key]]; });
            Object.keys(manifest.bare).forEach(function (name) { imports[name] = moduleUrls[manifest.modules[manifest.bare[name]]]; });

            installShims();
            trapMaplibre(manifest.worker);

            var map = document.createElement("script");
            map.type = "importmap";
            map.textContent = JSON.stringify({ imports: imports });
            document.head.appendChild(map);

            var main = document.createElement("script");
            main.type = "module";
            main.textContent = "import " + JSON.stringify(manifest.entry) + ";";
            document.body.appendChild(main);
        });
    }

    try { start().catch(fail); } catch (error) { fail(error); }
})();
"""

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' fill='%231E64C8'/%3E"
    "%3Crect x='9' y='6' width='14' height='20' fill='none' stroke='white' stroke-width='2.5'/%3E"
    "%3Cpath d='M12.5 12h7M12.5 16h7M12.5 20h4' stroke='white' stroke-width='2'/%3E%3C/svg%3E"
)


def build_html(template: str, styles: str, build_info: dict, manifest: dict, modules_gz: bytes,
               blocks: dict, wasm: bytes, db: bytes) -> str:
    html = template

    def remove(pattern: str, what: str, count: int = 0, repl: str = "") -> None:
        nonlocal html
        html, n = re.subn(pattern, repl, html, flags=re.S)
        if n == 0 or (count and n != count):
            die(f"front/index.html: expected {what}, found {n}")

    # Stylesheets: the first <link rel=stylesheet> becomes the inlined <style>, the rest go.
    first = [True]

    def style_repl(_m: re.Match) -> str:
        if first[0]:
            first[0] = False
            return "<style>\n" + styles + "\n</style>"
        return ""

    html, n = re.subn(r'[ \t]*<link rel="stylesheet" href="[^"]+"\s*/?>\n?', style_repl, html)
    if n == 0:
        die("front/index.html: expected <link rel=stylesheet>")
    remove(r'[ \t]*<script type="importmap">.*?</script>\n?', "an import map", 1)
    remove(r'[ \t]*<link rel="modulepreload"[^>]*>\n?', "a modulepreload link")
    remove(r'[ \t]*<link rel="preload"[^>]*>\n?', "a database preload link")
    remove(r'[ \t]*<script type="module" src="[^"]+"></script>\n?', "the module entry script", 1)
    if 'rel="icon"' not in html:
        html = html.replace("</title>", f'</title>\n        <link rel="icon" href="{FAVICON}" />', 1)

    head = f"        <script>window.__HAGIO_BUILD__ = {json_for_html(build_info)};</script>\n    </head>"
    html = html.replace("</head>", head, 1)

    parts = [f'<script type="application/json" id="hagio-manifest">{json_for_html(manifest)}</script>',
             f'<script type="application/octet-stream" id="hagio-modules" data-enc="gzip">{b64(modules_gz)}</script>']
    for block_id, (enc, data, _cat) in blocks.items():
        parts.append(f'<script type="application/octet-stream" data-asset="{block_id}" data-enc="{enc}">{b64(data)}</script>')
    parts.append(f'<script type="application/octet-stream" id="hagio-wasm">{b64(wasm)}</script>')
    parts.append(f'<script type="application/octet-stream" id="hagio-db">{b64(db)}</script>')
    parts.append("<script>" + BOOTSTRAP_JS + "</script>")
    html = html.replace("</body>", "\n".join(parts) + "\n</body>", 1)
    return html


# --------------------------------------------------------------------------
# Metadata, README
# --------------------------------------------------------------------------


def dataset_meta() -> dict:
    text = (FRONT / "app" / "dataset.js").read_text(encoding="utf-8")

    def field(name: str) -> str:
        m = re.search(rf'^\s*{name}:\s*"([^"]*)"', text, re.M)
        return m.group(1) if m else ""

    return {"version": field("version"), "doi": field("doi"), "repository": field("repository"),
            "shortTitle": field("shortTitle") or "Hagiographies"}


def readme(meta: dict, build: dict, html_sha: str) -> str:
    doi = meta["doi"] if meta["doi"] and meta["doi"] != "TBD" else "to be assigned"
    return f"""Hagiographies: medieval Latin hagiographic texts, manuscripts and editions
(M-PATCH prototype corpus), Ghent University
==========================================================================

Version:       {meta['version']}
DOI:           {doi}
Export date:   {build['exportDate']} (date of the SQLite export)
Built:         {build['builtAt']} (code {build['gitCommit']}, Pihka {build['pihkaCommit']})

FILES

  hagiographies.sqlite   The dataset: a SQLite 3 database exported from the
                         project's PostgreSQL database. Links to the project's
                         restricted working files and placeholder links are
                         left out of this public copy. Open it with any SQLite
                         tool, e.g. the sqlite3 command line shell or DB Browser
                         for SQLite (https://sqlitebrowser.org/).
                         sha256 {build['sha256']}

  hagiographies.html     A browser for the same data, in one self-contained
                         file. Double-click it to open it in a current web
                         browser (Chrome, Edge, Firefox, Safari 16.4+). It needs
                         no installation and no server. It embeds an identical
                         copy of hagiographies.sqlite (the front page shows its
                         sha256) and opens it in memory; the deposited database
                         file is never changed.
                         sha256 {html_sha}

  SHA256SUMS             Checksums of both files (check with: sha256sum -c SHA256SUMS).

NETWORK USE

  The browser works offline, with one exception: digitised manuscript images
  are shown with IIIF. Their manifests and images are loaded live from the
  institutions that hold them, and remain under those holders' rights and
  terms of use. Without a network connection those viewers stay empty.

LICENCES

  Data (hagiographies.sqlite and the data shown in the browser): Creative
  Commons Attribution 4.0 International (CC BY 4.0),
  https://creativecommons.org/licenses/by/4.0/

  Code of the browser: MIT licence, https://opensource.org/license/mit
  It is built on Pihka (GhentCDH, https://github.com/GhentCDH/pihka, MIT) and
  includes third-party software under its own licences, including Preact (MIT),
  SQLite (public domain), MapLibre GL JS (BSD-3-Clause), PMTiles (BSD-3-Clause)
  and fflate (MIT). The basemap uses OpenStreetMap data (ODbL) via Protomaps.

  TIFY IIIF viewer v0.36.2 is licensed under the GNU Affero General Public
  License v3.0 (AGPL-3.0). Its source code is available at
  https://github.com/tify-iiif-viewer/tify (tag v0.36.2).

  Excluded from these licences: the UGent Panno fonts and the Ghent University
  and GhentCDH logos. They are trademarks and property of Ghent University and
  may not be reused outside this work.

CREDITS

  See the Credits page in hagiographies.html for the M-PATCH project team,
  Ghent Centre for Digital Humanities (GhentCDH) and the funding (FWO
  I004326N), and for the full third-party notices.
"""


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def human(n: int) -> str:
    return f"{n / 1024 / 1024:6.2f} MB" if n >= 1024 * 1024 else f"{n / 1024:6.1f} kB"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, type=Path, help="the SQLite export to embed and deposit")
    parser.add_argument("--release", action="store_true",
                        help="refuse TBD/preview metadata and a dirty git tree")
    parser.add_argument("--out", type=Path, default=DIST, help="output directory (default front/dist)")
    parser.add_argument("--no-check", action="store_true", help="skip the node --check syntax pass")
    args = parser.parse_args()

    db_path = args.db if args.db.is_absolute() else (Path.cwd() / args.db)
    if not db_path.is_file():
        die(f"{args.db} not found")
    if not (PIHKA / "core").is_dir():
        die("front/vendor/pihka is empty; run: git submodule update --init front/vendor/pihka")

    meta = dataset_meta()
    head = git("rev-parse", "--short", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    pihka_commit = git("rev-parse", "--short", "HEAD", cwd=PIHKA)
    if args.release:
        problems = []
        if meta["doi"] in ("", "TBD"):
            problems.append('dataset.js doi is "TBD"')
        if "preview" in meta["version"]:
            problems.append(f'dataset.js version "{meta["version"]}" is a preview')
        if dirty:
            problems.append("the git tree is dirty (commit first)")
        if problems:
            die("--release refused: " + "; ".join(problems))

    if db_path.read_bytes()[:16] != b"SQLite format 3\x00":
        die(f"{args.db} is not a SQLite 3 database")
    db = public_db(db_path)
    db_sha = sha256(db)
    build = {
        "exportDate": dt.datetime.fromtimestamp(db_path.stat().st_mtime, dt.timezone.utc).date().isoformat(),
        "builtAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sha256": db_sha,
        "bytes": len(db),
        "gitCommit": (head or "unknown") + ("-dirty" if dirty else ""),
        "pihkaCommit": pihka_commit or "unknown",
    }

    # Modules
    graph = Graph(read_bare_map())
    entry_key = graph.add(ENTRY)
    for w in graph.warnings:
        print(f"compose: warning: {w}")
    if not args.no_check:
        check_syntax(graph.modules, args.out / ".check")
        shutil.rmtree(args.out / ".check", ignore_errors=True)
    bare = {name: graph.alias[key_of(path)] for name, path in graph.bare.items() if key_of(path) in graph.alias}
    modules_json = json.dumps(graph.modules, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    modules_gz = gz(modules_json)

    # Assets and CSS
    stats = Stats()
    vfs, blocks = collect_assets(stats)
    worker_source = classic_worker(MAPLIBRE_WORKER).encode("utf-8")
    worker_id = sha256(worker_source)[:16]
    blocks[worker_id] = ("gzip", gz(worker_source), "worker")
    vfs[WORKER_VPATH] = {"id": worker_id, "type": "text/javascript"}
    template = (FRONT / "index.html").read_text(encoding="utf-8")
    css_links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', template)
    styles = "\n".join(f"/* {href} */\n" + inline_css((FRONT / href).resolve(), stats) for href in css_links)
    styles = styles.replace("</style", "<\\/style")

    manifest = {"entry": entry_key, "worker": VBASE + WORKER_VPATH[1:], "database": DB_VPATH,
                "modules": graph.alias, "bare": bare, "files": vfs}
    wasm = SQLITE_WASM.read_bytes()
    html = build_html(template, styles, build, manifest, modules_gz, blocks, wasm, db)

    # Outputs
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    html_bytes = html.encode("utf-8")
    (out / "hagiographies.html").write_bytes(html_bytes)
    (out / "hagiographies.sqlite").write_bytes(db)
    html_sha = sha256(html_bytes)
    (out / "SHA256SUMS").write_text(f"{html_sha}  hagiographies.html\n{db_sha}  hagiographies.sqlite\n", encoding="ascii")
    (out / "README.txt").write_text(readme(meta, build, html_sha), encoding="utf-8")

    # Sanity: the restricted share host must only exist inside base64/gzip payloads.
    if "files.m-patch.ugent.be" in html:
        die("files.m-patch.ugent.be appears in plain text in the composed HTML")

    # Size report (bytes as they sit in the HTML)
    def b64len(n: int) -> int:
        return (n + 2) // 3 * 4

    pm = sum(b64len(len(d)) for e, d, c in blocks.values() if c == "pmtiles")
    other = sum(b64len(len(d)) for e, d, c in blocks.values() if c == "other")
    worker = sum(b64len(len(d)) for e, d, c in blocks.values() if c == "worker")
    rows = [
        (f"modules ({len(graph.modules)} files, {human(graph.raw_bytes).strip()} raw, gzip)", b64len(len(modules_gz))),
        ("MapLibre worker (gzip)", worker),
        ("sqlite3.wasm", b64len(len(wasm))),
        ("database", b64len(len(db))),
        ("pmtiles basemap (deduplicated)", pm),
        ("fonts (CSS data: URIs)", stats.fonts),
        ("other assets (CSS, glyphs, svg, json)", other + stats.css_images),
    ]
    rows.append(("rest (HTML, inline CSS, bootstrap, manifest)", len(html_bytes) - sum(n for _, n in rows)))
    print(f"compose: wrote {rel(out / 'hagiographies.html')} ({human(len(html_bytes)).strip()})")
    for label, n in rows:
        print(f"  {human(n)}  {label}")
    print(f"  export date {build['exportDate']}, db sha256 {db_sha[:16]}…, code {build['gitCommit']}, pihka {build['pihkaCommit']}")


if __name__ == "__main__":
    main()
