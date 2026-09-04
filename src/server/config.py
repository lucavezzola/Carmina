"""Shared server configuration constants.

This file centralizes the values that must stay consistent between the
server gameplay rules and the client visual logic.
"""

import math

# Network endpoints and shared gameplay dimensions.
SERVER_ADDRESS = "0.0.0.0"
SERVER_PORT = 8765

SPELLS_LIST = ["fulmine", "scudo", "fuoco"]
MODEL_PATH = "model"
SAMPLE_RATE = 16000

MAX_PLAYERS = 5
SPELLS_COOLDOWNS = {"fulmine": 18000, "scudo": 3000, "fuoco": 7000}
SPAWN_RADIUS = 3.0
EYE_HEIGHT = 1.7
players = {}

# Terrain settings must match the generated map and browser interpolation.
TERRAIN_SIZE = 180.0
TERRAIN_RESOLUTION = 65
WORLD_MAP_PATH = "world_map_2.json"

MAX_HP = 100
RESPAWN_DELAY_S = 3.0

LIGHTNING_RANGE = 20.0
LIGHTNING_RADIUS = 0.6
LIGHTNING_DAMAGE = 25

FIRE_DEPTH = 5.0
FIRE_RADIUS_NEAR = 0.5
FIRE_RADIUS_FAR = 2.5
FIRE_DURATION_S = 5.0
FIRE_TICK_INTERVAL_S = 0.2
FIRE_TICK_DAMAGE = 1.2
SHIELD_DURATION_MS = 2400


def effective_cooldown_ms(word):
    if word == "fuoco":
        return FIRE_DURATION_S * 1000 + SPELLS_COOLDOWNS["fuoco"]
    return SPELLS_COOLDOWNS[word]


def forward_vector(yaw, pitch):
    """Same convention as the browser camera in Three.js."""
    fx = -math.cos(pitch) * math.sin(yaw)
    fy = math.sin(pitch)
    fz = -math.cos(pitch) * math.cos(yaw)
    return (fx, fy, fz)
