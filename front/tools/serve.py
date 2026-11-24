"""Serve front/ for development, with HTTP Range support (PMTiles needs it).

Python's http.server ignores Range headers, so MapLibre's PMTiles basemap
fails against it. This adds single-range byte serving and nothing else.
Stdlib only:  uv run --no-project python front/tools/serve.py [--port 9162]
"""

import argparse
import functools
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/vnd.sqlite3", ".sqlite")
mimetypes.add_type("application/octet-stream", ".pmtiles")
mimetypes.add_type("application/x-protobuf", ".pbf")

RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


class RangeHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_head(self):
        match = RANGE.match(self.headers.get("Range", "").strip())
        path = self.translate_path(self.path)
        if not match or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        first, last = match.groups()
        if first:
            start, end = int(first), min(int(last) if last else size - 1, size - 1)
        else:  # suffix range: the last N bytes
            start, end = max(size - int(last or 0), 0), size - 1
        if start > end or start >= size:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        handle = open(path, "rb")
        handle.seek(start)
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return handle

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self._remaining = None
        while remaining > 0:
            chunk = source.read(min(65536, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=9162)
    parser.add_argument("--directory", default=os.path.join(os.path.dirname(__file__), ".."))
    args = parser.parse_args()
    handler = functools.partial(RangeHandler, directory=os.path.abspath(args.directory))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Serving {os.path.abspath(args.directory)} on http://localhost:{args.port}/", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
