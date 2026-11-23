"""Check the codices' IIIF manifest links and record the result.

Every 'IIIF manifest' link in public.codex_link is fetched once (a manifest on
several codices is fetched once) and lightly checked: it must answer, parse as
JSON and look like a IIIF Presentation v2 or v3 Manifest. The outcome goes into
codex_link_checked_at / codex_link_check_note (migration 067).

Polite by design: requests to one host are at least --delay seconds apart, also
across redirects and retries, while different hosts are fetched in parallel.

Every manifest that checks out OK is stored in hagio_admin.iiif_manifest_cache
(migration 069, see iiif_cache). A cached manifest is re-fetched conditionally
(ETag / Last-Modified): a 304 keeps the cached copy.

Before checking it runs the manifest/viewer sync (iiif_sync; --no-sync skips
it), so hand edits in Mathesar are tidied first. It also reports manifests
attached to more than one codex for the researchers.

--only picks what to (re)check: all (default), unchecked (never checked, or the
URL was edited since: migration 068 clears the result then) or failed (every
result that is not OK, e.g. to retry Gallica's 403s another day).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import typer
from rich.table import Table

from .conn import announce, connect, console, resolve_url
from .iiif_cache import store, validators
from .iiif_sync import sync

USER_AGENT = "hagiographies-iiif-check/1.0 (+https://github.com/GhentCDH/Hagiographies)"
ACCEPT = "application/ld+json, application/json;q=0.9, */*;q=0.1"
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_RETRY_AFTER = 60.0
GIVE_UP_AFTER = 3  # consecutive unreachable answers before a host is skipped
# Hosts that block at one request per second. Gallica answered 9 manifests and
# then 403/429 for the rest at 1 req/s (2026-11-23).
HOST_DELAY = {"gallica.bnf.fr": 10.0}
MAX_HOST_DELAY = 60.0
# Gallica refuses this checker (HTTP 403) from any network and at any rate,
# also with browser headers over HTTP/2, while a real browser gets 200: it
# fingerprints the client below the headers (2026-11-23). Its 403s say
# nothing about the link; they are noted as such, see GALLICA_403.
# Extra seconds on top of --timeout for one request, body included. Enforced
# outside httpx, which does not time out a SOCKS handshake to a dead host.
DEADLINE_SLACK = 30.0
GALLICA_403 = "not verifiable automatically: Gallica refuses non-browser clients (HTTP 403); open it in a browser"

MANIFEST_LINKS = """
SELECT l.codex_link_id, c.codex_unique_identifier, btrim(l.codex_link_url::text),
       l.codex_link_checked_at IS NULL, coalesce(l.codex_link_check_note, '') LIKE 'OK%'
  FROM public.codex_link l
  JOIN public.codex_link_type t USING (codex_link_type_id)
  JOIN public.codex c USING (codex_id)
 WHERE t.codex_link_type = 'IIIF manifest'
 ORDER BY l.codex_link_id
"""

ONLY = ("all", "unchecked", "failed")

app = typer.Typer(add_completion=False, help=__doc__)


class Pacer:
    """At most one request per `delay` seconds to each host, across threads.

    Hosts in HOST_DELAY get their own, longer delay; a host that answers 429
    gets its delay doubled (up to MAX_HOST_DELAY) for the rest of the run.
    """

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last: dict[str, float] = {}
        self._delay: dict[str, float] = {}

    def delay_for(self, host: str) -> float:
        return self._delay.get(host, max(self.delay, HOST_DELAY.get(host, 0.0)))

    def slow_down(self, host: str) -> None:
        with self._guard:
            self._delay[host] = min(self.delay_for(host) * 2, MAX_HOST_DELAY)

    def wait(self, host: str) -> None:
        with self._guard:
            lock = self._locks[host]
        with lock:
            pause = self._last.get(host, 0.0) + self.delay_for(host) - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self._last[host] = time.monotonic()


@dataclass
class Result:
    url: str
    note: str
    data: dict | None = None  # the manifest, when it was fetched and is OK
    status: int = 0
    etag: str | None = None
    last_modified: str | None = None

    @property
    def ok(self) -> bool:
        return self.note.startswith("OK")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _with_deadline(fn, seconds: float):
    """Run fn() with a hard wall-clock limit; raise TimeoutError past it.

    The work runs in a daemon thread, so a request stuck in a SOCKS handshake
    is abandoned rather than waited for, also at interpreter exit.
    """
    box: dict = {}

    def target() -> None:
        try:
            box["result"] = fn()
        except BaseException as err:  # noqa: BLE001 - re-raised below
            box["error"] = err

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise TimeoutError
    if "error" in box:
        raise box["error"]
    return box["result"]


def _hop(client: httpx.Client, url: str, headers: dict | None = None) -> tuple[int, dict, bytes]:
    """One GET without following redirects; the body only for 2xx, capped."""
    with client.stream("GET", url, headers=headers) as resp:
        headers = dict(resp.headers)
        if not 200 <= resp.status_code < 300:
            return resp.status_code, headers, b""
        body = bytearray()
        for chunk in resp.iter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                break
        return resp.status_code, headers, bytes(body)


def _get(url: str, pacer: Pacer, client: httpx.Client,
         conditional: dict | None = None) -> tuple[int, str, bytes, dict]:
    """GET with paced redirects and one paced retry on 429/503.

    Redirects are followed by hand, so every hop waits its turn for its host.
    Returns (status, final url, body, headers); raises httpx.TransportError or
    TimeoutError when the host cannot be reached.
    """
    deadline = client.timeout.read + DEADLINE_SLACK if client.timeout.read else 60.0
    retried = False
    first = True
    for _ in range(MAX_REDIRECTS + 1):
        pacer.wait(_host(url))
        cond = conditional if first else None  # validators belong to the original URL
        first = False
        status, headers, body = _with_deadline(lambda u=url, c=cond: _hop(client, u, c), deadline)
        if status in (301, 302, 303, 307, 308) and headers.get("location"):
            url = urljoin(url, headers["location"])
            continue
        if status == 429:
            pacer.slow_down(_host(url))
        if status in (429, 503) and not retried:
            retried = True
            try:
                wait = float(headers.get("retry-after", "5"))
            except ValueError:
                wait = 5.0
            time.sleep(min(max(wait, 0.0), MAX_RETRY_AFTER))
            continue
        return status, url, body, headers
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


def check(url: str, pacer: Pacer, client: httpx.Client, cached: tuple | None = None) -> Result:
    """Fetch and classify one manifest.

    cached is the cache's (etag, last_modified, iiif_version, fetched_via) for
    this URL, if any: its validators make the request conditional (a 304 keeps
    the cached copy), and a Gallica 403 counts as OK when a copy fetched in a
    browser is cached.
    """
    if urlsplit(url).scheme not in ("http", "https"):
        return Result(url, "not an http(s) URL")
    conditional = {}
    if cached and cached[0]:
        conditional["If-None-Match"] = cached[0]
    if cached and cached[1]:
        conditional["If-Modified-Since"] = cached[1]
    try:
        status, final, body, headers = _get(url, pacer, client, conditional or None)
    except (httpx.TimeoutException, TimeoutError):
        return Result(url, "unreachable: timed out")
    except (httpx.TransportError, OSError) as err:
        return Result(url, f"unreachable: {err or type(err).__name__}"[:200])
    if status == 0:
        return Result(url, f"unreachable: more than {MAX_REDIRECTS} redirects")
    if status == 304 and cached:
        return Result(url, f"OK (IIIF v{cached[2]}; not modified since cached)", status=304)
    if status == 403 and _host(final) == "gallica.bnf.fr":
        if cached and cached[3] == "browser":
            return Result(url, f"OK (IIIF v{cached[2]}; cached copy fetched in a browser, "
                               "Gallica refuses non-browser clients)", status=403)
        return Result(url, GALLICA_403)
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
    res = Result(url, note, status=status)
    if res.ok and isinstance(data, dict):
        lower = {k.lower(): v for k, v in headers.items()}
        res.data, res.etag, res.last_modified = data, lower.get("etag"), lower.get("last-modified")
    return res


def check_all(urls: list[str], delay: float, timeout: float,
              proxy: str | None = None, cache: dict | None = None) -> dict[str, Result]:
    """One worker per host: hosts run in parallel, a host's URLs one by one.

    proxy (e.g. socks5h://127.0.0.1:1080 over `ssh -D`) routes every request
    through another machine; pacing and User-Agent stay the same.
    """
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
                res = check(url, pacer, client, (cache or {}).get(url))
                dead = dead + 1 if res.note.startswith("unreachable") else 0
            with lock:
                results[url] = res
                done += 1
                mark = "[green]ok[/]" if res.ok else f"[red]{res.note}[/]"
                console.print(f"[dim]{time.strftime('%H:%M:%S')} {done}/{len(urls)}[/] {mark} {url}",
                              highlight=False)

    slow = ", ".join(f"{h} {d:g}s" for h, d in HOST_DELAY.items() if h in by_host)
    console.print(f"checking {len(urls)} manifests on {len(by_host)} hosts, "
                  f"≥{delay:g}s between requests to one host" + (f" ({slow})" if slow else "")
                  + (f", via proxy {proxy}" if proxy else ""))
    client = httpx.Client(
        proxy=proxy,
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": ACCEPT},
        limits=httpx.Limits(max_connections=len(by_host) + 4),
    )
    with client, ThreadPoolExecutor(max_workers=max(1, len(by_host))) as pool:
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
    only: str = typer.Option(
        "all", help="What to check: all, unchecked (never checked or URL edited since) or failed (not OK)."
    ),
    proxy: str = typer.Option(
        None, help="Route requests through a proxy, e.g. socks5h://127.0.0.1:1080 "
        "for an `ssh -N -D 127.0.0.1:1080 <host>` tunnel (socks5h: DNS on the far side too).",
    ),
    no_sync: bool = typer.Option(
        False, "--no-sync", help="Skip the manifest/viewer sync that runs first."
    ),
) -> None:
    if only not in ONLY:
        raise typer.BadParameter(f"--only must be one of {', '.join(ONLY)}")
    url = resolve_url(database_url)
    announce(url)

    if not no_sync:
        with connect(url) as conn:
            sync(conn)
            if dry_run:
                conn.rollback()
            else:
                conn.commit()

    # Read, then let go of the database while the (slow) fetching runs.
    with connect(url, read_only=True) as conn, conn.cursor() as cur:
        cur.execute(MANIFEST_LINKS)
        rows = cur.fetchall()
        cache = validators(cur)
    if not rows:
        console.print("no 'IIIF manifest' links found")
        return

    # Every manifest on the codices, for the 'more than one codex' report.
    codices: dict[str, list[str]] = defaultdict(list)
    for _, codex, u, _, _ in rows:
        codices[u].append(codex)

    if only == "unchecked":
        rows = [r for r in rows if r[3]]
    elif only == "failed":
        rows = [r for r in rows if not r[3] and not r[4]]
    links = [(link_id, codex, u) for link_id, codex, u, _, _ in rows]
    manifests = sorted({u for _, _, u in links})
    console.print(f"{len(links)} manifest links to check (--only {only})")
    results = check_all(manifests, delay, timeout, proxy, cache) if manifests else {}
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
        cached = 0
        for u, res in results.items():
            if res.data is not None:
                store(cur, u, res.data, status=res.status, etag=res.etag,
                      last_modified=res.last_modified, via="checker")
                cached += 1
        conn.commit()
    console.print(f"[green]recorded[/] {len(links)} check results; {cached} manifests cached")


def entrypoint() -> None:  # pragma: no cover - console script shim
    sys.exit(app())


if __name__ == "__main__":  # pragma: no cover
    entrypoint()
