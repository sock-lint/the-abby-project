import { setupServer } from 'msw/node';
import { handlers } from './handlers.js';

// One server instance, started/stopped in setup.js. Individual tests override
// handlers via `server.use(...)` and let resetHandlers() in afterEach restore
// the defaults.
export const server = setupServer(...handlers);
