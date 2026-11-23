"""Check the codices' IIIF manifest links and record the result.

Every 'IIIF manifest' link in public.codex_link is fetched once (a manifest on
several codices is fetched once) and lightly checked: it must answer, parse as
JSON and look like a IIIF Presentation v2 or v3 Manifest. The outcome goes into
codex_link_checked_at / codex_link_check_note (migration 067).

Polite by design: requests to one host are at least --delay seconds apart, also
across redirects and retries, while different hosts are fetched in parallel.

It also adds the Theseus 'IIIF viewer' link of every manifest that lacks one
(migration 066 did this once; manifests added later get theirs here), and
reports manifests attached to more than one codex for the researchers.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import typer
from rich.table import Table

from .conn import announce, connect, console, resolve_url

USER_AGENT = "hagiographies-iiif-check/1.0 (+https://github.com/GhentCDH/Hagiographies)"
ACCEPT = "application/ld+json, application/json;q=0.9, */*;q=0.1"
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_RETRY_AFTER = 60.0
GIVE_UP_AFTER = 3  # consecutive unreachable answers before a host is skipped

# The same SQL as migration 066, so a viewer link added here is identical to
# one added there and ON CONFLICT recognises it.
ADD_VIEWER_LINKS = """
INSERT INTO public.codex_link (codex_id, codex_link_type_id, codex_link_url)
SELECT l.codex_id, v.codex_link_type_id,
       'https://theseusviewer.org/?iiif-content=' ||
       replace(replace(replace(replace(replace(replace(replace(
           l.codex_link_url::text, '%', '%25'), '&', '%26'), '?', '%3F'), '#', '%23'),
           '=', '%3D'), '+', '%2B'), ' ', '%20')
  FROM public.codex_link l
  JOIN public.codex_link_type m ON m.codex_link_type_id = l.codex_link_type_id
                               AND m.codex_link_type = 'IIIF manifest'
 CROSS JOIN public.codex_link_type v
 WHERE v.codex_link_type = 'IIIF viewer'
ON CONFLICT (codex_id, codex_link_type_id, codex_link_url) DO NOTHING
"""

MANIFEST_LINKS = """
SELECT l.codex_link_id, c.codex_unique_identifier, btrim(l.codex_link_url::text)
  FROM public.codex_link l
  JOIN public.codex_link_type t USING (codex_link_type_id)
  JOIN public.codex c USING (codex_id)
 WHERE t.codex_link_type = 'IIIF manifest'
 ORDER BY l.codex_link_id
"""

app = typer.Typer(add_completion=False, help=__doc__)


class _NoRedirect(HTTPRedirectHandler):
    """Hand redirects back to us, so every hop is paced per host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


_opener = build_opener(_NoRedirect)


class Pacer:
    """At most one request per `delay` seconds to each host, across threads."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        with self._guard:
            lock = self._locks[host]
        with lock:
            pause = self._last.get(host, 0.0) + self.delay - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self._last[host] = time.monotonic()


@dataclass
class Result:
    url: str
    note: str

    @property
    def ok(self) -> bool:
        return self.note.startswith("OK")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _get(url: str, pacer: Pacer, timeout: float) -> tuple[int, str, bytes, dict]:
    """GET with paced redirects and one paced retry on 429/503.

    Returns (status, final url, body, headers); raises URLError/OSError when
    the host cannot be reached.
    """
    retried = False
    for _ in range(MAX_REDIRECTS + 1):
        pacer.wait(_host(url))
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
        try:
            with _opener.open(req, timeout=timeout) as resp:
                return resp.status, url, resp.read(MAX_BYTES + 1), dict(resp.headers)
        except HTTPError as err:
            if err.code in (301, 302, 303, 307, 308) and err.headers.get("Location"):
                url = urljoin(url, err.headers["Location"])
                continue
            if err.code in (429, 503) and not retried:
                retried = True
                try:
                    wait = float(err.headers.get("Retry-After", "5"))
                except ValueError:
                    wait = 5.0
                time.sleep(min(max(wait, 0.0), MAX_RETRY_AFTER))
                continue
            return err.code, url, b"", dict(err.headers or {})
    return 0, url, b"", {}


def classify(data: object) -> str:
    """Light IIIF check on parsed JSON: Manifest v2/v3, Collection, or neither."""
    if not isinstance(data, dict):
        return "JSON, not a IIIF manifest"
    ctx = data.get("@context")
    ctx = " ".join(c for c in ctx if isinstance(c, str)) if isinstance(ctx, list) else str(ctx or "")
    kind = data.get("type") or data.get("@type")
    if kind == "Manifest" and "iiif.io/api/presentation/3" in ctx:
        return "OK (IIIF v3)"
    if kind == "sc:Manifest" and "iiif.io/api/presentation/2" in ctx:
        return "OK (IIIF v2)"
    if kind in ("Collection", "sc:Collection"):
        return "IIIF Collection, not a manifest"
    if kind in ("Manifest", "sc:Manifest"):
        return "IIIF Manifest without a presentation @context"
    return "JSON, not a IIIF manifest"


def check(url: str, pacer: Pacer, timeout: float) -> Result:
    if urlsplit(url).scheme not in ("http", "https"):
        return Result(url, "not an http(s) URL")
    try:
        status, final, body, headers = _get(url, pacer, timeout)
    except (URLError, OSError) as err:
        reason = getattr(err, "reason", err)
        return Result(url, f"unreachable: {reason}"[:200])
    if status == 0:
        return Result(url, f"unreachable: more than {MAX_REDIRECTS} redirects")
    if status == 403:
        return Result(url, "HTTP 403 (forbidden; the host may block automated clients)")
    if status >= 400:
        return Result(url, f"HTTP {status}")
    if len(body) > MAX_BYTES:
        return Result(url, f"larger than {MAX_BYTES // (1024 * 1024)} MB, not checked")
    try:
        data = json.loads(body)
    except ValueError:
        ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "?")
        return Result(url, f"not JSON ({ctype.split(';')[0]})")
    note = classify(data)
    if final != url:
        note += f"; redirects to {final}"
    return Result(url, note)


def check_all(urls: list[str], delay: float, timeout: float) -> dict[str, Result]:
    """One worker per host: hosts run in parallel, a host's URLs one by one."""
    by_host: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        by_host[_host(url)].append(url)
    pacer = Pacer(delay)
    results: dict[str, Result] = {}
    done = 0
    lock = threading.Lock()

    def run(host_urls: list[str]) -> None:
        nonlocal done
        dead = 0  # consecutive unreachable answers from this host
        for url in host_urls:
            if dead >= GIVE_UP_AFTER:
                res = Result(url, f"unreachable: host not answering, skipped after {GIVE_UP_AFTER} failures")
            else:
                res = check(url, pacer, timeout)
                dead = dead + 1 if res.note.startswith("unreachable") else 0
            with lock:
                results[url] = res
                done += 1
                mark = "[green]ok[/]" if res.ok else f"[red]{res.note}[/]"
                console.print(f"[dim]{done}/{len(urls)}[/] {mark} {url}", highlight=False)

    console.print(f"checking {len(urls)} manifests on {len(by_host)} hosts, "
                  f"≥{delay:g}s between requests to one host")
    with ThreadPoolExecutor(max_workers=max(1, len(by_host))) as pool:
        list(pool.map(run, by_host.values()))
    return results


@app.command()
def main(
    database_url: str = typer.Option(
        None, help="Database to check (default: DATABASE_URL / PG_DATABASE_URL)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch and report, but write nothing."
    ),
    delay: float = typer.Option(1.0, min=1.0, help="Seconds between requests to one host."),
    timeout: float = typer.Option(30.0, help="Seconds before a request gives up."),
) -> None:
    url = resolve_url(database_url)
    announce(url)

    # Read, then let go of the database while the (slow) fetching runs.
    with connect(url, read_only=True) as conn, conn.cursor() as cur:
        cur.execute(MANIFEST_LINKS)
        links = cur.fetchall()
    if not links:
        console.print("no 'IIIF manifest' links found")
        return

    manifests = sorted({u for _, _, u in links})
    results = check_all(manifests, delay, timeout)

    # Summary per outcome, with the codices of every failure.
    codices: dict[str, list[str]] = defaultdict(list)
    for _, codex, u in links:
        codices[u].append(codex)
    counts = Counter(r.note.split(";")[0] if r.ok else r.note.split(":")[0] for r in results.values())
    table = Table("result", "manifests")
    for note, n in counts.most_common():
        table.add_row(note, str(n))
    console.print(table)
    for u in manifests:
        if not results[u].ok:
            console.print(f"[red]{results[u].note}[/] {u} [dim]({', '.join(codices[u])})[/]", highlight=False)
    shared = {u: c for u, c in codices.items() if len(set(c)) > 1}
    if shared:
        console.print(f"\n[yellow]{len(shared)} manifests are linked to more than one codex[/] "
                      "(allowed, but check whether that is right):")
        for u, c in sorted(shared.items()):
            console.print(f"  {u}: {', '.join(sorted(set(c)))}", highlight=False)

    if dry_run:
        console.print("[yellow]dry run — nothing was written[/]")
        return

    with connect(url) as conn, conn.cursor() as cur:
        for link_id, _, u in links:
            cur.execute(
                "UPDATE public.codex_link SET codex_link_checked_at = now(), "
                "codex_link_check_note = %s WHERE codex_link_id = %s",
                (results[u].note, link_id),
            )
        cur.execute(ADD_VIEWER_LINKS)
        added = cur.rowcount
        conn.commit()
    console.print(f"[green]recorded[/] {len(links)} check results; {added} viewer links added")


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
