"""World-generation and terrain helpers.

This module starts the split of world logic out of server.py so that map
creation and terrain interpolation are easier to test independently.
"""

import json
import math
import os
import random

from .config import TERRAIN_RESOLUTION, TERRAIN_SIZE, WORLD_MAP_PATH, MAX_PLAYERS, EYE_HEIGHT, SPAWN_RADIUS


def generate_heightmap(seed=42):
    rng = random.Random(seed)
    waves = [
        {
            "freq_x": rng.uniform(0.05, 0.15),
            "freq_z": rng.uniform(0.05, 0.15),
            "phase": rng.uniform(0, math.pi * 2),
            "amplitude": rng.uniform(0.5, 2.5),
        }
        for _ in range(5)
    ]

    river_amplitude = 8.0
    river_freq = 0.04
    river_width = 3.0
    river_depth = 2.5

    half = TERRAIN_SIZE / 2
    heights = []
    for iz in range(TERRAIN_RESOLUTION):
        z = -half + (iz / (TERRAIN_RESOLUTION - 1)) * TERRAIN_SIZE
        row = []
        for ix in range(TERRAIN_RESOLUTION):
            x = -half + (ix / (TERRAIN_RESOLUTION - 1)) * TERRAIN_SIZE

            h = 0.0
            for w in waves:
                h += w["amplitude"] * math.sin(x * w["freq_x"] + w["phase"]) * math.cos(z * w["freq_z"] + w["phase"])

            river_x = river_amplitude * math.sin(z * river_freq)
            distance_from_river = abs(x - river_x)
            if distance_from_river < river_width:
                t = distance_from_river / river_width
                h -= river_depth * (1 - t)

            row.append(round(h, 3))
        heights.append(row)
    return heights


def terrain_height_at(heights, x, z):
    """Bilinear interpolation kept aligned with the browser terrain logic."""
    half = TERRAIN_SIZE / 2
    grid_x = (x + half) / TERRAIN_SIZE * (TERRAIN_RESOLUTION - 1)
    grid_z = (z + half) / TERRAIN_SIZE * (TERRAIN_RESOLUTION - 1)
    grid_x = max(0, min(TERRAIN_RESOLUTION - 1.001, grid_x))
    grid_z = max(0, min(TERRAIN_RESOLUTION - 1.001, grid_z))

    x0, z0 = int(grid_x), int(grid_z)
    x1, z1 = x0 + 1, z0 + 1
    tx, tz = grid_x - x0, grid_z - z0

    h00, h10 = heights[z0][x0], heights[z0][x1]
    h01, h11 = heights[z1][x0], heights[z1][x1]
    top = h00 * (1 - tx) + h10 * tx
    bottom = h01 * (1 - tx) + h11 * tx
    return top * (1 - tz) + bottom * tz


def generate_world_map():
    rng = random.Random(42)
    heights = generate_heightmap(seed=42)
    objects = []

    for _ in range(14):
        angle = rng.uniform(0, math.pi * 2)
        distance = rng.uniform(8, 33)
        x = math.cos(angle) * distance
        z = math.sin(angle) * distance
        y = terrain_height_at(heights, x, z)
        objects.append({"type": "tree", "x": x, "y": y, "z": z})

    building_specs = [
        (-8, -6, 4, 3.5, 4, 0x8a7a6a),
        (9, -4, 5, 4.5, 3, 0x9a8a7a),
        (0, -14, 6, 5, 5, 0x7a6a5a),
    ]
    for x, z, width, height, depth, color in building_specs:
        y = terrain_height_at(heights, x, z)
        objects.append({
            "type": "building",
            "x": x,
            "y": y,
            "z": z,
            "width": width,
            "height": height,
            "depth": depth,
            "color": color,
        })

    return {
        "terrain": {"size": TERRAIN_SIZE, "resolution": TERRAIN_RESOLUTION, "heights": heights},
        "objects": objects,
    }


def load_or_generate_world_map():
    if os.path.exists(WORLD_MAP_PATH):
        with open(WORLD_MAP_PATH, "r") as f:
            return json.load(f)

    world = generate_world_map()
    with open(WORLD_MAP_PATH, "w") as f:
        json.dump(world, f)
    return world


def spawn_position(slot, world_map=None):
    angle = (slot / MAX_PLAYERS) * math.pi * 2
    x = math.cos(angle) * SPAWN_RADIUS
    z = math.sin(angle) * SPAWN_RADIUS
    heights = (world_map or {}).get("terrain", {}).get("heights") or generate_heightmap()
    y = terrain_height_at(heights, x, z) + EYE_HEIGHT
    return x, y, z
