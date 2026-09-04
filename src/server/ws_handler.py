"""WebSocket client handler and session setup.

This module owns the per-client lifecycle and the Vosk recognizer state.
"""

import asyncio
import json

import websockets
from vosk import KaldiRecognizer

from .combat import try_spell
from .config import MAX_HP, SAMPLE_RATE, SPELLS_LIST, players
from .network import send_all, send_to
from .players import spawn_position
from .voice import find_spell_matches


async def handle_client(websocket, model, world_map):
    """Register one client, stream speech/position messages, and clean up on exit."""
    slot = None
    for candidate in range(5):
        if candidate not in players:
            slot = candidate
            break

    if slot is None:
        await websocket.send(json.dumps({"type": "full"}))
        await websocket.close()
        return

    detected_in_utterance = set()

    print(f"Client connesso: {websocket.remote_address}")
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    spawn_x, spawn_y, spawn_z = spawn_position(slot, world_map)
    players[slot] = {
        "websocket": websocket,
        "recognizer": recognizer,
        "last_cast": {word: 0.0 for word in SPELLS_LIST},
        "x": spawn_x,
        "y": spawn_y,
        "z": spawn_z,
        "yaw": 0.0,
        "pitch": 0.0,
        "hp": MAX_HP,
        "shielded_until": 0.0,
        "teleport_target": None,
    }

    existing_players = [
        {"slot": s, "x": p["x"], "y": p["y"], "z": p["z"], "yaw": p["yaw"], "pitch": p["pitch"], "hp": p["hp"]}
        for s, p in players.items() if s != slot
    ]
    await websocket.send(json.dumps({
        "type": "welcome",
        "your_slot": slot,
        "spawn_x": spawn_x,
        "spawn_y": spawn_y,
        "spawn_z": spawn_z,
        "players": existing_players,
        "world_map": world_map,
    }))

    await send_all({
        "type": "player_connected",
        "slot": slot,
        "x": spawn_x,
        "y": spawn_y,
        "z": spawn_z,
        "yaw": 0.0,
        "pitch": 0.0,
    }, exclude_slot=slot)

    try:
        async for message in websocket:
            if isinstance(message, (bytes, bytearray)):
                player_state = players[slot]
                rec = player_state["recognizer"]

                if rec.AcceptWaveform(message):
                    result = json.loads(rec.Result())
                    recognized_text = result.get("text", "")
                    for match in find_spell_matches(recognized_text):
                        word = match.group(1).lower()
                        if word in detected_in_utterance:
                            continue
                        detected_in_utterance.add(word)
                        asyncio.create_task(try_spell(slot, word))
                    detected_in_utterance.clear()
                else:
                    partial_text = json.loads(rec.PartialResult()).get("partial", "")
                    for match in find_spell_matches(partial_text):
                        word = match.group(1).lower()
                        if word in detected_in_utterance:
                            continue
                        detected_in_utterance.add(word)
                        asyncio.create_task(try_spell(slot, word))

            else:
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "rtc_signal":
                    target = data.get("target")
                    signal = data.get("signal")
                    if isinstance(target, int) and isinstance(signal, dict) and target in players:
                        await send_to(target, {
                            "type": "rtc_signal",
                            "from": slot,
                            "signal": signal,
                        })

                elif data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong", "id": data.get("id")}))

                elif data.get("type") == "position":
                    player_state = players[slot]
                    player_state["x"] = data.get("x", player_state["x"])
                    player_state["y"] = data.get("y", player_state["y"])
                    player_state["z"] = data.get("z", player_state["z"])
                    player_state["yaw"] = data.get("yaw", player_state["yaw"])
                    player_state["pitch"] = data.get("pitch", player_state["pitch"])
                    player_state["position_dirty"] = True

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        del players[slot]
        print(f"Giocatore disconnesso da slot {slot}")
        await send_all({"type": "player_disconnected", "slot": slot})
