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

import websockets
from vosk import Model

from src.server.config import (
    SERVER_ADDRESS,
    SERVER_PORT,
    MODEL_PATH,
)
from src.server.world import load_or_generate_world_map as load_world_map
from src.server.ws_handler import handle_client

# ===== CONFIGURAZIONE SERVER =====
# Phase 1 bootstrap: keep runtime behavior stable while delegating the shared
# constants and world logic to the new package structure.

# ===== CONFIGURAZIONE MODELLO =====
# Moved to src/server/config.py.

# ===== CONFIGURAZIONE GIOCO =====
# Moved to src/server/config.py.

# ===== CREAZIONE MAPPA DI GIOCO =====
# Moved to src/server/world.py and kept as a shared world-state dependency.
WORLD_MAP = load_world_map()

# ===== CARICAMENTO MODELLO =====
print(f"Caricamento del modello italiano dalla cartella `{MODEL_PATH}` ...")

try:
    model = Model(MODEL_PATH)  # Caricamento del modello Vosk
except Exception:
    print(f"Caricamento del modello fallito. Inserire un modello valido in `{MODEL_PATH}` e riprovare.")
    exit()  # nota: "exit" da solo (senza parentesi) NON termina il programma, serve chiamarlo


# ===== RICERCA INCANTESIMI =====
# Moved to src/server/voice.py.

async def main():
    """Start the WebSocket server and keep it alive for connected clients."""
    async with websockets.serve(lambda ws: handle_client(ws, model, WORLD_MAP), SERVER_ADDRESS, SERVER_PORT):
        print(f"server vocale in ascolto su wss://{SERVER_ADDRESS}:{SERVER_PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())