"""
Fase 5 - Server multiplayer con posizione in prima persona
Rispetto alla Fase 4, il server ora tiene traccia anche di x/z/yaw di ogni
giocatore (non solo slot e incantesimi) e la ritrasmette agli altri client,
cosi' possono disegnare il modello del mago nel punto giusto della mappa.

Uso:
    pip install vosk websockets
    python server.py
"""

import asyncio
import json
import re
import ssl
import time
import math
import websockets
from vosk import Model, KaldiRecognizer

# ===== CONFIGURAZIONE SERVER =====
CERT_FILE = "C:/xampp/apache/conf/ssl-custom/192.168.1.170+2.pem"
KEY_FILE = "C:/xampp/apache/conf/ssl-custom/192.168.1.170+2-key.pem"

SERVER_ADDRESS = '0.0.0.0'
SERVER_PORT = 8765

# ===== CONFIGURAZIONE MODELLO =====
SPELLS_LIST = ["fulmine", "scudo", "fuoco"]  # Lista di incantesimi da riconoscere
MODEL_PATH = "model"
SAMPLE_RATE = 16000  # Frequenza di campionamento standard per i modelli Vosk

# ===== CONFIGURAZIONE GIOCO =====
MAX_PLAYERS = 5
COOLDOWN_MS = 1800
SPAWN_RADIUS = 3.0  # raggio del cerchio usato per posizionare i giocatori all'ingresso
players = {}

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
    """Posizione iniziale su un cerchio, cosi' i giocatori non nascono impilati
    uno sopra l'altro all'origine della mappa."""
    angle = (slot / MAX_PLAYERS) * math.pi * 2
    return math.cos(angle) * SPAWN_RADIUS, math.sin(angle) * SPAWN_RADIUS


# ===== GESTIONE LANCIO INCANTESIMI =====
async def try_spell(slot, word):
    # Applica il cooldown lato server prima di confermare l'incantesimo a tutti.
    player_state = players.get(slot)
    if player_state is None:
        return
    now = time.monotonic() * 1000
    last_cast = player_state["last_cast"].get(word, 0.0)
    if now - last_cast < COOLDOWN_MS:
        return  # ancora in cooldown: il server ignora silenziosamente
    player_state["last_cast"][word] = now
    await send_all({"type": "spell", "slot": slot, "word": word})


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
    spawn_x, spawn_z = spawn_position(slot)
    players[slot] = {
        "websocket": websocket,
        "recognizer": recognizer,
        "last_recognized": None,
        "last_cast": {word: 0.0 for word in SPELLS_LIST},
        "x": spawn_x,
        "z": spawn_z,
        "yaw": 0.0,
    }

    print(f"Giocatore connesso su slot {slot} ({websocket.remote_address})")

    # Al nuovo giocatore: il suo slot, la posizione di partenza, e chi c'e' gia' (con la sua posizione)
    existing_players = [
        {"slot": s, "x": p["x"], "z": p["z"], "yaw": p["yaw"]}
        for s, p in players.items() if s != slot
    ]
    await websocket.send(json.dumps({
        "type": "welcome",
        "your_slot": slot,
        "spawn_x": spawn_x,
        "spawn_z": spawn_z,
        "players": existing_players,
    }))

    # Agli altri: notifica che si è unito un nuovo giocatore, con la sua posizione iniziale
    await send_all({
        "type": "player_connected",
        "slot": slot,
        "x": spawn_x,
        "z": spawn_z,
        "yaw": 0.0,
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
                    player_state["z"] = data.get("z", player_state["z"])
                    player_state["yaw"] = data.get("yaw", player_state["yaw"])
                    await send_all({
                        "type": "player_position",
                        "slot": slot,
                        "x": player_state["x"],
                        "z": player_state["z"],
                        "yaw": player_state["yaw"],
                    }, exclude_slot=slot)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        del players[slot]
        print(f"Giocatore disconnesso da slot {slot}")
        await send_all({"type": "player_disconnected", "slot": slot})


async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)

    async with websockets.serve(handle_client, SERVER_ADDRESS, SERVER_PORT, ssl=ssl_context):
        print(f"server vocale in ascolto su wss://{SERVER_ADDRESS}:{SERVER_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())