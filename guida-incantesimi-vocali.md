# Guida: Gioco Multiplayer di Incantesimi Vocali

Guida di riferimento da consultare mano a mano che procedi. Non contiene codice — solo architettura, decisioni da prendere, e concetti/librerie da approfondire in ogni fase.

---

## 1. La decisione più importante: keyword spotting, non speech-to-text

Prima di tutto, un cambio di prospettiva rispetto alla conversazione precedente sul voice-to-text in italiano: **non ti serve trascrivere frasi libere**. Ti serve riconoscere un **set chiuso e piccolo di parole** (i nomi degli incantesimi — es. "fulmine", "scudo", "fuoco"). Questo è un problema molto più semplice, chiamato **keyword spotting** (o riconoscimento vocale a vocabolario vincolato), e cambia tutto a livello di fattibilità:

- È molto più leggero computazionalmente di uno speech-to-text generico.
- È più accurato e più tollerante al rumore, perché il motore non deve "indovinare" tra migliaia di parole possibili, solo tra le poche che gli hai detto essere valide.
- È più veloce (minore latenza), fondamentale per un gioco dove il feedback deve essere quasi istantaneo.

**Libreria consigliata: Vosk**, che supporta nativamente una modalità a "grammatica vincolata" — le passi una lista di parole/frasi ammesse, e lei ottimizza il riconoscimento solo su quelle. È open source, gira su CPU (niente GPU necessaria), ha un modello italiano piccolo (circa 40-50MB), ed è pensata per lo streaming in tempo reale.

Alternativa più specializzata se in futuro vorrai qualcosa di ancora più leggero e reattivo: **Porcupine** (di Picovoice) — un motore di *wake word / keyword detection* pensatissimo per riconoscere singole parole con latenza minima, ma con un vocabolario ancora più rigido (meno adatto se in futuro vuoi frasi come "scudo di ghiaccio" con variazioni).

Per iniziare, punta su **Vosk in modalità grammatica vincolata** — è il miglior compromesso tra semplicità di setup e flessibilità.

---

## 2. Fattibilità hardware: quale macchina usare

**PC vecchio (4GB RAM):** realisticamente sufficiente per **1-2 giocatori** in contemporanea con keyword spotting (grazie al modello piccolo e alla grammatica vincolata), ma con 5 giocatori che potenzialmente parlano in modo ravvicinato, rischi di saturare RAM/CPU sommando: 5 stream audio in elaborazione + il server di gioco (stato, sincronizzazione, networking) + il web server che serve i file statici. Usalo per **prototipare e testare con 1-2 giocatori**, non per l'hosting finale a 5.

**Laptop (RTX 3060H, i7-12650H, 16GB RAM):** qui hai margine comodo. Vosk non sfrutta la GPU (gira su CPU), ma con 16GB di RAM e un processore recente, 5 stream di keyword spotting in parallelo più il game server sono un carico ragionevole. La GPU ti tornerebbe utile solo se in futuro passassi a un motore basato su modelli più pesanti (es. Whisper accelerato via CUDA), ma per il keyword spotting non è necessaria. **Questa è la scelta pratica per l'hosting reale del gioco.**

**Cloud:** valutalo solo se vuoi che il gioco sia raggiungibile da internet (non solo dalla tua rete locale) o se in futuro vuoi scalare oltre 5 giocatori / passare a modelli più pesanti. Per iniziare non ti serve: tienilo come opzione di espansione, non come primo passo.

**Assunzione di partenza che ti consiglio:** sviluppa e testa tutto in **rete locale (LAN/Wi-Fi di casa)** prima. Aprire il gioco su internet richiede occuparti di NAT/port forwarding o un servizio di tunneling (es. Cloudflare Tunnel, ngrok) — un problema separato da risolvere solo dopo che il gioco funziona in locale.

---

## 3. Architettura generale

Tre componenti logicamente distinti, anche se potresti farli girare tutti sulla stessa macchina all'inizio:

1. **Client (browser di ogni giocatore)**: cattura audio dal microfono, lo invia al server vocale; riceve e mostra lo stato del gioco (posizioni, incantesimi lanciati, effetti).
2. **Server vocale**: riceve lo stream audio di ogni giocatore, esegue Vosk in modalità grammatica vincolata, e quando riconosce una parola-chiave, notifica il server di gioco "il giocatore X ha detto la parola Y".
3. **Server di gioco**: tiene lo stato autoritativo della partita (posizioni, salute, cooldown degli incantesimi), riceve gli eventi dal server vocale, applica la logica di gioco, e trasmette lo stato aggiornato a tutti i client.

Nota: server vocale e server di gioco possono benissimo essere lo **stesso processo** all'inizio (stessa macchina, stesso linguaggio) — separali logicamente nel codice, ma non serve che siano separati fisicamente finché non hai bisogno di scalare.

**Perché tenerli concettualmente separati fin da subito**: il riconoscimento vocale è un problema "a bassa frequenza" (poche parole al secondo, elaborazione pesante ma sporadica), mentre lo stato di gioco è "ad alta frequenza" (aggiornamenti di posizione magari 20-60 volte al secondo). Mischiarli nello stesso ciclo di elaborazione rischia di far "scattare" il gioco quando il riconoscimento vocale sta lavorando.

---

## 4. Stack tecnologico consigliato

- **Server**: Python (Vosk ha binding Python maturi e ben documentati) con **FastAPI** o semplicemente `websockets`/`asyncio` per gestire connessioni multiple in parallelo senza bloccarsi a vicenda.
- **Comunicazione client↔server**: **WebSocket** per entrambi i flussi (audio in streaming verso il server vocale, stato di gioco dal server di gioco verso i client) — a differenza di HTTP, un WebSocket resta aperto e permette comunicazione bidirezionale continua, essenziale sia per lo streaming audio continuo sia per gli aggiornamenti di gioco in tempo reale.
- **Cattura audio lato client**: `getUserMedia` (già lo conosci) + **`MediaRecorder`** (nuova API per te: cattura l'audio a "pezzi" — chunk temporali — pronti per essere inviati via rete, invece di doverli elaborare tu campione per campione).
- **Rendering del gioco lato client**: dato che il resto del tuo progetto è già HTML/CSS/JS puro, puoi continuare così — canvas 2D per una vista dall'alto semplice, o valutare una libreria leggera (es. Phaser) se vuoi sprite, animazioni e collisioni già pronte, evitando di reinventare un motore di gioco 2D da zero.

---

## 5. Roadmap di sviluppo, fase per fase

**Fase 0 — Definisci il gioco su carta prima di scrivere codice**
Quanti incantesimi? Che parole (in italiano, foneticamente ben distinte tra loro per ridurre confusione — es. evita parole troppo simili come "fuoco" e "fioco")? Che effetto ha ogni incantesimo (danno, scudo, movimento)? Quanto dura il cooldown? Definiscilo tutto per iscritto prima, così il resto delle fasi ha un bersaglio chiaro.

**Fase 1 — Keyword spotting da riga di comando, senza gioco e senza rete**
Installa Vosk in locale, scarica il modello italiano piccolo, e fai riconoscere una singola parola pronunciata da microfono, stampando a schermo il risultato. Nessun browser, nessuna rete — solo Python che ascolta il tuo microfono. Obiettivo: verificare che il riconoscimento funzioni bene con le parole che hai scelto, prima di costruirci sopra qualunque altra cosa.

**Fase 2 — Portalo online: un solo giocatore, browser → server**
Costruisci il collegamento minimo: il browser cattura l'audio col microfono e lo invia via WebSocket al tuo server Python, che lo passa a Vosk e rimanda indietro (sempre via WebSocket) la parola riconosciuta. Nessuna logica di gioco ancora — solo "dico una parola, la vedo apparire a schermo".

**Fase 3 — Stato di gioco minimo, ancora un solo giocatore**
Aggiungi un personaggio semplice sullo schermo (anche solo un cerchio su canvas) e collega il riconoscimento di una parola a un effetto visibile (es. dici "fuoco" → appare un lampo colorato). Qui costruisci il "cuore" della logica di gioco, ancora in single-player.

**Fase 4 — Multiplayer: due giocatori**
Estendi il server per gestire più connessioni WebSocket contemporaneamente, ognuna associata a un giocatore con il proprio stato (posizione, salute). Il server diventa la fonte di verità: riceve gli eventi vocali di ciascun giocatore, aggiorna lo stato, e trasmette il nuovo stato a **tutti** i client connessi (non solo a chi ha lanciato l'incantesimo).

**Fase 5 — Scala a 5 giocatori e testa le prestazioni**
Solo a questo punto testa con il numero reale di giocatori target, sul laptop più potente. Monitora CPU/RAM mentre tutti parlano contemporaneamente — è qui che scoprirai se serve ottimizzare (es. aggiungere rilevamento di attività vocale per non processare audio quando nessuno sta parlando, di cui al punto 6).

**Fase 6 — Rifinitura**: interfaccia, effetti visivi/sonori, bilanciamento del gioco, eventuale rete oltre la LAN.

---

## 6. Un'ottimizzazione importante: Voice Activity Detection (VAD)

Se ogni client invia continuamente audio al server (anche quando il giocatore sta zitto), sprechi banda e cicli di CPU per elaborare silenzio. Una tecnica semplice: implementa un **VAD** (rilevamento di attività vocale) **lato client**, usando esattamente l'RMS che hai già imparato a calcolare in questo progetto — se il volume supera una soglia, inizia a inviare audio al server; altrimenti non mandare nulla. Riduce drasticamente il carico sul server con 5 giocatori, e riusa una competenza che hai già.

---

## Altre idee per giochi/strumenti basati su audio e voce

Alcune ispirate a giochi esistenti, altre che riusano direttamente quello che hai già costruito in questo progetto (pitch detection, RMS, spettro):

- **Karaoke/pitch-matching**: il giocatore deve "cantare" una nota bersaglio; usi il tuo pitch detector già pronto per confrontare la frequenza cantata con quella richiesta e dare un punteggio di precisione (esattamente come fanno i giochi di karaoke con punteggio).
- **"Urla per saltare/correre"**: il volume (RMS) della voce controlla direttamente un parametro del gioco — più urli, più forte salta il personaggio, o più veloce corre. Semplicissimo da implementare con quello che hai già.
- **Simon Says vocale**: il gioco pronuncia (o mostra) una sequenza di parole-chiave, il giocatore deve ripeterle nell'ordine corretto entro un tempo limite — variante del keyword spotting che già stai costruendo, ma come gioco di memoria invece che d'azione.
- **Gioco a squadre "sussurra/urla"**: usa il volume per differenziare comandi — sussurrare attiva un'abilità stealth, urlare un'abilità d'attacco potente ma che "rivela la posizione" (rilevabile dagli altri giocatori).
- **Rhythm game basato su onset detection**: se in futuro implementi la beat/onset detection (il punto 6 del piano originale del tuo progetto di analisi audio), potresti costruire un gioco ritmico dove il giocatore deve battere le mani o dire una parola "a tempo" con una base musicale, sfruttando la rilevazione degli onset per giudicare la precisione del tempismo.
- **"Torre di Babele" cooperativo**: ogni giocatore vede istruzioni diverse ma deve comunicare vocalmente con gli altri per risolvere un puzzle condiviso — qui il riconoscimento vocale serve solo a registrare/trascrivere per un sistema di aiuti, non per comandi diretti.

---

## Prossimo passo consigliato

Parti dalla **Fase 1** (keyword spotting locale, Vosk da riga di comando, niente rete/browser) — è il test più veloce per validare che l'approccio funzioni bene con le parole italiane che sceglierai, prima di investire tempo nell'infrastruttura di rete e nel gioco vero e proprio.
