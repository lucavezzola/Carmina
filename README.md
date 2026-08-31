"Carmina" (plural of _carmen_), meaning songs, poems, verses or chants, but also incantations, oracles, or ritual formulas, is a work-in-progress speech activated spells game, similar in concept to Mage Arena.

How to run:
- Python game server
  > python .\server.run
- HTTP server
  > python -m http.server 8080

How to open servers to the internet:
- Python game server
  > cloudflared tunnel --url http://localhost:8765
- Change "WS_URL" in _index.html_ to the "http://" url given from the above command, but changing the protocol into "wss://" (e.g. "wss://list-of-random-words.trycloudflare.com").
- HTTP server
  > cloudflared tunnel --url http://localhost:8080
- The "http://" url given by this last command is the one you should access on the browser.