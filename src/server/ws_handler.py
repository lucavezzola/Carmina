"""WebSocket client handler and session setup.

This module owns the per-client lifecycle and the Vosk recognizer state.
"""

import json

import websockets
from vosk import KaldiRecognizer

from .combat import try_spell
from .config import MAX_HP, SAMPLE_RATE, SPELLS_LIST, players
from .network import send_all, send_to
from .players import spawn_position


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

    emitted_spell_count = 0
    partial_checked_until = 0
    max_spell_length = max(map(len, SPELLS_LIST))

    print(f"Client connesso: {websocket.remote_address}")
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    spawn_x, spawn_y, spawn_z = spawn_position(slot, world_map)
    players[slot] = {
        "websocket": websocket,
        "recognizer": recognizer,
        "last_recognized": None,
        "last_cast": {word: 0.0 for word in SPELLS_LIST},
        "x": spawn_x,
        "y": spawn_y,
        "z": spawn_z,
        "yaw": 0.0,
        "pitch": 0.0,
        "hp": MAX_HP,
        "shielded_until": 0.0,
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
                    rec.Result()
                    emitted_spell_count = 0
                    partial_checked_until = 0
                    player_state["last_recognized"] = None
                else:
                    partial_text = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if len(partial_text) < partial_checked_until:
                        partial_checked_until = 0
                    scan_from = max(0, partial_checked_until - max_spell_length + 1)
                    new_partial = partial_text[scan_from:]
                    partial_matches = []
                    for spell in sorted(SPELLS_LIST, key=len, reverse=True):
                        import re
                        pattern = re.compile(rf"(?<!\w)({re.escape(spell)})(?!\w)", re.IGNORECASE)
                        for match in pattern.finditer(new_partial):
                            partial_matches.append(match)
                    for match in partial_matches:
                        if scan_from + match.end() > partial_checked_until:
                            word = match.group(1)
                            await try_spell(slot, word)
                            player_state["last_recognized"] = word
                            emitted_spell_count += 1
                    partial_checked_until = len(partial_text)

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

                elif data.get("type") == "position":
                    player_state = players[slot]
                    player_state["x"] = data.get("x", player_state["x"])
                    player_state["y"] = data.get("y", player_state["y"])
                    player_state["z"] = data.get("z", player_state["z"])
                    player_state["yaw"] = data.get("yaw", player_state["yaw"])
                    player_state["pitch"] = data.get("pitch", player_state["pitch"])
                    await send_all({
                        "type": "player_position",
                        "slot": slot,
                        "x": player_state["x"],
                        "y": player_state["y"],
                        "z": player_state["z"],
                        "yaw": player_state["yaw"],
                        "pitch": player_state["pitch"],
                    }, exclude_slot=slot)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        del players[slot]
        print(f"Giocatore disconnesso da slot {slot}")
        await send_all({"type": "player_disconnected", "slot": slot})
