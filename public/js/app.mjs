// Keep the HTML entrypoint small; all browser behavior lives in the runtime module.
import { bootClient } from './client-runtime.mjs';

bootClient({ wsUrl: 'ws://localhost:8765' });
