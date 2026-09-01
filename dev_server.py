#!/usr/bin/env python3
"""Development HTTP server for the browser client.

Serves the public/ folder and explicitly registers .mjs as JavaScript so the
browser can import the modularized game client from public/js/*.mjs.
"""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = PROJECT_ROOT / "public"

# Browsers require .mjs to be served with a JavaScript MIME type.
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/javascript", ".js")


class PublicFileHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"[http] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the public web client locally.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), PublicFileHandler)
    print(f"Serving {PUBLIC_DIR} on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
