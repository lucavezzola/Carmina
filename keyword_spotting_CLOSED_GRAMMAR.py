import json
import queue
import sys
import time

import sounddevice as sd
from vosk import KaldiRecognizer, Model


# ===== CONFIGURAZIONE =====
SPELLS_LIST = ["fulmine", "scudo", "fuoco", "ghiaccio"] # Lista di incantesimi da riconoscere
MODEL_PATH = "model"
SAMPLE_RATE = 16000 # Frequenza di campionamento standard per i modelli Vosk
BLOCK_SIZE = 8000 # Dimensione dei blocchi di audio analizzati

def main():
  
  # ===== CARICAMENTO MODELLO =====
  print(f"Caricamento del modello italiano dalla cartella `{MODEL_PATH}` ...")
  
  try:
    model = Model(MODEL_PATH) # Caricamento del modello Vosk
  except Exception as e:
    print(f"Caricamento del modello fallito. Inserire un modello valido in `{MODEL_PATH}` e riprovare.")
  
  # ===== CREAZIONE DEL RICONOSCITORE VINCOLATO =====
  grammar = json.dumps(SPELLS_LIST + ["[unk]"]) # Lista JSON di vocaboli + "termine sconosciuto"
  recognizer = KaldiRecognizer(model, SAMPLE_RATE, grammar)
  recognizer.SetWords(True) # L'output tornerà anche il grado di confidenza del riconoscimento
  
  print(f"Parole riconosciute: {', '.join(SPELLS_LIST)}")
  print("Pronuncia una parola alla volta. Ctrl+C per uscire.\n")
  
  # ===== CREAZIONE CODA BLOCCHI AUDIO DA MICROFONO =====
  audio_queue = queue.Queue() # Coda per passare i blocchi dal thread del mic al ciclo principale
  def callback(indata, frames, time_info, status):
    if status:
      print(f"[avviso audio] {status}", file=sys.stderr)
    audio_queue.put(bytes(indata))
  
  # ===== APERTURA STREAM AUDIO E CICLO DI RICONOSCIMENTO =====
  try:
    timerStart = None
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype="int16", channels=1, callback=callback) as stream:
      print(f"Sample rate effettivo dello stream: {stream.samplerate}")
      
      while True:
        data = audio_queue.get()
        
        if timerStart is None:
          timerStart = time.perf_counter()
        
        if recognizer.AcceptWaveform(data):
          print(f"Durata: {time.perf_counter()-timerStart} s")
          
          result = json.loads(recognizer.Result())
          words = result.get("result", [])
          text = result.get("text", "").strip()
          if text and words:
            confidence = words[0]["conf"] # La confidenza maggiore tra le candidate
            if confidence >= 0.7: # Soglia di confidenza
              print(f">> Riconosciuto: {text} (conf: {confidence:.2f})")
            else:
              print(f"!% Scartato: {text} (conf: {confidence:.2f}))")
          
          timerStart = time.perf_counter()
        
        else:
          # Risultato parziale, utile per debug ma silenziato qui
          # per non riempire lo schermo. Decommenta se ti serve:
          # parziale = json.loads(recognizer.PartialResult())
          # print(f"... {parziale.get('partial', '')}", end="\r")
          pass
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