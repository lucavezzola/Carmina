// Keep the HTML entrypoint small; all browser behavior lives in the runtime module.
import { bootClient } from './client-runtime.mjs';

fetch('/runtime-config.json')
	.then((response) => response.ok ? response.json() : {})
	.catch(() => ({}))
	.then((config) => bootClient(config.wss_url));
