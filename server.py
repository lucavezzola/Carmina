"""
Fase 5 - Server multiplayer con posizione in prima persona
Rispetto alla Fase 4, il server ora tiene traccia anche di x/y/z/yaw di ogni
giocatore (non solo slot e incantesimi) e la ritrasmette agli altri client,
cosi' possono disegnare il modello del mago nel punto giusto della mappa.

Uso:
    pip install vosk websockets
    python server.py
"""

import asyncio
import json
import random
import re
import os
import time
import math
import websockets
from vosk import Model, KaldiRecognizer

# ===== CONFIGURAZIONE SERVER =====
SERVER_ADDRESS = '0.0.0.0'
SERVER_PORT = 8765

# ===== CONFIGURAZIONE MODELLO =====
SPELLS_LIST = ["fulmine", "scudo", "fuoco"]  # Lista di incantesimi da riconoscere
MODEL_PATH = "model"
SAMPLE_RATE = 16000  # Frequenza di campionamento standard per i modelli Vosk

# ===== CONFIGURAZIONE GIOCO =====
MAX_PLAYERS = 5
SPELLS_COOLDOWNS = {"fulmine": 18000, "scudo": 3000, "fuoco": 7000}
SPAWN_RADIUS = 3.0  # raggio del cerchio usato per posizionare i giocatori all'ingresso
EYE_HEIGHT = 1.7
players = {}

# ===== CREAZIONE MAPPA DI GIOCO =====
# Generata UNA SOLA VOLTA all'avvio del server: ogni client riceve esattamente
# questa lista, così l'aspetto della mappa è identico per tutti, invece che
# generato a caso in modo indipendente su ogni browser.
TERRAIN_SIZE = 100.0      # copre da -50 a +50 su entrambi gli assi
TERRAIN_RESOLUTION = 33   # punti campionati per lato (32 segmenti di griglia)
WORLD_MAP_PATH = "world_map.json"


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

    # un fiume: una curva sinuosa lungo z, che scava una valle stretta nel terreno
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
                h -= river_depth * (1 - t)  # più vicino al centro del fiume, più scaviamo

            row.append(round(h, 3))
        heights.append(row)
    return heights


def terrain_height_at(heights, x, z):
    """Interpolazione bilineare - DEVE restare identica alla versione client
    (terrainHeightAt in JS), altrimenti alberi/edifici non combaciano col
    terreno disegnato."""
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
            "type": "building", "x": x, "y": y, "z": z,
            "width": width, "height": height, "depth": depth, "color": color,
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

WORLD_MAP = load_or_generate_world_map()

# ===== CARICAMENTO MODELLO =====
print(f"Caricamento del modello italiano dalla cartella `{MODEL_PATH}` ...")

try:
    model = Model(MODEL_PATH)  # Caricamento del modello Vosk
except Exception:
    print(f"Caricamento del modello fallito. Inserire un modello valido in `{MODEL_PATH}` e riprovare.")
    exit()  # nota: "exit" da solo (senza parentesi) NON termina il programma, serve chiamarlo


# ===== RICERCA INCANTESIMI =====
def find_spells(text):
    # Gli incantesimi composti vengono cercati prima di quelli più brevi
    spell_pattern = "|".join(
        re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True)
    )
    # I confini di parola evitano di riconoscere un incantesimo dentro un'altra parola
    return re.findall(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower())


def find_spell_matches(text):
    # Restituisce anche la posizione, utile per saltare il testo gia' controllato
    spell_pattern = "|".join(
        re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True)
    )
    return list(re.finditer(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower()))


# ===== GESTIONE LOBBY =====
def free_slot():
    for i in range(MAX_PLAYERS):
        if i not in players:
            return i
    return None


def spawn_position(slot):
    angle = (slot / MAX_PLAYERS) * math.pi * 2
    x = math.cos(angle) * SPAWN_RADIUS
    z = math.sin(angle) * SPAWN_RADIUS
    y = terrain_height_at(WORLD_MAP["terrain"]["heights"], x, z) + EYE_HEIGHT
    return x, y, z

# ===== GESTIONE LANCIO INCANTESIMI =====
MAX_HP = 100
RESPAWN_DELAY_S = 3.0

LIGHTNING_RANGE = 20.0
LIGHTNING_RADIUS = 0.6
LIGHTNING_DAMAGE = 25

FIRE_DEPTH = 5.0
FIRE_RADIUS_NEAR = 0.5   # larghezza del cono vicino al lanciatore
FIRE_RADIUS_FAR = 2.5    # larghezza del cono a fine profondità
FIRE_DURATION_S = 5.0
FIRE_TICK_INTERVAL_S = 1.0   # un tick di danno ogni secondo
FIRE_TICK_DAMAGE = 6         # danno per tick (5 tick totali ≈ 30 danno se resti dentro tutto il tempo)

SHIELD_DURATION_MS = 2400  # combacia con la durata visiva dello scudo nel client

def effective_cooldown_ms(word):
    if word == "fuoco":
        return FIRE_DURATION_S * 1000 + SPELLS_COOLDOWNS["fuoco"]
    return SPELLS_COOLDOWNS[word]

def forward_vector(yaw, pitch):
    """Vettore 3D unitario nella direzione in cui il giocatore guarda,
    combinando rotazione orizzontale (yaw) e verticale (pitch).
    Stessa convenzione della camera Three.js con ordine di rotazione 'YXZ':
    pitch positivo = guardi in alto, yaw applicato dopo il pitch."""
    fx = -math.cos(pitch) * math.sin(yaw)
    fy = math.sin(pitch)
    fz = -math.cos(pitch) * math.cos(yaw)
    return (fx, fy, fz)

def projected_position(caster_slot, target_slot):
    """Restituisce (avanti, lato) del bersaglio rispetto al lanciatore,
    proiettati sulla sua direzione di mira 3D (yaw + pitch)."""
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
    lato = math.sqrt(lateral_dx**2 + lateral_dy**2 + lateral_dz**2)

    return avanti, lato


def find_lightning_target(caster_slot):
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

def projected_from_origin(origin, forward, target_slot):
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
    lato = math.sqrt(lateral_dx**2 + lateral_dy**2 + lateral_dz**2)

    return avanti, lato

async def run_fire_effect(caster_slot, origin, forward):
    ticks = int(FIRE_DURATION_S / FIRE_TICK_INTERVAL_S)
    for i in range(ticks):
        targets = find_fire_targets_static(origin, forward, exclude_slot=caster_slot)
        for target_slot in targets:
            await apply_damage(target_slot, FIRE_TICK_DAMAGE)
        if i < ticks - 1:
            await asyncio.sleep(FIRE_TICK_INTERVAL_S)

def find_fire_targets_static(origin, forward, exclude_slot=None):
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
    player_state = players.get(slot)
    if player_state is None:
        return  # potrebbe essersi disconnesso nel frattempo

    now = time.monotonic() * 1000
    if player_state.get("shielded_until", 0) > now:
        amount = 0  # scudo attivo: annulla il danno in ingresso

    player_state["hp"] = max(0, player_state["hp"] - amount)
    await send_all({"type": "health_update", "slot": slot, "hp": player_state["hp"]})

    if player_state["hp"] <= 0:
        await send_all({"type": "player_down", "slot": slot})
        asyncio.create_task(respawn_after_delay(slot))


async def respawn_after_delay(slot):
    await asyncio.sleep(RESPAWN_DELAY_S)
    player_state = players.get(slot)
    if player_state is None:
        return  # si è disconnesso durante l'attesa

    x, y, z = spawn_position(slot)
    player_state["x"], player_state["y"], player_state["z"] = x, y, z
    player_state["hp"] = MAX_HP
    await send_all({
        "type": "player_respawn", "slot": slot,
        "x": x, "y": y, "z": z, "hp": MAX_HP,
    })

async def try_spell(slot, word):
    player_state = players.get(slot)
    if player_state is None:
        return
    now = time.monotonic() * 1000
    last_cast = player_state["last_cast"].get(word, 0.0)
    if now - last_cast < effective_cooldown_ms(word):
        return  # ancora in cooldown
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
        origin = (player_state["x"], player_state["y"], player_state["z"])
        forward = forward_vector(player_state["yaw"], player_state["pitch"])
        await send_all({
            "type": "spell", "slot": slot, "word": word,
            "origin": {"x": origin[0], "y": origin[1], "z": origin[2]},
            "yaw": player_state["yaw"], "pitch": player_state["pitch"],
            "duration": FIRE_DURATION_S,
        })
        asyncio.create_task(run_fire_effect(slot, origin, forward))
        return

# ===== GESTIONE EVENTI COLLETTIVI =====
async def send_all(message, exclude_slot=None):
    # Trasmette un messaggio JSON a tutti i giocatori connessi (di default anche
    # a chi ha generato l'evento: è il server che conferma cosa è 'vero').
    text = json.dumps(message)
    targets = [
        g["websocket"] for slot, g in players.items() if slot != exclude_slot
    ]
    if not targets:
        return
    await asyncio.gather(
        *(ws.send(text) for ws in targets), return_exceptions=True
    )


# ===== CLIENT HANDLER =====
async def handle_client(websocket):
    slot = free_slot()
    if slot is None:
        await websocket.send(json.dumps({"type": "full"}))
        await websocket.close()
        return

    emitted_spell_count = 0  # Numero di incantesimi gia' mostrati nel risultato parziale
    partial_checked_until = 0  # Posizione del risultato parziale gia' controllata
    max_spell_length = max(map(len, SPELLS_LIST))  # Lunghezza massima degli incantesimi

    print(f"Client connesso: {websocket.remote_address}")

    # Un recognizer dedicato per ogni client così i giocatori
    # non si influenzano a vicenda
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)
    spawn_x, spawn_y, spawn_z = spawn_position(slot)
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

    print(f"Giocatore connesso su slot {slot} ({websocket.remote_address})")

    # Al nuovo giocatore: il suo slot, la posizione di partenza, e chi c'e' gia' (con la sua posizione)
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
        "world_map": WORLD_MAP,
    }))

    # Agli altri: notifica che si è unito un nuovo giocatore, con la sua posizione iniziale
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
                # audio dal microfono -> riconoscimento vocale (logica invariata)
                player_state = players[slot]
                rec = player_state["recognizer"]

                if rec.AcceptWaveform(message):
                    # Se una parola è stata riconosciuta come una delle spells alla fine
                    # è perchè è una trascrizione più accurata. Però potrebbe venire dopo
                    # qualche secondo, quindi non è accettabile perchè potrebbe anche
                    # causare latenze lunghe qualche secondo.

                    # Ritornerebbe il testo trascritto ma lo usiamo "a vuoto" per svuotare la trascrizione
                    rec.Result()

                    emitted_spell_count = 0  # Azzera il conteggio per la frase successiva
                    partial_checked_until = 0  # Azzera la posizione per la frase successiva

                    player_state["last_recognized"] = None

                else:
                    # Il risultato parziale permette di riconoscere gli incantesimi senza aspettare la pausa
                    partial_text = json.loads(rec.PartialResult()).get("partial", "").strip()
                    # Controlla solo la parte nuova del risultato parziale
                    if len(partial_text) < partial_checked_until:
                        partial_checked_until = 0
                    # Mantiene una sovrapposizione per gli incantesimi composti
                    scan_from = max(0, partial_checked_until - max_spell_length + 1)
                    new_partial = partial_text[scan_from:]
                    partial_matches = find_spell_matches(new_partial)
                    for match in partial_matches:
                        if scan_from + match.end() > partial_checked_until:
                            # Invia la parola riconosciuta al client
                            word = match.group(1)
                            await try_spell(slot, word)
                            player_state["last_recognized"] = word
                            emitted_spell_count += 1
                    partial_checked_until = len(partial_text)

            else:
                # Messaggio di controllo in JSON (per ora: aggiornamento di posizione)
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "position":
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


async def main():
    async with websockets.serve(handle_client, SERVER_ADDRESS, SERVER_PORT):
        print(f"server vocale in ascolto su wss://{SERVER_ADDRESS}:{SERVER_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())