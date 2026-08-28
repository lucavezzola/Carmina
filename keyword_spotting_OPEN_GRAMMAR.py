import json
import os
import queue
import re
import sys

import sounddevice as sd
from vosk import KaldiRecognizer, Model


# ===== CONFIGURAZIONE =====
SPELLS_LIST = ["fulmine", "scudo", "palla di fuoco", "ghiaccio", "scambio", "salto"] # Lista di incantesimi da riconoscere
MODEL_PATH = "model"
SAMPLE_RATE = 16000 # Frequenza di campionamento standard per i modelli Vosk
BLOCK_SIZE = 8000 # Dimensione dei blocchi di audio analizzati


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

def main():
  print(f"PID processo: {os.getpid()}", flush=True)
  
  # ===== CARICAMENTO MODELLO =====
  print(f"Caricamento del modello italiano dalla cartella `{MODEL_PATH}` ...")
  
  try:
    model = Model(MODEL_PATH) # Caricamento del modello Vosk
  except Exception as e:
    print(f"Caricamento del modello fallito. Inserire un modello valido in `{MODEL_PATH}` e riprovare.")
  
  # ===== CREAZIONE DEL RICONOSCITORE VINCOLATO =====
  recognizer = KaldiRecognizer(model, SAMPLE_RATE)
  
  print(f"Parole riconosciute: {', '.join(SPELLS_LIST)}")
  print("Pronuncia una parola alla volta. Ctrl+C per uscire.\n")
  
  # ===== CREAZIONE CODA BLOCCHI AUDIO DA MICROFONO =====
  audio_queue = queue.Queue() # Coda per passare i blocchi dal thread del mic al ciclo principale
  emitted_spell_count = 0 # Numero di incantesimi gia mostrati nel risultato parziale
  partial_checked_until = 0 # Posizione del risultato parziale gia controllata
  max_spell_length = max(map(len, SPELLS_LIST)) # Lunghezza massima degli incantesimi

  # ===== CALLBACK AUDIO =====
  def callback(indata, frames, time_info, status):
    if status:
      print(f"[avviso audio] {status}", file=sys.stderr)
    audio_queue.put(bytes(indata)) # Inserisce il blocco audio nella coda
  
  # ===== APERTURA STREAM AUDIO E CICLO DI RICONOSCIMENTO =====
  try:
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype="int16", channels=1, callback=callback) as stream:
      print(f"Sample rate effettivo dello stream: {stream.samplerate}")
      
      while True:
        data = audio_queue.get()
        
        if recognizer.AcceptWaveform(data):
          result = json.loads(recognizer.Result())
          text = result.get("text", "").strip() # Testo definitivo dopo la pausa
          final_spells = find_spells(text)
          # Mostra solo gli incantesimi non gia stampati durante il riconoscimento parziale
          print(f"Blocco di testo completo: {text}")
          # for spell in final_spells[emitted_spell_count:]:
          #   print(f">> Riconosciuto: {spell}")
          emitted_spell_count = 0 # Azzera il conteggio per la frase successiva
          partial_checked_until = 0 # Azzera la posizione per la frase successiva
        
        else:
          # Il risultato parziale permette di riconoscere gli incantesimi senza aspettare la pausa
          partial = json.loads(recognizer.PartialResult()).get("partial", "").strip()
          # Controlla solo la parte nuova del risultato parziale
          if len(partial) < partial_checked_until:
            partial_checked_until = 0
          # Mantiene una sovrapposizione per gli incantesimi composti
          scan_from = max(0, partial_checked_until - max_spell_length + 1)
          new_partial = partial[scan_from:]
          partial_matches = find_spell_matches(new_partial)
          for match in partial_matches:
            if scan_from + match.end() > partial_checked_until:
              print(f">> Riconosciuto: {match.group(1)}")
              emitted_spell_count += 1
          partial_checked_until = len(partial)
  except KeyboardInterrupt:
    print("\nUscita.")
  except Exception as e:
    print(f"ERRORE durante l'ascolto del microfono: {e}")
    print("Controlla che il microfono sia collegato e che 'sounddevice'")
    print("sia riuscito a rilevare un dispositivo di input valido.")
    print("Puoi elencare i dispositivi disponibili con:")
    print("    python -c \"import sounddevice; print(sounddevice.query_devices())\"")
    sys.exit(1)
    
if __name__ == "__main__":
  main()