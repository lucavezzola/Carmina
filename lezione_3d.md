# Come funziona il tuo gioco: GUI, 3D e collisioni

Questa lezione spiega i concetti dietro al codice che abbiamo scritto finora, in modo che tu possa leggerlo, modificarlo, e aggiungere cose nuove (attacchi, danni, collisioni migliori) senza dover copiare/incollare alla cieca.

---

## 1. La GUI: due mondi separati che si sovrappongono

Nella pagina convivono **due sistemi di rendering completamente diversi**, sovrapposti visivamente:

1. Un `<canvas>` a schermo intero, dentro cui **Three.js** disegna il mondo 3D (mappa, maghi, effetti).
2. Elementi HTML normali (`<div>`) posizionati sopra, con CSS, per la parte di interfaccia — barre di cooldown, il mirino, i messaggi di stato.

Il canvas non sa nulla dell'HTML sopra di lui, e viceversa: sono due livelli indipendenti. Il trucco che li tiene insieme è nel CSS:

```css
canvas#scene { position: fixed; inset: 0; }   /* riempie tutto lo schermo, sotto */
#hud { position: fixed; top: 24px; left: 24px; pointer-events: none; }  /* sopra, ma "trasparente" ai click */
```

`position: fixed` fa sì che l'elemento sia posizionato rispetto alla finestra del browser, non rispetto al resto della pagina — necessario per sovrapporre le cose con precisione. `pointer-events: none` è quello che ti permette di cliccare "attraverso" un elemento HTML e raggiungere il canvas sotto (altrimenti il div dell'HUD bloccherebbe ogni click, anche se è trasparente).

**Perché questo conta per te**: se vuoi aggiungere una barra della salute, un inventario, un messaggio "sei morto" — sono tutti `<div>` HTML normali, non hanno niente a che fare con Three.js. Li aggiorni con `element.style.qualcosa = ...` o `element.textContent = ...` dentro al loop di animazione, esattamente come già fa `updateCooldownBars()`.

---

## 2. Il mondo 3D: scena, camera, renderer

Ogni programma Three.js ha sempre questi tre pezzi:

```js
const scene = new THREE.Scene();               // il "contenitore" di tutto ciò che esiste
const camera = new THREE.PerspectiveCamera(...); // il punto di vista da cui guardiamo la scena
const renderer = new THREE.WebGLRenderer({canvas}); // quello che disegna davvero i pixel
```

- **`scene`** è solo un albero di oggetti (mesh, luci, gruppi) — non fa nulla da sola, è un contenitore.
- **`camera`** ha una posizione e una direzione nello spazio 3D. `PerspectiveCamera(fov, aspect, near, far)`: `fov` è il campo visivo in gradi (quanto è "largo" lo sguardo), `near`/`far` sono le distanze minima e massima oltre le quali le cose non vengono disegnate (per risparmiare calcoli).
- **`renderer.render(scene, camera)`** è la riga che effettivamente calcola "cosa si vede dalla camera, dentro la scena" e lo disegna sul canvas. Va chiamata **ad ogni frame** — se non la richiami, lo schermo resta fermo all'ultima immagine disegnata.

---

## 3. Cos'è una Mesh

Una **mesh** è un oggetto visibile nella scena, fatto di due parti separate:

- **Geometria**: la *forma* — un elenco di vertici e triangoli. `THREE.SphereGeometry(raggio, ...)`, `THREE.ConeGeometry(raggio, altezza, ...)`, `THREE.BoxGeometry(largo, alto, profondo)`, `THREE.CylinderGeometry(raggioAlto, raggioBasso, altezza, ...)` — sono tutte fabbriche di forme già pronte, non devi disegnare i triangoli a mano.
- **Materiale**: l'*aspetto* — colore, se riflette la luce, se è trasparente. `MeshStandardMaterial` reagisce alle luci della scena (ombreggiature realistiche); `MeshBasicMaterial` è "piatto", non reagisce alla luce (usato per il wireframe e per gli scudi semi-trasparenti, dove non ci serve un'ombreggiatura realistica).

```js
const geometry = new THREE.SphereGeometry(0.5, 16, 16); // raggio 0.5, 16 segmenti orizzontali e verticali
const material = new THREE.MeshStandardMaterial({ color: 0x6b3fa0 });
const mesh = new THREE.Mesh(geometry, material); // la mesh vera e propria
scene.add(mesh); // senza questa riga, la mesh esiste ma non è visibile
```

La stessa geometria o lo stesso materiale possono essere riutilizzati su più mesh — nel tuo codice però creiamo geometrie/materiali nuovi per ogni mago per poter cambiare il colore di ognuno indipendentemente (`bodyMaterial` per slot).

---

## 4. Object3D: la classe madre di tutto

`Mesh`, `Group`, `Camera`, e le luci **condividono tutti** una classe base: `Object3D`. Questo significa che *tutti* hanno:

- `.position` (un `Vector3`: `.x`, `.y`, `.z`)
- `.rotation` (angoli di Eulero: `.x`, `.y`, `.z`, in radianti)
- `.scale` (un moltiplicatore per ogni asse, di default `(1,1,1)`)
- `.children` (una lista di altri Object3D "agganciati" a lui)

Un **`Group`** è un Object3D che non ha una forma propria — serve solo a raggruppare altri oggetti perché si muovano insieme:

```js
function createWizard(color) {
  const group = new THREE.Group();
  const body = new THREE.Mesh(sphereGeometry, bodyMaterial);
  const hat = new THREE.Mesh(coneGeometry, hatMaterial);
  group.add(body);
  group.add(hat);
  return group; // sposti group.position, e sfera+cono si muovono insieme
}
```

### Gerarchia: posizione locale vs. posizione nel mondo

Quando un oggetto è figlio di un altro (`parent.add(child)`), la sua `.position` è **relativa al genitore**, non alle coordinate assolute della scena. Questo è esattamente il trucco dietro allo scudo nel tuo codice:

```js
anchor.add(shieldMesh); // shieldMesh diventa figlio dell'ancora del giocatore
```

Da questo momento, se il giocatore si muove, lo scudo lo segue **automaticamente** — non devi aggiornare la sua posizione ogni frame, perché la sua posizione è sempre "un po' più in alto rispetto al genitore", qualunque cosa faccia il genitore. Quando invece ti serve sapere *dove si trova davvero* un oggetto nello spazio della scena (per esempio per far partire le particelle di un incantesimo), usi:

```js
anchor.getWorldPosition(worldPosition); // converte la posizione locale in coordinate assolute
```

---

## 5. Il loop di animazione

Un gioco non disegna un solo fotogramma: ne disegna decine al secondo, ognuno leggermente diverso. Il meccanismo è:

```js
function animate() {
  requestAnimationFrame(animate); // "richiamami di nuovo appena il browser è pronto per il prossimo frame"
  // ...aggiorna posizioni, controlla input, ecc...
  renderer.render(scene, camera);
}
animate(); // avvia il ciclo una prima volta
```

`requestAnimationFrame` chiama la funzione passata subito prima che il browser ridisegni lo schermo — di solito ~60 volte al secondo, ma varia in base al monitor e al carico della macchina. **Proprio perché non è un tempo fisso**, ogni movimento deve essere moltiplicato per `delta` (il tempo trascorso dall'ultimo frame), altrimenti su un PC più lento il personaggio si muoverebbe più lentamente in termini assoluti:

```js
const delta = (now - lastFrameTime) / 1000; // secondi trascorsi dall'ultimo frame
camera.position.x += velocity * delta; // "velocity" è in unità al SECONDO, non per frame
```

---

## 6. La rete: chi decide cosa è "vero"

Il tuo client e il server si scambiano due tipi di messaggi sullo stesso WebSocket:

- **Binari** → audio del microfono (dal client al server soltanto)
- **Testo JSON** → tutto il resto: posizione, incantesimi, ingresso/uscita giocatori

Il punto concettuale più importante: **il client non decide mai da solo se qualcosa "è successo"**. Quando pronunci un incantesimo, il client manda solo l'audio; è il server che lo riconosce, controlla il cooldown, e trasmette l'evento a tutti (compreso te). Il client si limita a *reagire* a quello che il server conferma. Questo evita che due giocatori vedano stati diversi, o che un client modificato possa "barare".

### Perché serve interpolare gli altri giocatori

Il server manda la tua posizione agli altri circa 10 volte al secondo (non ad ogni frame, per non intasare la rete). Se un client remoto scattasse istantaneamente all'ultima posizione ricevuta, il movimento sembrerebbe a scatti. La soluzione è l'**interpolazione**: ad ogni frame (quindi ~60 volte al secondo) il client si avvicina un po' di più alla posizione bersaglio, invece di teletrasportarcisi:

```js
player.group.position.x += (player.targetX - player.group.position.x) * REMOTE_LERP_FACTOR;
```

Questa riga dice: "copri una frazione (`REMOTE_LERP_FACTOR`, es. 0.18) della distanza rimanente, ogni frame". Il risultato è un movimento morbido che rincorre sempre la posizione vera senza scatti — a costo di un piccolo ritardo percepito, invisibile in LAN.

---

## 7. Collisioni: perché il cerchio non basta

Finora tratti ogni ostacolo come un cerchio (`{x, z, radius}`), e controlli solo la distanza dal centro. Funziona bene per gli alberi (sono rotondi), ma è **sbagliato per gli edifici**: un cerchio che contiene un cubo o è troppo grande (blocchi spazio vuoto vicino agli angoli) o è troppo piccolo (il giocatore taglia l'angolo passandoci dentro). Serve una forma che rispecchi davvero il rettangolo.

### Bounding Box (AABB): la soluzione standard

Una **AABB** (Axis-Aligned Bounding Box, "scatola allineata agli assi") è definita da due punti: l'angolo minimo e l'angolo massimo lungo ogni asse. Three.js la rappresenta con `THREE.Box3`:

```js
const box = new THREE.Box3().setFromObject(buildingMesh); // calcolata automaticamente dalla mesh
// oppure a mano, se conosci già le dimensioni:
const box = new THREE.Box3(
  new THREE.Vector3(x - width/2, 0, z - depth/2),  // angolo minimo
  new THREE.Vector3(x + width/2, height, z + depth/2) // angolo massimo
);
```

Il test di collisione corretto contro un rettangolo (ignorando l'altezza, dato che ti muovi solo sul piano XZ) è:

1. Trova il **punto più vicino** al giocatore *dentro* il rettangolo, "bloccando" (clampando) le coordinate del giocatore dentro i limiti min/max del box.
2. Misura la distanza tra il giocatore e quel punto.
3. Se la distanza è minore del raggio del giocatore, sei in collisione — e la direzione per "spingerti fuori" è proprio quella dal punto più vicino verso di te.

```js
function resolveBoxCollision(playerX, playerZ, box, playerRadius) {
  const closestX = Math.max(box.min.x, Math.min(playerX, box.max.x));
  const closestZ = Math.max(box.min.z, Math.min(playerZ, box.max.z));
  const dx = playerX - closestX;
  const dz = playerZ - closestZ;
  const distance = Math.hypot(dx, dz);
  if (distance < playerRadius && distance > 0.0001) {
    const factor = playerRadius / distance;
    return { x: closestX + dx * factor, z: closestZ + dz * factor };
  }
  return null; // nessuna collisione
}
```

Questo gestisce correttamente gli angoli: se ti avvicini di lato a un edificio vieni spinto lateralmente, se ti avvicini in diagonale verso uno spigolo vieni spinto in diagonale — cosa che un cerchio non può fare.

**Cosa cambierebbe nel tuo codice**: nella lista `obstacles`, invece di `{x, z, radius}` per gli edifici salveresti `{x, z, halfWidth, halfDepth}` (o direttamente un `THREE.Box3`), e in `resolveCollisions()` useresti il test sopra per quelli, mantenendo il vecchio test a cerchio solo per gli alberi.

**Un limite che resta**: questo funziona per edifici allineati agli assi (non ruotati). Se in futuro vuoi edifici ruotati a piacere, serve una **OBB** (Oriented Bounding Box — stessa idea, ma il test avviene nel sistema di riferimento ruotato dell'edificio) — più complesso, da affrontare solo se ti serve davvero.

---

## 8. Verso attacchi e danni: come impostare il ragionamento

Non lo implemento qui, ma ti do la struttura concettuale per farlo tu (o insieme, la prossima volta):

1. **La salute vive sul server**, non sul client — stesso principio del cooldown: se decidesse il client, un giocatore modificato potrebbe dichiararsi immortale. Il server tiene `player_state["health"]`, e lo manda giù ad ogni cambiamento.
2. **Rilevare il colpo**: per un incantesimo "a distanza" come il fulmine, ti serve sapere *chi* stava colpendo il lanciatore. Due strade comuni:
   - **Raggio/cono davanti a chi lancia**: controlli la distanza e l'angolo tra il lanciatore e ogni altro giocatore, e consideri "colpito" chiunque sia abbastanza vicino e davanti.
   - **Raycasting**: `THREE.Raycaster` spara un raggio invisibile da un punto in una direzione e ti dice quale mesh incontra per primo — più preciso, utile se vuoi puntare con la mira invece che colpire "chiunque sia vicino".
3. **Applicare il danno**: il server scala la salute del bersaglio e trasmette `{"type": "damage", "slot": bersaglio, "health": nuova_salute}`. Il client aggiorna la barra della salute (un altro `<div>` HTML, come il cooldown) e magari fa lampeggiare di rosso il modello colpito.
4. **Morte/respawn**: quando la salute arriva a 0, decide sempre il server — manda un evento tipo `{"type": "player_down", "slot": ...}`, e dopo qualche secondo un nuovo `spawn_position()` per farlo rientrare in gioco.

---

## Glossario rapido: concetto → dove lo trovi nel tuo codice

| Concetto | Nel tuo codice |
|---|---|
| Scena | `scene` |
| Camera (il tuo punto di vista) | `camera`, mossa da `PointerLockControls` |
| Renderer | `renderer.render(scene, camera)` dentro `animate()` |
| Mesh (forma + materiale) | `body`, `hat`, `ground`, `bolt` |
| Gruppo (oggetti che si muovono insieme) | `createWizard()`, il `group` di ogni mago |
| Gerarchia genitore-figlio | `anchor.add(shieldMesh)` |
| Loop di gioco | `animate()` + `requestAnimationFrame` |
| Tempo indipendente dal framerate | `delta` |
| Rete: il server è la fonte di verità | `try_spell()` nel server, mai deciso dal client |
| Interpolazione dei giocatori remoti | `REMOTE_LERP_FACTOR` in `animate()` |
| Collisione (attuale, a cerchio) | `resolveCollisions()` |
| Collisione da migliorare (AABB) | sezione 7 di questa lezione |

---

Quando hai letto e digerito questo, i prossimi passi naturali sono: convertire gli edifici in AABB per collisioni corrette, e poi iniziare a costruire salute/danno lato server. Fammi sapere da dove vuoi ripartire.
