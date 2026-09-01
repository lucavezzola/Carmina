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

    river_amplitude = 12.0
    river_freq = 0.04
    river_width = 4.0
    river_depth = 3.5

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

            mountain = 12.0 * math.exp(-((x + 42) ** 2 + (z - 38) ** 2) / 850.0)
            ridge = 7.0 * math.exp(-((x - 58) ** 2 + (z + 42) ** 2) / 1200.0)
            h += mountain + ridge

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

    for _ in range(42):
        angle = rng.uniform(0, math.pi * 2)
        distance = rng.uniform(8, 78)
        x = math.cos(angle) * distance
        z = math.sin(angle) * distance
        y = terrain_height_at(heights, x, z)
        objects.append({"type": "tree", "x": x, "y": y, "z": z})

    building_specs = [
        (-18, -12, 7, 5, 7, 0x8a7a6a),
        (18, -8, 9, 6, 6, 0x9a8a7a),
        (-4, -30, 10, 7, 8, 0x7a6a5a),
        (38, 20, 8, 5, 10, 0x6d7f86),
        (-42, 28, 11, 8, 7, 0x806b5b),
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

    column_specs = [
        (-12, 5, 0.9, 5, 0xb8b1a4), (12, 10, 0.8, 4, 0xb8b1a4),
        (28, -22, 1.0, 6, 0x9ea7ad), (-30, -26, 0.75, 4.5, 0xc2b280),
        (48, 2, 1.1, 7, 0x87939a),
    ]
    for x, z, radius, height, color in column_specs:
        objects.append({
            "type": "column", "x": x, "y": terrain_height_at(heights, x, z) + height / 2,
            "z": z, "radius": radius, "height": height, "rotation": {"x": 0, "y": 0, "z": 0},
            "color": color,
        })

    platform_specs = [
        (-34, -2, 8, 0.8, 8, 5.0, 0x526b73),
        (-20, 14, 6, 0.7, 6, 3.5, 0x5f7880),
        (4, 24, 7, 0.8, 7, 6.0, 0x806c5a),
        (30, 34, 10, 0.8, 6, 8.0, 0x526b73),
        (58, -8, 8, 0.8, 8, 5.5, 0x6f6659),
    ]
    for x, z, width, height, depth, lift, color in platform_specs:
        base_y = terrain_height_at(heights, x, z) + lift
        objects.append({
            "type": "platform", "x": x, "y": base_y, "z": z,
            "width": width, "height": height, "depth": depth, "color": color,
        })

    ramp_specs = [
        (-28, 8, 8, 1.2, 14, 0.28, 0x9b7653),
        (8, -2, 7, 1.0, 12, -0.32, 0x8c694d),
        (34, 12, 9, 1.2, 16, 0.25, 0x9a795b),
        (-4, 42, 8, 1.0, 14, -0.28, 0x766a5c),
    ]
    for x, z, width, height, depth, angle, color in ramp_specs:
        center_y = terrain_height_at(heights, x, z) + 2.0
        objects.append({
            "type": "ramp", "x": x, "y": center_y, "z": z,
            "width": width, "height": height, "depth": depth,
            "rotation": {"x": angle, "y": 0, "z": 0}, "color": color,
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
