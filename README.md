"Carmina" (plural of _carmen_), meaning songs, poems, verses or chants, but also incantations, oracles, or ritual formulas, is a work-in-progress speech activated spells game, similar in concept to Mage Arena.

How to run:
- Python game server
  > python .\server.py
- Browser client (serves the public folder and supports .mjs modules)
  > python .\dev_server.py

Then open:
  > http://127.0.0.1:8000

How to run map-editor server (from "world_editor" folder):
  > python -m http.server 8000

How to open servers to the internet:
- Python game server
  > cloudflared tunnel --url http://localhost:8765
- Change "WS_URL" in _index.html_ to the "http://" url given from the above command, but changing the protocol into "wss://" (e.g. "wss://list-of-random-words.trycloudflare.com").
- HTTP server
  > cloudflared tunnel --url http://localhost:8080
- The "http://" url given by this last command is the one you should access on the browser.