#!/usr/bin/env python3
"""Development HTTP server for the browser client.

Serves the public/ folder and explicitly registers .mjs as JavaScript so the
browser can import the modularized game client from public/js/*.mjs.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = PROJECT_ROOT / "public"

# Browsers require .mjs to be served with a JavaScript MIME type.
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/javascript", ".js")


class PublicFileHandler(SimpleHTTPRequestHandler):
    runtime_config_path: Path | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/runtime-config.json" and self.runtime_config_path:
            try:
                payload = self.runtime_config_path.read_bytes()
            except OSError:
                self.send_error(503, "Runtime configuration is not ready")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        print(f"[http] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the public web client locally.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--runtime-config", type=Path)
    args = parser.parse_args()

    PublicFileHandler.runtime_config_path = args.runtime_config
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
