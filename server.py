"""
Game server entry point.

The server keeps each player's x/y/z/yaw state, broadcasts it to connected
clients, and listens for voice-triggered spell events.

Usage:
    pip install vosk websockets
    python server.py
"""

import asyncio

import websockets
from vosk import Model

from src.server.config import (
    SERVER_ADDRESS,
    SERVER_PORT,
    MODEL_PATH,
)
from src.server.network import broadcast_dirty_positions
from src.server.world import load_or_generate_world_map as load_world_map
from src.server.ws_handler import handle_client

# ===== SERVER CONFIGURATION =====
# Phase 1 bootstrap: keep runtime behavior stable while delegating shared
# constants and world logic to the new package structure.

# ===== MODEL CONFIGURATION =====
# Moved to src/server/config.py.

# ===== GAME CONFIGURATION =====
# Moved to src/server/config.py.

# ===== GAME WORLD SETUP =====
# Moved to src/server/world.py and kept as a shared world-state dependency.
WORLD_MAP = load_world_map()

# ===== MODEL LOADING =====
print(f"Loading the Italian Vosk model from `{MODEL_PATH}` ...")

try:
    model = Model(MODEL_PATH)  # Load the Vosk model used for real-time spell recognition.
except Exception:
    print(f"Model loading failed. Add a valid model in `{MODEL_PATH}` and try again.")
    exit()  # A bare exit() is intentionally kept for the current startup flow.


# ===== SPELL DETECTION =====
# Moved to src/server/voice.py.

async def main():
    """Start the WebSocket server and keep it alive for connected clients."""
    position_task = asyncio.create_task(broadcast_dirty_positions())
    try:
        async with websockets.serve(lambda ws: handle_client(ws, model, WORLD_MAP), SERVER_ADDRESS, SERVER_PORT):
            print(f"Voice server listening on wss://{SERVER_ADDRESS}:{SERVER_PORT}")
            await asyncio.Future()
    finally:
        position_task.cancel()
        await asyncio.gather(position_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())