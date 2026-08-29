"""
Fase 2 - Server vocale minimo
Riceve audio PCM raw (16-bit, 16kHz, mono) via WebSocket da un client browser,
lo passa a Vosk in streaming, e rimanda indietro la parola riconosciuta
appena viene individuato uno degli incantesimi nella lista.

Uso:
    (pip install vosk websockets)
    python server.py
 
Prerequisiti:
    - Il modello italiano Vosk scaricato e scompattato in una cartella
      (es. vosk-model-small-it-0.22), path da impostare in MODEL_PATH.
      Usa lo stesso modello che già funziona mello script di Fase 1.
"""

import asyncio
import json
import websockets
from vosk import Model, KaldiRecognizer

import re


# ===== CONFIGURAZIONE =====
SPELLS_LIST = ["fulmine", "scudo", "fuoco"] # Lista di incantesimi da riconoscere
MODEL_PATH = "model"
SAMPLE_RATE = 16000 # Frequenza di campionamento standard per i modelli Vosk

# ===== CARICAMENTO MODELLO =====
print(f"Caricamento del modello italiano dalla cartella `{MODEL_PATH}` ...")

try:
  model = Model(MODEL_PATH) # Caricamento del modello Vosk
except Exception as e:
  print(f"Caricamento del modello fallito. Inserire un modello valido in `{MODEL_PATH}` e riprovare.")


# ===== RICERCA INCANTESIMI =====
def find_spells(text):
  # Gli incantesimi composti vengono cercati prima di quelli più brevi
  spell_pattern = "|".join(
    re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True)
  )
  # I confini di parola evitano di riconoscere un incantesimo dentro un'altra parola
  return re.findall(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower())


def find_spell_matches(text):
  # Restituisce anche la posizione, utile per saltare il testo gia controllato
  spell_pattern = "|".join(
    re.escape(spell) for spell in sorted(SPELLS_LIST, key=len, reverse=True)
  )
  return list(re.finditer(rf"(?<!\w)({spell_pattern})(?!\w)", text.lower()))

async def handle_client(websocket):
  emitted_spell_count = 0 # Numero di incantesimi gia mostrati nel risultato parziale
  partial_checked_until = 0 # Posizione del risultato parziale gia controllata
  max_spell_length = max(map(len, SPELLS_LIST)) # Lunghezza massima degli incantesimi

  
  print(f"Client connesso: {websocket.remote_address}")
  
  # Un recognizer dedicato per ogni client così i giocatori
  # non si influenzano a vicenda
  
  recognizer = KaldiRecognizer(model, SAMPLE_RATE)
  
  try:
    async for message in websocket:
      if not isinstance(message, (bytes, bytearray)):
        # Ignora eventuali messaggi di testo (es. ping futuri)
        continue
      
      if recognizer.AcceptWaveform(message):
        # Se una parola è stata riconosciuta come una delle spells alla fine
        # è perchè è una trascrizione più accurata. Però potrebbe venire dopo
        # qualche secondo, quindi non è accettabile perchè potrebbe anche
        # causare latenze lunghe qualche secondo.
        
        # Ritornerebbe il testo trascritto ma lo usiamo "a vuoto" per svuotare la trascrizione
        recognizer.Result()
        
        emitted_spell_count = 0 # Azzera il conteggio per la frase successiva
        partial_checked_until = 0 # Azzera la posizione per la frase successiva
      
      else:
        # Il risultato parziale permette di riconoscere gli incantesimi senza aspettare la pausa
        partial_text = json.loads(recognizer.PartialResult()).get("partial", "").strip()
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
            await websocket.send(json.dumps({"word": match.group(1)}))
            emitted_spell_count += 1
        partial_checked_until = len(partial_text)
      
  except websockets.exceptions.ConnectionClosed:
    pass
  finally:
    print(f"Client disconnesso: {websocket.remote_address}")   


async def main():  
  async with websockets.serve(handle_client, "0.0.0.0", 8765):
    print("server vocale in ascolto su ws://0.0.0.0:8765")
    await asyncio.Future() # Resta in esecutzione per sempre

if __name__ == "__main__":
  asyncio.run(main())