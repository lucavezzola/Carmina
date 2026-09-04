"""Gameplay rules for spells, damage and respawn.

This module owns most of the combat logic previously mixed into server.py.
"""

import asyncio
import math
import time

from .config import (
    FIRE_DEPTH,
    FIRE_DURATION_S,
    FIRE_RADIUS_FAR,
    FIRE_RADIUS_NEAR,
    FIRE_TICK_DAMAGE,
    FIRE_TICK_INTERVAL_S,
    LIGHTNING_DAMAGE,
    LIGHTNING_RANGE,
    LIGHTNING_RADIUS,
    MAX_HP,
    RESPAWN_DELAY_S,
    SHIELD_DURATION_MS,
    SPELLS_COOLDOWNS,
    effective_cooldown_ms,
    forward_vector,
    players,
)
from .network import send_all


def projected_position(caster_slot, target_slot):
    """Return forward and lateral distance of target relative to the caster."""
    caster = players[caster_slot]
    target = players[target_slot]
    fx, fy, fz = forward_vector(caster["yaw"], caster["pitch"])

    dx = target["x"] - caster["x"]
    dy = target["y"] - caster["y"]
    dz = target["z"] - caster["z"]

    avanti = dx * fx + dy * fy + dz * fz
    lateral_dx = dx - avanti * fx
    lateral_dy = dy - avanti * fy
    lateral_dz = dz - avanti * fz
    lato = math.sqrt(lateral_dx ** 2 + lateral_dy ** 2 + lateral_dz ** 2)

    return avanti, lato


def projected_from_origin(origin, forward, target_slot):
    """Project a target onto a spell ray that starts at an arbitrary origin."""
    target = players[target_slot]
    ox, oy, oz = origin
    fx, fy, fz = forward

    dx = target["x"] - ox
    dy = target["y"] - oy
    dz = target["z"] - oz

    avanti = dx * fx + dy * fy + dz * fz
    lateral_dx = dx - avanti * fx
    lateral_dy = dy - avanti * fy
    lateral_dz = dz - avanti * fz
    lato = math.sqrt(lateral_dx ** 2 + lateral_dy ** 2 + lateral_dz ** 2)

    return avanti, lato


def find_lightning_target(caster_slot):
    """Find the nearest player inside the caster's forward lightning corridor."""
    best_slot = None
    best_distance = None
    for slot in players:
        if slot == caster_slot:
            continue
        avanti, lato = projected_position(caster_slot, slot)
        if not (0 <= avanti <= LIGHTNING_RANGE):
            continue
        if lato > LIGHTNING_RADIUS:
            continue
        if best_distance is None or avanti < best_distance:
            best_distance = avanti
            best_slot = slot
    return best_slot


def find_fire_targets_static(origin, forward, exclude_slot=None):
    """Find players inside the expanding cone of a fire spell."""
    hit_slots = []
    for slot in players:
        if slot == exclude_slot:
            continue
        avanti, lato = projected_from_origin(origin, forward, slot)
        if not (0 <= avanti <= FIRE_DEPTH):
            continue
        t = avanti / FIRE_DEPTH
        raggio_consentito = FIRE_RADIUS_NEAR + t * (FIRE_RADIUS_FAR - FIRE_RADIUS_NEAR)
        if lato <= raggio_consentito:
            hit_slots.append(slot)
    return hit_slots


async def apply_damage(slot, amount):
    """Apply shields, health changes, defeat notifications, and respawn scheduling."""
    player_state = players.get(slot)
    if player_state is None:
        return

    now = time.monotonic() * 1000
    if player_state.get("shielded_until", 0) > now:
        amount = 0

    player_state["hp"] = max(0, player_state["hp"] - amount)
    await send_all({"type": "health_update", "slot": slot, "hp": player_state["hp"]})

    if player_state["hp"] <= 0:
        await send_all({"type": "player_down", "slot": slot})
        asyncio.create_task(respawn_after_delay(slot))


async def respawn_after_delay(slot):
    """Restore a defeated player after the configured respawn delay."""
    await asyncio.sleep(RESPAWN_DELAY_S)
    player_state = players.get(slot)
    if player_state is None:
        return

    x, y, z = player_state.get("spawn", (0, 0, 0))
    player_state["x"], player_state["y"], player_state["z"] = x, y, z
    player_state["hp"] = MAX_HP
    await send_all({
        "type": "player_respawn",
        "slot": slot,
        "x": x,
        "y": y,
        "z": z,
        "hp": MAX_HP,
    })


async def run_fire_effect(caster_slot):
    """Apply fire breath damage using the caster's current position and aim."""
    ticks = int(FIRE_DURATION_S / FIRE_TICK_INTERVAL_S)
    
    for i in range(ticks):
        caster = players.get(caster_slot)
        if caster is None:
            return
        
        origin = (
            caster["x"],
            caster["y"],
            caster["z"],
        )
        forward = forward_vector(caster["yaw"], caster["pitch"])
        
        targets = find_fire_targets_static(
            origin,
            forward,
            exclude_slot=caster_slot,
        )
        
        for target_slot in targets:
            await apply_damage(target_slot, FIRE_TICK_DAMAGE)
            
        if i < ticks - 1:
            await asyncio.sleep(FIRE_TICK_INTERVAL_S)


async def try_spell(slot, word):
    """Validate cooldowns and execute the requested authoritative spell action."""
    player_state = players.get(slot)
    if player_state is None:
        return

    now = time.monotonic() * 1000
    last_cast = player_state["last_cast"].get(word, 0.0)
    if now - last_cast < effective_cooldown_ms(word):
        return
    player_state["last_cast"][word] = now

    if word == "scudo":
        player_state["shielded_until"] = now + SHIELD_DURATION_MS
        await send_all({"type": "spell", "slot": slot, "word": word})
        return

    if word == "fulmine":
        target = find_lightning_target(slot)
        await send_all({"type": "spell", "slot": slot, "word": word, "target": target})
        if target is not None:
            await apply_damage(target, LIGHTNING_DAMAGE)
        return

    if word == "fuoco":
        await send_all({
            "type": "spell",
            "slot": slot,
            "word": word,
            "duration": FIRE_DURATION_S,
        })
        asyncio.create_task(run_fire_effect(slot))
        return
