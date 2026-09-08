"Carmina" (plural of _carmen_), meaning songs, poems, verses or chants, but also incantations, oracles, or ritual formulas, is a work-in-progress speech activated spells game, similar in concept to Mage Arena.

How to run everything, including public Cloudflare quick tunnels:

  > python .\run.py

The command prints the public web link. It starts the game server on port 8765,
the browser client on port 8080, and updates the client's WebSocket URL when the
WebSocket tunnel is ready. Install `cloudflared` and make sure it is on PATH.

How to run map-editor server (from "world_editor" folder):
  > python -m http.server 8000

How to open servers to the internet:
- Python game server
  > cloudflared tunnel --url http://localhost:8765
- Change "WS_URL" in _index.html_ to the "http://" url given from the above command, but changing the protocol into "wss://" (e.g. "wss://list-of-random-words.trycloudflare.com").
- HTTP server
  > cloudflared tunnel --url http://localhost:8080
- The "http://" url given by this last command is the one you should access on the browser.