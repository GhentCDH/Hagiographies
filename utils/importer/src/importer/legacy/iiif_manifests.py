# iiif_manifests.py
# ---------------------------------------------------------------------------
# Check and repair the IIIF manifest links of Image records.
#
# Phase 1 (always): for every Image of type iiif / iiif_mf, fetch the stored
# URL and classify it:
#   manifest      — the URL returns JSON with minimal IIIF Manifest structure
#   collection    — valid IIIF JSON, but a Collection (not directly viewable)
#   not_manifest  — reachable, but HTML or non-IIIF JSON (viewer/landing page)
#   error         — network / HTTP failure
#
# Phase 2 (--fix): store validated manifest URLs in Image.iiif_manifest_url.
# For not_manifest pages the HTML is scraped for candidate manifest links
# (…/manifest.json, /manifest/ paths, manifest=/iiifContent= query params);
# each candidate is fetched and validated, the first real manifest wins.
# The original Image.url is never modified.
#
# A manifest URL renders in any IIIF viewer, e.g.:
#   https://tify.rocks/?manifest=<iiif_manifest_url>
#
# Usage (inside the utils container):
#   uv run check-iiif                # report only, writes /data/iiif_manifest_report.csv
#   uv run check-iiif --fix          # also discover + store manifest URLs
#   uv run check-iiif --fix --only-missing --limit 20
# ---------------------------------------------------------------------------

import argparse
import csv
import html
import json
import logging
import re
import time
from typing import Any, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from rich.logging import RichHandler
from sqlmodel import Session, select

from utilities.config import DATA_ROOT
from utilities.db import engine
from utilities.legacy_model import Codex, Image, ImageType

logging.basicConfig(
    level=logging.INFO, format="%(message)s",
    handlers=[RichHandler(show_time=True, show_path=False, markup=True)],
)
logger = logging.getLogger(__name__)

IIIF_IMAGE_TYPES = ("iiif", "iiif_mf")
REQUEST_TIMEOUT = 20.0
POLITE_DELAY_S = 0.5
REPORT_PATH = DATA_ROOT / "iiif_manifest_report.csv"

# Candidate manifest URLs inside page HTML: absolute URLs whose path or query
# mentions "manifest" (e.g. …/manifest.json, /manifest/iiif/v3/…, ?manifest=…).
_ABS_MANIFEST_RE = re.compile(
    r"https?://[^\s\"'<>\\)]+manifest[^\s\"'<>\\)]*", re.IGNORECASE
)
# href/src attributes with relative paths mentioning "manifest".
_REL_MANIFEST_RE = re.compile(
    r"""(?:href|src|data-manifest(?:-url)?|content)=["']([^"']*manifest[^"']*)["']""",
    re.IGNORECASE,
)


def _classify_iiif_json(data: Any) -> Optional[str]:
    """Return 'manifest' / 'collection' for IIIF Presentation JSON, else None."""
    if not isinstance(data, dict):
        return None
    context = data.get("@context", "")
    context_str = json.dumps(context) if not isinstance(context, str) else context
    if "iiif.io/api/presentation" not in context_str:
        return None
    kind = data.get("type") or data.get("@type") or ""
    if isinstance(kind, list):
        kind = " ".join(str(k) for k in kind)
    kind = str(kind)
    if "Manifest" in kind and ("items" in data or "sequences" in data):
        return "manifest"
    if "Collection" in kind:
        return "collection"
    return None


def _fetch(client: httpx.Client, url: str) -> httpx.Response:
    resp = client.get(url)
    resp.raise_for_status()
    return resp


# URL shapes that are manifest endpoints by convention — used when a server
# blocks robots (e.g. gallica.bnf.fr 403s all non-browser requests) so the
# JSON cannot be validated programmatically.
_MANIFEST_SHAPE_RE = re.compile(r"(/manifest\.json($|\?)|/manifest/)", re.IGNORECASE)


def check_url(client: httpx.Client, url: str) -> Tuple[str, Optional[str], str]:
    """Classify a stored image URL.

    Returns (status, page_html_or_None, note).  page HTML is returned for
    not_manifest responses so --fix can scrape it without a second request.
    """
    try:
        resp = _fetch(client, url)
    except httpx.HTTPStatusError as exc:
        if (exc.response.status_code in (401, 403)
                and _MANIFEST_SHAPE_RE.search(urlparse(url).path)):
            return ("assumed_manifest", None,
                    f"{exc.response.status_code} to robots, but URL has "
                    "manifest shape — accepted unverified")
        return "error", None, f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # network, TLS, …
        return "error", None, f"{type(exc).__name__}: {exc}"

    text = resp.text
    try:
        kind = _classify_iiif_json(json.loads(text))
    except (json.JSONDecodeError, UnicodeDecodeError):
        kind = None

    if kind == "manifest":
        return "manifest", None, f"validated at {resp.url}"
    if kind == "collection":
        return "collection", None, "IIIF Collection, not a Manifest"
    return "not_manifest", text, f"content-type {resp.headers.get('content-type', '?')}"


def extract_manifest_candidates(page_html: str, base_url: str) -> List[str]:
    """Collect candidate manifest URLs from a viewer/landing page, best first."""
    decoded = html.unescape(page_html)
    candidates: List[str] = []

    def _add(u: str) -> None:
        u = u.strip().rstrip("\\").rstrip("&?;,")
        if u.endswith(".webmanifest"):  # PWA manifest, not IIIF
            return
        if u.startswith("http") and u not in candidates:
            candidates.append(u)

    # 1. manifest=/iiifContent= query params anywhere (viewer permalinks) —
    #    the parameter value is the manifest itself, most reliable.
    for match in re.finditer(r"(?:manifest|iiifContent)=([^&\"'\s<>]+)",
                             decoded, re.IGNORECASE):
        _add(unquote(match.group(1)))

    # 2. absolute URLs mentioning "manifest".
    for match in _ABS_MANIFEST_RE.finditer(decoded):
        url = match.group(0)
        # skip the permalink wrappers themselves (?manifest=… handled above)
        if re.search(r"[?&](?:manifest|iiifContent)=", url, re.IGNORECASE):
            continue
        _add(unquote(url) if "%2F" in url else url)

    # 3. relative hrefs/srcs mentioning "manifest", resolved against the page.
    for match in _REL_MANIFEST_RE.finditer(decoded):
        target = match.group(1)
        if not target.startswith("http"):
            _add(urljoin(base_url, target))

    return candidates


# Links on a landing page worth a second hop (same host only, no assets).
_HREF_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.IGNORECASE)
_ASSET_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                   ".ico", ".pdf", ".webmanifest")
MAX_SECOND_HOP_LINKS = 5


def _same_host_links(page_html: str, page_url: str) -> List[str]:
    """Same-host page links from a landing page (resolver/disambiguation)."""
    host = urlparse(page_url).netloc
    links: List[str] = []
    for match in _HREF_RE.finditer(html.unescape(page_html)):
        target = urljoin(page_url, match.group(1).strip())
        parsed = urlparse(target)
        if parsed.scheme not in ("http", "https") or parsed.netloc != host:
            continue
        if parsed.path.lower().endswith(_ASSET_SUFFIXES):
            continue
        if target != page_url and target not in links:
            links.append(target)
    return links


def _validate_candidates(
    client: httpx.Client, candidates: List[str], tried: List[str]
) -> Optional[str]:
    for candidate in candidates:
        if candidate in tried:
            continue
        tried.append(candidate)
        try:
            resp = _fetch(client, candidate)
            if _classify_iiif_json(json.loads(resp.text)) == "manifest":
                return str(resp.url)
        except Exception:
            continue
        time.sleep(POLITE_DELAY_S)
    return None


def discover_manifest(
    client: httpx.Client, page_html: str, page_url: str
) -> Tuple[Optional[str], List[str]]:
    """Find a valid manifest for a viewer/landing page.

    First validates manifest-looking URLs on the page itself; if none work,
    follows up to MAX_SECOND_HOP_LINKS same-host links (e.g. resolver pages
    listing the actual reader pages) and scans those one level deep.
    Returns (manifest URL or None, all candidate URLs tried).
    """
    tried: List[str] = []
    found = _validate_candidates(
        client, extract_manifest_candidates(page_html, page_url), tried
    )
    if found:
        return found, tried

    for link in _same_host_links(page_html, page_url)[:MAX_SECOND_HOP_LINKS]:
        try:
            resp = _fetch(client, link)
        except Exception:
            continue
        time.sleep(POLITE_DELAY_S)
        found = _validate_candidates(
            client, extract_manifest_candidates(resp.text, str(resp.url)), tried
        )
        if found:
            return found, tried
    return None, tried


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check (and with --fix repair) IIIF manifest links of images."
    )
    parser.add_argument("--fix", action="store_true",
                        help="discover manifests and write Image.iiif_manifest_url")
    parser.add_argument("--only-missing", action="store_true",
                        help="skip images that already have a iiif_manifest_url")
    parser.add_argument("--limit", type=int, default=None,
                        help="process at most N images")
    args = parser.parse_args()

    rows: List[dict] = []
    counts: dict = {}

    with Session(engine) as session, httpx.Client(
        follow_redirects=True, timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "hagiographies-iiif-check/1.0"},
    ) as client:
        query = (
            select(Image, ImageType, Codex)
            .join(ImageType, Image.image_type_id == ImageType.id)  # type: ignore[arg-type]
            .outerjoin(Codex, Image.codex_id == Codex.id)  # type: ignore[arg-type]
            .where(ImageType.name.in_(IIIF_IMAGE_TYPES))  # type: ignore[attr-defined]
            .order_by(Image.id)
        )
        results: Iterable = session.exec(query).all()

        processed = 0
        for image, image_type, codex in results:
            if args.only_missing and image.iiif_manifest_url:
                continue
            if args.limit is not None and processed >= args.limit:
                break
            processed += 1

            status, page_html_text, note = check_url(client, image.url)
            manifest_url: Optional[str] = None

            if status in ("manifest", "assumed_manifest"):
                manifest_url = image.url
            elif status == "not_manifest" and args.fix and page_html_text:
                manifest_url, tried = discover_manifest(
                    client, page_html_text, image.url
                )
                if manifest_url:
                    status = "fixed"
                    note = f"manifest discovered on page ({len(tried)} candidate(s) tried)"
                else:
                    status = "unresolved"
                    note = f"no valid manifest among {len(tried)} candidate(s)"

            if args.fix and manifest_url:
                image.iiif_manifest_url = manifest_url
                session.add(image)

            counts[status] = counts.get(status, 0) + 1
            rows.append({
                "image_id": image.id,
                "codex": codex.codex_unique_identifier if codex else "",
                "image_type": image_type.name,
                "url": image.url,
                "status": status,
                "manifest_url": manifest_url or "",
                "note": note,
            })
            logger.info(f"[{status:>12}] {image.url[:80]}"
                        + (f" → {manifest_url[:60]}" if manifest_url else ""))
            time.sleep(POLITE_DELAY_S)

        if args.fix:
            session.commit()

    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "image_id", "codex", "image_type", "url",
            "status", "manifest_url", "note",
        ])
        writer.writeheader()
        writer.writerows(rows)

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    logger.info(f"[Summary] {processed} image(s) checked: {summary}")
    logger.info(f"[Report] {REPORT_PATH}")


if __name__ == "__main__":
    main()
