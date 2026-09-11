# Carmina

A small multiplayer spellcasting prototype built around a browser client and a Python backend.

Features:
- first-person movement and world rendering in the browser
- WebSocket multiplayer state sync
- voice-driven spell casting with Vosk
- simple combat, cooldowns, and procedural map generation
- a basic world editor for terrain and map data

## Run

Start the full stack:

```bash
python .\run.py
```

This starts:
- the game server on port `8765`
- the browser client on port `8080`
- Cloudflare tunnels when `cloudflared` is installed and available on `PATH`

## Manual startup

```bash
python server.py
python dev_server.py --host 127.0.0.1 --port 8080
```

## Requirements

- Python 3
- Vosk model in `model/`
- `websockets`
- `vosk`
- `cloudflared` for public tunnel support

## Structure

- `server.py` — game server entry point
- `dev_server.py` — local web server for the browser client
- `run.py` — launches the full stack
- `src/server/` — networking, world logic, combat, voice matching
- `public/` — browser game client and assets
- `world_editor/` — map editor files
- `world_map*.json` — generated world data

This is an in-progress prototype focused on the voice spell system and multiplayer loop, not a finished commercial game.