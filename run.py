#!/usr/bin/env python3
"""Start the game, web server, and Cloudflare quick tunnels together."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
HTTP_PORT = 8080
WS_PORT = 8765
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def python_executable() -> str:
    """Use the repository virtual environment when it exists."""
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


class Tunnel:
    def __init__(self, label: str, port: int, on_url):
        self.label = label
        self.port = port
        self.on_url = on_url
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        command = [
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--url",
            f"http://127.0.0.1:{self.port}",
        ]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "cloudflared was not found on PATH. Install it and run this command again."
            ) from error

        threading.Thread(target=self._read_output, daemon=True).start()

    def _read_output(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            print(f"[{self.label}] {line.rstrip()}", flush=True)
            match = TUNNEL_URL_RE.search(line)
            if match:
                self.on_url(match.group(0))

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()


def start_process(command: list[str], label: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def forward_output() -> None:
        assert process.stdout
        for line in process.stdout:
            print(f"[{label}] {line.rstrip()}", flush=True)

    threading.Thread(target=forward_output, daemon=True).start()
    return process


def main() -> int:
    processes: list[subprocess.Popen[str]] = []
    tunnels: list[Tunnel] = []
    config_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="carmina-runtime-", delete=False, encoding="utf-8"
    )
    config_path = Path(config_file.name)
    config_file.close()

    http_url: str | None = None
    ws_url: str | None = None
    ready = threading.Event()

    def update_ws_url(url: str) -> None:
        nonlocal ws_url
        ws_url = url.replace("https://", "wss://", 1)
        config_path.write_text(json.dumps({"wss_url": ws_url}), encoding="utf-8")
        if http_url:
            ready.set()

    def update_http_url(url: str) -> None:
        nonlocal http_url
        http_url = url
        if ws_url:
            ready.set()

    config_path.write_text(json.dumps({"wss_url": f"ws://127.0.0.1:{WS_PORT}"}), encoding="utf-8")

    try:
        interpreter = python_executable()
        os.chdir(PROJECT_ROOT)
        processes.append(start_process([interpreter, "server.py"], "game"))
        processes.append(
            start_process(
                [
                    interpreter,
                    "dev_server.py",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(HTTP_PORT),
                    "--runtime-config",
                    str(config_path),
                ],
                "web",
            )
        )

        tunnels = [
            Tunnel("web-tunnel", HTTP_PORT, update_http_url),
            Tunnel("ws-tunnel", WS_PORT, update_ws_url),
        ]
        for tunnel in tunnels:
            tunnel.start()

        deadline = time.monotonic() + 30
        while not ready.is_set():
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"A service exited with code {process.returncode}.")
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for both Cloudflare tunnel URLs.")
            time.sleep(0.25)

        print("\nCarmina is online", flush=True)
        print(f"Web link: {http_url}", flush=True)
        print(f"WebSocket tunnel: {ws_url}", flush=True)
        print("Press Ctrl+C to stop all services.", flush=True)

        while True:
            for process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"A service exited with code {process.returncode}.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping Carmina...", flush=True)
    finally:
        for tunnel in tunnels:
            tunnel.stop()
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        config_path.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())