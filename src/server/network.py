"""Broadcast helpers and websocket message utilities.

This keeps message fan-out isolated from the gameplay and lobby code.
"""

import asyncio
import json

from .config import players

POSITION_BROADCAST_INTERVAL_S = 0.1


async def send_all(message, exclude_slot=None):
    """Send a JSON message to all connected players except, optionally, one."""
    text = json.dumps(message)
    targets = [g["websocket"] for slot, g in players.items() if slot != exclude_slot]
    if not targets:
        return
    await asyncio.gather(*(ws.send(text) for ws in targets), return_exceptions=True)


async def send_to(slot, message):
    """Send a JSON message to one connected player."""
    player = players.get(slot)
    if player is None:
        return
    try:
        await player["websocket"].send(json.dumps(message))
    except Exception:
        return


async def broadcast_dirty_positions():
    """Coalesce frequent position updates into a fixed-rate broadcast stream."""
    while True:
        await asyncio.sleep(POSITION_BROADCAST_INTERVAL_S)
        for slot, player in list(players.items()):
            if not player.pop("position_dirty", False):
                continue
            await send_all({
                "type": "player_position",
                "slot": slot,
                "x": player["x"],
                "y": player["y"],
                "z": player["z"],
                "yaw": player["yaw"],
                "pitch": player["pitch"],
            }, exclude_slot=slot)
