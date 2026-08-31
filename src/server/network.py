"""Broadcast helpers and websocket message utilities.

This keeps message fan-out isolated from the gameplay and lobby code.
"""

import asyncio
import json

from .config import players


async def send_all(message, exclude_slot=None):
    """Send a JSON message to all connected players except, optionally, one."""
    text = json.dumps(message)
    targets = [g["websocket"] for slot, g in players.items() if slot != exclude_slot]
    if not targets:
        return
    await asyncio.gather(*(ws.send(text) for ws in targets), return_exceptions=True)
