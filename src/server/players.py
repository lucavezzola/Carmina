"""Player registry and spawn helpers.

This module owns the lobby logic that previously lived in server.py.
"""

import math

from .config import MAX_PLAYERS, EYE_HEIGHT, SPAWN_RADIUS, players
from .world import generate_heightmap, terrain_height_at


def free_slot():
    for i in range(MAX_PLAYERS):
        if i not in players:
            return i
    return None


def spawn_position(slot, world_map=None):
    angle = (slot / MAX_PLAYERS) * math.pi * 2
    x = math.cos(angle) * SPAWN_RADIUS
    z = math.sin(angle) * SPAWN_RADIUS
    heights = (world_map or {}).get("terrain", {}).get("heights") or generate_heightmap()
    y = terrain_height_at(heights, x, z) + EYE_HEIGHT
    return x, y, z
