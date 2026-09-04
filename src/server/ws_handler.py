"""WebSocket client handler and session setup.

This module owns the per-client lifecycle and the Vosk recognizer state.
"""

import asyncio
import json
import time

import websockets
from vosk import KaldiRecognizer

from .combat import try_spell
from .config import MAX_HP, SAMPLE_RATE, SPELLS_LIST, effective_cooldown_ms, players
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
    last_partial_sent = None

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
        "spell_cooldowns_ms": {word: effective_cooldown_ms(word) for word in SPELLS_LIST},
        "spell_cooldowns_seconds": {word: effective_cooldown_ms(word) / 1000 for word in SPELLS_LIST},
        "server_time_ms": int(time.time() * 1000),
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
                    # Final transcription is intentionally ignored: spells must only
                    # trigger from partial results, never from delayed final audio.
                    rec.Result()
                    detected_in_utterance.clear()
                    if last_partial_sent:
                        last_partial_sent = None
                        asyncio.create_task(send_to(slot, {"type": "voice_partial", "text": ""}))
                else:
                    partial_text = json.loads(rec.PartialResult()).get("partial", "")
                    if partial_text != last_partial_sent:
                        last_partial_sent = partial_text
                        asyncio.create_task(send_to(slot, {"type": "voice_partial", "text": partial_text}))
                    # Partial text is cumulative. Only the newest unseen match
                    # may cast, preventing a backlog from firing all at once.
                    for match in reversed(find_spell_matches(partial_text)):
                        word = match.group(1).lower()
                        if word in detected_in_utterance:
                            continue
                        detected_in_utterance.add(word)
                        asyncio.create_task(try_spell(slot, word))
                        break

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

                elif data.get("type") == "voice_end":
                    # Start the next phrase with a fresh Vosk context; otherwise
                    # old partial words can reappear on the next sound.
                    player_state = players[slot]
                    player_state["recognizer"].Reset()
                    detected_in_utterance.clear()
                    last_partial_sent = None
                    asyncio.create_task(send_to(slot, {"type": "voice_partial", "text": ""}))

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
