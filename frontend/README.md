# The Abby Project — Frontend

React 19 + Vite 8 + Tailwind 4 frontend for The Abby Project. See the [root README](../README.md) for full project documentation.

## Scripts

```bash
npm run dev            # Dev server on :3000 with /api proxy to :8000
npm run build          # Production build into dist/
npm run lint           # ESLint check
npm run test           # Vitest watcher (interactive)
npm run test:run       # One-shot test run (no watch)
npm run test:coverage  # Run tests with v8 coverage report → coverage/
```

## Testing

Tests live next to source as `*.test.{js,jsx}`. The shared scaffolding in
`src/test/` provides:

- `setup.js` — jest-dom matchers, jsdom polyfills (`matchMedia`, `IntersectionObserver`, `createImageBitmap`, canvas), Sentry mock, MSW lifecycle, and `localStorage` reset between tests.
- `server.js` + `handlers.js` — MSW node server with permissive default handlers for every `/api` route. Override with `server.use(http.get(…))` per test for specific responses.
- `render.jsx` — `renderWithProviders(ui, { route, routePath, withAuth })` wraps in `<MemoryRouter>` + `<AuthProvider>`. Re-exports RTL helpers and a configured `userEvent`.
- `factories.js` — `buildUser`, `buildParent`, `buildProject`, `buildBadge`, `buildChore`, `buildNotification` fixture builders.

Coverage thresholds are enforced in CI (see `vitest.config.js > coverage.thresholds`). Decorative SVGs, framer-motion animation primitives, and the dev-only `/__design` route are excluded.

When you need to stub framer-motion's `AnimatePresence` so exit animations don't keep nodes mounted past your assertion, mock at the file level:

```js
vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});
```

Modal components use `createPortal(…, document.body)`, so query their backdrop and contents off `document.body` rather than the RTL container.
