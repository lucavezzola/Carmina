// Keep the HTML entrypoint small; the full browser game logic lives in the
// runtime module, which handles rendering, movement, audio, and multiplayer.
import { bootClient } from './client-runtime.mjs';

fetch('/runtime-config.json')
	.then((response) => response.ok ? response.json() : {})
	.catch(() => ({}))
	.then((config) => bootClient(config.wss_url));
