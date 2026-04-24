# Shell-only PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make The Abby Project installable as a Progressive Web App with shell-only caching, prompt-for-update toast, and a Settings install card. No offline writes, no push.

**Architecture:** `vite-plugin-pwa` in `generateSW` + `prompt` mode. Workbox precaches all hashed JS/CSS/HTML/icons. `/api/*` stays network-only. Django adds explicit routes for `/sw.js` + `/manifest.webmanifest` + PWA icons so the SPA catch-all doesn't intercept them. A `PwaStatusProvider` React context drives the global `<UpdateBanner />` (sticky top) and `<OfflineReadyToast />` (one-shot bottom). A `<InstallCard />` on Settings handles install UX via a captured `beforeinstallprompt` event on Chrome/Android and static instructions on iOS Safari.

**Tech Stack:** vite-plugin-pwa 1.x, @vite-pwa/assets-generator (devDep, one-shot CLI), Workbox (transitive), React 19 Context, Vitest 4, Django 5.

**Spec:** [docs/superpowers/specs/2026-04-24-pwa-shell-only-design.md](../specs/2026-04-24-pwa-shell-only-design.md)

---

## File Structure

**New frontend files:**
- `frontend/src/pwa/PwaStatusProvider.jsx` — context provider, registers SW once, exposes `{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }`
- `frontend/src/pwa/UpdateBanner.jsx` — sticky top banner inside `JournalShell`'s sticky header, "Reload" button
- `frontend/src/pwa/OfflineReadyToast.jsx` — one-shot bottom toast, auto-dismiss after 4s (modeled on `DropToastStack.jsx`)
- `frontend/src/pwa/useInstallPrompt.js` — hook capturing `beforeinstallprompt` at app boot, exposing `{ canInstall, install, isStandalone }`
- `frontend/src/pwa/InstallCard.jsx` — Settings card with 4 render branches
- Tests: `PwaStatusProvider.test.jsx`, `UpdateBanner.test.jsx`, `OfflineReadyToast.test.jsx`, `useInstallPrompt.test.js`, `InstallCard.test.jsx`
- `frontend/public/pwa-192x192.png`, `pwa-512x512.png`, `maskable-icon-512x512.png`, `apple-touch-icon.png` — generated, committed

**New backend files:**
- `config/tests/test_pwa_urls.py` — pins the new URL routes

**Modified frontend files:**
- `frontend/package.json` — add `vite-plugin-pwa` and `@vite-pwa/assets-generator` to `devDependencies`; add `generate-pwa-icons` script
- `frontend/vite.config.js` — register `VitePWA` plugin
- `frontend/index.html` — drop manual `<link rel="manifest">`; update `apple-touch-icon` href; keep theme-color and viewport meta
- `frontend/public/manifest.webmanifest` — DELETE (plugin generates the new one)
- `frontend/src/App.jsx` — wrap tree in `<PwaStatusProvider>`; mount `<UpdateBanner />` and `<OfflineReadyToast />`
- `frontend/src/pages/SettingsPage.jsx` — render `<InstallCard />` after profile section
- `frontend/src/test/setup.js` — stub `navigator.serviceWorker` and `BeforeInstallPromptEvent`

**Modified backend files:**
- `config/urls.py` — add explicit PWA root file routes before SPA catch-all

---

## Task 1: Backend — explicit URL routes for PWA root files

Add Django routes for `/sw.js`, `/manifest.webmanifest`, and the PWA icons so they aren't intercepted by the SPA catch-all. `sw.js` MUST get `Cache-Control: no-cache` so the browser checks for updates on every page load.

**Files:**
- Create: `config/tests/test_pwa_urls.py`
- Modify: `config/urls.py`

- [ ] **Step 1.1: Write the failing test**

Create `config/tests/test_pwa_urls.py`:

```python
"""Tests for PWA root-file URL handling.

Problem: Django's SPA catch-all (re_path(r"^(?!static/|\.well-known/).*$", spa_view))
greedily matches any unmatched path and returns the React index.html. For a PWA
this is fatal — the service worker MUST be served from /sw.js (not /static/sw.js)
to control the whole app, and browsers reject manifests served as text/html.

Fix: explicit URL routes for the small set of PWA root files, served from
frontend_dist/ directly. sw.js gets Cache-Control: no-cache so update detection
isn't blocked by stale browser caches.
"""
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings


def _ensure_pwa_fixture_files():
    """Materialize tiny fixture files in frontend_dist/ so static_serve has
    something to return. Creates the directory if needed; idempotent."""
    root = settings.BASE_DIR / "frontend_dist"
    root.mkdir(exist_ok=True)
    fixtures = {
        "sw.js": b"// fixture sw\n",
        "manifest.webmanifest": b'{"name":"Abby"}',
        "pwa-192x192.png": b"\x89PNG\r\n\x1a\n",
        "pwa-512x512.png": b"\x89PNG\r\n\x1a\n",
        "maskable-icon-512x512.png": b"\x89PNG\r\n\x1a\n",
        "apple-touch-icon.png": b"\x89PNG\r\n\x1a\n",
    }
    for name, body in fixtures.items():
        path = root / name
        if not path.exists():
            path.write_bytes(body)


class PwaRoutingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_pwa_fixture_files()

    def test_sw_js_returns_file_not_html(self):
        resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_sw_js_has_no_cache_header(self):
        """SW must revalidate on every load — otherwise users get stuck on a
        stale SW that controls a bundle that no longer exists."""
        resp = self.client.get("/sw.js")
        self.assertEqual(resp["Cache-Control"], "no-cache")

    def test_manifest_returns_file_not_html(self):
        resp = self.client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_pwa_icon_returns_file_not_html(self):
        resp = self.client.get("/pwa-192x192.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_maskable_icon_returns_file_not_html(self):
        resp = self.client.get("/maskable-icon-512x512.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_apple_touch_icon_returns_file_not_html(self):
        resp = self.client.get("/apple-touch-icon.png")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("text/html", resp["Content-Type"])

    def test_unknown_root_file_falls_through_to_spa(self):
        """Guard: only the listed PWA files get intercepted. Everything else
        still hits the SPA catch-all so React Router keeps working."""
        resp = self.client.get("/random-nonexistent-thing.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])

    def test_unknown_root_path_falls_through_to_spa(self):
        resp = self.client.get("/some-react-route")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp["Content-Type"])
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd C:/Users/socce/Documents/GitHub/the-abby-project
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
  DJANGO_SETTINGS_MODULE=config.settings_test \
  python manage.py test config.tests.test_pwa_urls -v 2
```

Expected: All `test_*_returns_file_not_html` tests FAIL with status 200 + `text/html` (because the SPA catch-all is intercepting). `test_unknown_root_*` tests PASS already (they document existing correct behavior).

- [ ] **Step 1.3: Add the URL routes**

Modify `config/urls.py`. Add `import re` near the top imports (after `import hashlib`). Insert this block AFTER the `if not settings.USE_S3_STORAGE: ...` block but BEFORE the `# SPA catch-all — MUST be last.` block:

```python
# PWA root files — these MUST be served from / (not /static/) so the service
# worker has root scope and the manifest serves with the right content type.
# Inserted before the SPA catch-all so it doesn't intercept them.
_PWA_ROOT_FILES = [
    "sw.js",
    "registerSW.js",
    "manifest.webmanifest",
    "pwa-192x192.png",
    "pwa-512x512.png",
    "maskable-icon-512x512.png",
    "apple-touch-icon.png",
    "favicon.svg",
]


def _pwa_static_serve(request, path):
    """Serve a PWA root file from frontend_dist with the right cache headers.
    sw.js MUST carry Cache-Control: no-cache so the browser revalidates on
    every page load — otherwise users get stuck on a stale SW that controls
    a bundle that no longer exists."""
    response = static_serve(
        request,
        path,
        document_root=str(settings.BASE_DIR / "frontend_dist"),
    )
    if path == "sw.js":
        response["Cache-Control"] = "no-cache"
    return response


urlpatterns += [
    re_path(
        rf"^(?P<path>{'|'.join(re.escape(f) for f in _PWA_ROOT_FILES)})$",
        _pwa_static_serve,
        name="pwa-root-file",
    ),
]
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
  DJANGO_SETTINGS_MODULE=config.settings_test \
  python manage.py test config.tests.test_pwa_urls -v 2
```

Expected: All 8 tests PASS.

- [ ] **Step 1.5: Run full Django test suite to confirm no regression**

```bash
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
  DJANGO_SETTINGS_MODULE=config.settings_test \
  python manage.py test
```

Expected: PASS (matches the baseline before this task; no new failures).

- [ ] **Step 1.6: Commit**

```bash
git add config/urls.py config/tests/test_pwa_urls.py
git commit -m "Add explicit Django routes for PWA root files

Route /sw.js, /manifest.webmanifest, and PWA icons through static_serve
from frontend_dist/ so the SPA catch-all doesn't intercept them. Service
workers need root scope to control the whole app, and browsers reject
manifests served as text/html. sw.js carries Cache-Control: no-cache so
update detection isn't blocked by stale browser caches."
```

---

## Task 2: Add npm dependencies

**Files:**
- Modify: `frontend/package.json` (via `npm install`)

- [ ] **Step 2.1: Install `vite-plugin-pwa`**

```bash
cd frontend
npm install --save-dev vite-plugin-pwa@^1.0.0
```

Expected: package added under `devDependencies`; `package-lock.json` updated.

- [ ] **Step 2.2: Install `@vite-pwa/assets-generator`**

```bash
cd frontend
npm install --save-dev @vite-pwa/assets-generator@^1.0.0
```

Expected: package added under `devDependencies`.

- [ ] **Step 2.3: Add an icon-generation script to `package.json`**

Modify `frontend/package.json`. Add this entry to the `scripts` block (after `test:coverage`):

```json
"generate-pwa-icons": "pwa-assets-generator --preset minimal-2023 public/favicon.svg"
```

The full `scripts` block becomes:

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest",
  "test:run": "vitest run",
  "test:coverage": "vitest run --coverage",
  "generate-pwa-icons": "pwa-assets-generator --preset minimal-2023 public/favicon.svg"
},
```

- [ ] **Step 2.4: Verify install**

```bash
cd frontend
npx vite-plugin-pwa --help 2>&1 | head -3 || echo "vite-plugin-pwa is a library, no CLI"
npx pwa-assets-generator --help | head -5
```

Expected: `pwa-assets-generator` shows its help screen with `--preset` flag mentioned. The vite plugin is library-only — the failing first command is fine.

- [ ] **Step 2.5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "Add vite-plugin-pwa and @vite-pwa/assets-generator devDeps"
```

---

## Task 3: Generate PWA icons from existing favicon.svg

**Files:**
- Create: `frontend/public/pwa-192x192.png`
- Create: `frontend/public/pwa-512x512.png`
- Create: `frontend/public/maskable-icon-512x512.png`
- Create: `frontend/public/apple-touch-icon.png`

- [ ] **Step 3.1: Run the icon generator**

```bash
cd frontend
npm run generate-pwa-icons
```

Expected output: lines like `Generated public/pwa-192x192.png`, `Generated public/pwa-512x512.png`, `Generated public/maskable-icon-512x512.png`, `Generated public/apple-touch-icon.png` (the `minimal-2023` preset emits exactly those four).

- [ ] **Step 3.2: Verify the four PNG files exist**

```bash
cd frontend
ls public/*.png public/favicon.svg
```

Expected: 4 PNGs present + the existing favicon.svg.

- [ ] **Step 3.3: Spot-check sizes**

```bash
cd frontend
file public/pwa-192x192.png public/pwa-512x512.png public/maskable-icon-512x512.png public/apple-touch-icon.png
```

Expected: each line shows `PNG image data, NNNxNNN`. Sizes should be 192×192, 512×512, 512×512 (with maskable safe-zone padding), 180×180.

- [ ] **Step 3.4: Commit**

```bash
git add frontend/public/pwa-192x192.png frontend/public/pwa-512x512.png frontend/public/maskable-icon-512x512.png frontend/public/apple-touch-icon.png
git commit -m "Generate PWA icons from wax-seal favicon

Four PNG sizes: pwa-192x192 and pwa-512x512 for Chrome's installability
criteria, maskable-icon-512x512 with 20% safe-zone padding for Android's
adaptive masks, apple-touch-icon at 180x180 for iOS Safari (which doesn't
reliably honor SVG apple-touch-icons)."
```

---

## Task 4: Configure VitePWA plugin in vite.config.js

The plugin generates the SW + manifest at build time. Set `registerType: 'prompt'` so updates require user consent, and `injectRegister: false` so we register manually from `PwaStatusProvider`.

**Files:**
- Modify: `frontend/vite.config.js`
- Modify: `frontend/public/manifest.webmanifest` (DELETE)

- [ ] **Step 4.1: Delete the now-redundant manifest file**

```bash
cd frontend
git rm public/manifest.webmanifest
```

The plugin will emit a fresh manifest at `dist/manifest.webmanifest` from the inline config in `vite.config.js`.

- [ ] **Step 4.2: Update `vite.config.js`**

Replace the contents of `frontend/vite.config.js` with:

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import { VitePWA } from 'vite-plugin-pwa'

// In production builds, assets live under Django's STATIC_URL (/static/) so
// the built index.html can be served as-is from the SPA catch-all view and
// still resolve its bundled JS/CSS through WhiteNoise. In dev the Vite server
// serves from / and proxies /api to the Django dev server on :8000.
export default defineConfig(({ command }) => {
  const plugins = [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'prompt',
      injectRegister: false,
      filename: 'sw.js',
      manifestFilename: 'manifest.webmanifest',
      // Emit the SW + manifest at dist root (not under /static/) so they
      // serve from / via the explicit Django routes in config/urls.py. The
      // SW needs root scope; the manifest needs application/manifest+json.
      manifest: {
        name: 'The Abby Project',
        short_name: 'Abby',
        description:
          'Track projects, chores, and homework — earn money, coins, and badges.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#f4ecd8',
        theme_color: '#f4ecd8',
        icons: [
          { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/maskable-icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [
          /^\/api\//,
          /^\/admin\//,
          /^\/static\//,
          /^\/media\//,
          /^\/\.well-known\//,
        ],
        runtimeCaching: [],
        cleanupOutdatedCaches: true,
      },
    }),
  ]

  // Upload source maps to self-hosted Sentry during production builds.
  // Requires SENTRY_AUTH_TOKEN — gracefully skipped in local dev.
  if (command === 'build' && process.env.SENTRY_AUTH_TOKEN) {
    plugins.push(
      sentryVitePlugin({
        url: 'https://logs.neato.digital',
        org: process.env.SENTRY_ORG,
        project: process.env.SENTRY_PROJECT,
        authToken: process.env.SENTRY_AUTH_TOKEN,
        release: {
          name: process.env.VITE_SENTRY_RELEASE,
        },
        sourcemaps: {
          filesToDeleteAfterUpload: ['./dist/assets/*.map'],
        },
        telemetry: false,
      }),
    )
  }

  return {
    base: command === 'build' ? '/static/' : '/',
    plugins,
    build: {
      sourcemap: 'hidden',
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts: ['abby.bos.lol', '.sslip.io', 'localhost'],
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
```

- [ ] **Step 4.3: Run a production build to verify the SW + manifest emit correctly**

```bash
cd frontend
npm run build
```

Expected: build succeeds. Output mentions `vite-plugin-pwa` and lists `dist/sw.js`, `dist/manifest.webmanifest` among the emitted assets. The `dist/sw.js` file exists at the root of `dist/` (NOT under `dist/assets/` or `dist/static/`).

- [ ] **Step 4.4: Spot-check the generated SW**

```bash
cd frontend
head -10 dist/sw.js
ls -la dist/sw.js dist/manifest.webmanifest
```

Expected: `sw.js` starts with Workbox boilerplate (an `importScripts` line or precompiled equivalent). Both files exist at `dist/` root.

- [ ] **Step 4.5: Spot-check the generated manifest**

```bash
cd frontend
cat dist/manifest.webmanifest
```

Expected: valid JSON matching the inline config in `vite.config.js`.

- [ ] **Step 4.6: Commit**

```bash
git add frontend/vite.config.js
git commit -m "Wire vite-plugin-pwa with prompt-for-update strategy

Plugin emits sw.js and manifest.webmanifest at dist root (served via
explicit Django routes from Task 1). registerType=prompt + injectRegister=false
mean we control SW activation from PwaStatusProvider — no auto-reload mid-flow.
globPatterns precaches all hashed JS/CSS/HTML/icon/font assets; runtimeCaching
is empty so /api/* stays network-only. navigateFallback serves index.html for
SPA routes when offline, with the backend paths denylisted.

The old static frontend/public/manifest.webmanifest is removed — the plugin
generates a fresh one from the inline config on each build."
```

---

## Task 5: PwaStatusProvider — context provider that registers the SW

This is the core React glue. Mounts once near the top of `App.jsx`, registers the SW via `virtual:pwa-register`, exposes `{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }` to child components.

**Files:**
- Create: `frontend/src/pwa/PwaStatusProvider.jsx`
- Create: `frontend/src/pwa/PwaStatusProvider.test.jsx`
- Modify: `frontend/src/test/setup.js` (add SW + install-prompt stubs)

- [ ] **Step 5.1: Add jsdom stubs to test setup**

Modify `frontend/src/test/setup.js`. After the `HTMLCanvasElement` block (around line 77) and before `// --- Lifecycle ---`, append:

```js
// --- Service Worker / PWA stubs ------------------------------------------
// jsdom doesn't ship a ServiceWorkerContainer. Tests that exercise PWA
// registration mock virtual:pwa-register directly, but a few branches
// touch navigator.serviceWorker for feature detection.
if (!('serviceWorker' in navigator)) {
  Object.defineProperty(navigator, 'serviceWorker', {
    value: {
      register: vi.fn(() => Promise.resolve({})),
      ready: Promise.resolve({}),
      controller: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    },
    configurable: true,
  });
}

// BeforeInstallPromptEvent isn't a standard jsdom global. Tests for
// useInstallPrompt construct synthetic events that mimic its shape.
if (typeof window.BeforeInstallPromptEvent === 'undefined') {
  window.BeforeInstallPromptEvent = class extends Event {
    constructor(type, init = {}) {
      super(type, init);
      this.platforms = init.platforms || ['web'];
      this.userChoice = init.userChoice || Promise.resolve({ outcome: 'accepted' });
      this.prompt = init.prompt || vi.fn(() => Promise.resolve());
    }
  };
}
```

- [ ] **Step 5.2: Write the failing test**

Create `frontend/src/pwa/PwaStatusProvider.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the virtual module BEFORE importing the provider. The mock exposes
// captured callbacks and the updateSW function so tests can simulate SW
// lifecycle events.
const mockState = {
  registerSW: null,
  updateSW: vi.fn(),
};

vi.mock('virtual:pwa-register', () => ({
  registerSW: vi.fn((opts) => {
    mockState.registerSW = opts;
    return mockState.updateSW;
  }),
}));

// Import the provider AFTER the mock is set up.
import { PwaStatusProvider, usePwaStatus } from './PwaStatusProvider';

function StatusProbe() {
  const { updateReady, offlineReady } = usePwaStatus();
  return (
    <div>
      <span data-testid="update-ready">{String(updateReady)}</span>
      <span data-testid="offline-ready">{String(offlineReady)}</span>
    </div>
  );
}

function ApplyButton() {
  const { applyUpdate } = usePwaStatus();
  return <button onClick={applyUpdate}>apply</button>;
}

function DismissButton() {
  const { dismissOfflineReady } = usePwaStatus();
  return <button onClick={dismissOfflineReady}>dismiss</button>;
}

describe('PwaStatusProvider', () => {
  beforeEach(() => {
    mockState.registerSW = null;
    mockState.updateSW.mockReset();
  });

  it('starts with both flags false', () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    expect(screen.getByTestId('update-ready').textContent).toBe('false');
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });

  it('flips updateReady to true when onNeedRefresh fires', async () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onNeedRefresh();
    });
    expect(screen.getByTestId('update-ready').textContent).toBe('true');
  });

  it('flips offlineReady to true when onOfflineReady fires', async () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onOfflineReady();
    });
    expect(screen.getByTestId('offline-ready').textContent).toBe('true');
  });

  it('applyUpdate calls updateSW(true)', async () => {
    const user = userEvent.setup();
    render(
      <PwaStatusProvider>
        <ApplyButton />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    await user.click(screen.getByText('apply'));
    expect(mockState.updateSW).toHaveBeenCalledWith(true);
  });

  it('dismissOfflineReady flips offlineReady back to false', async () => {
    const user = userEvent.setup();
    render(
      <PwaStatusProvider>
        <StatusProbe />
        <DismissButton />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onOfflineReady();
    });
    expect(screen.getByTestId('offline-ready').textContent).toBe('true');
    await user.click(screen.getByText('dismiss'));
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });

  it('usePwaStatus has safe defaults outside the provider', () => {
    // Don't crash when used in isolated tests that mount components without
    // the provider — just expose the no-op shape.
    render(<StatusProbe />);
    expect(screen.getByTestId('update-ready').textContent).toBe('false');
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });
});
```

- [ ] **Step 5.3: Run test to verify it fails**

```bash
cd frontend
npx vitest run src/pwa/PwaStatusProvider.test.jsx
```

Expected: FAIL — `Cannot find module './PwaStatusProvider'`.

- [ ] **Step 5.4: Implement the provider**

Create `frontend/src/pwa/PwaStatusProvider.jsx`:

```jsx
import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import { registerSW } from 'virtual:pwa-register';

const noop = () => {};

const PwaStatusContext = createContext({
  updateReady: false,
  offlineReady: false,
  applyUpdate: noop,
  dismissOfflineReady: noop,
});

export function PwaStatusProvider({ children }) {
  const [updateReady, setUpdateReady] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const updateSWRef = useRef(null);

  useEffect(() => {
    // Skip registration only in the actual `vite` dev server. In tests,
    // MODE === 'test' (with import.meta.env.DEV also true) — but we DO want
    // registerSW to be called so the test mock can capture the callbacks.
    // In production, MODE === 'production' and registration proceeds.
    if (import.meta.env.MODE === 'development') return undefined;
    updateSWRef.current = registerSW({
      onNeedRefresh: () => setUpdateReady(true),
      onOfflineReady: () => setOfflineReady(true),
    });
    return undefined;
  }, []);

  const applyUpdate = useCallback(() => {
    const fn = updateSWRef.current;
    if (typeof fn === 'function') {
      fn(true);
    }
  }, []);

  const dismissOfflineReady = useCallback(() => {
    setOfflineReady(false);
  }, []);

  return (
    <PwaStatusContext.Provider
      value={{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }}
    >
      {children}
    </PwaStatusContext.Provider>
  );
}

export function usePwaStatus() {
  return useContext(PwaStatusContext);
}
```

- [ ] **Step 5.5: Run test to verify it passes**

```bash
cd frontend
npx vitest run src/pwa/PwaStatusProvider.test.jsx
```

Expected: All 6 tests PASS. The `MODE === 'development'` check is `false` in Vitest (which uses `MODE === 'test'`), so `registerSW` IS called and the mock captures the callbacks correctly.

- [ ] **Step 5.6: Commit**

```bash
git add frontend/src/test/setup.js frontend/src/pwa/PwaStatusProvider.jsx frontend/src/pwa/PwaStatusProvider.test.jsx
git commit -m "Add PwaStatusProvider context for SW lifecycle

Single mount near top of App.jsx; calls registerSW({onNeedRefresh, onOfflineReady})
once and exposes {updateReady, offlineReady, applyUpdate, dismissOfflineReady}
so UpdateBanner and OfflineReadyToast can react to state changes without each
registering their own SW handler. usePwaStatus has no-op defaults outside the
provider so isolated component tests don't crash.

Adds jsdom stubs for navigator.serviceWorker and BeforeInstallPromptEvent."
```

---

## Task 6: UpdateBanner component

A thin sticky banner at the top of `JournalShell`'s sticky header. Renders nothing when no update is waiting; when one is, renders a single line with copy + Reload button.

**Files:**
- Create: `frontend/src/pwa/UpdateBanner.jsx`
- Create: `frontend/src/pwa/UpdateBanner.test.jsx`

- [ ] **Step 6.1: Write the failing test**

Create `frontend/src/pwa/UpdateBanner.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UpdateBanner from './UpdateBanner';
import { PwaStatusContext } from './PwaStatusProvider';

function renderWithStatus(value) {
  return render(
    <PwaStatusContext.Provider value={value}>
      <UpdateBanner />
    </PwaStatusContext.Provider>,
  );
}

describe('UpdateBanner', () => {
  it('renders nothing when updateReady is false', () => {
    const { container } = renderWithStatus({
      updateReady: false,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a status banner with Reload button when updateReady is true', () => {
    renderWithStatus({
      updateReady: true,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/new version/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it('clicking Reload calls applyUpdate from context', async () => {
    const applyUpdate = vi.fn();
    const user = userEvent.setup();
    renderWithStatus({
      updateReady: true,
      offlineReady: false,
      applyUpdate,
      dismissOfflineReady: vi.fn(),
    });
    await user.click(screen.getByRole('button', { name: /reload/i }));
    expect(applyUpdate).toHaveBeenCalledTimes(1);
  });
});
```

Note: this test imports `PwaStatusContext` directly from the provider module — we'll need to export the context object alongside the provider. The current implementation only exports `PwaStatusProvider` and `usePwaStatus`. Update the provider in step 6.2.

- [ ] **Step 6.2: Export `PwaStatusContext` from the provider**

Modify `frontend/src/pwa/PwaStatusProvider.jsx`. Change the line:

```jsx
const PwaStatusContext = createContext({
```

to:

```jsx
export const PwaStatusContext = createContext({
```

(Add `export` keyword. The `usePwaStatus` hook still works as before; the context export is for tests that need to inject a custom value without re-running the provider's effect.)

- [ ] **Step 6.3: Run test to verify it fails**

```bash
cd frontend
npx vitest run src/pwa/UpdateBanner.test.jsx
```

Expected: FAIL — `Cannot find module './UpdateBanner'`.

- [ ] **Step 6.4: Implement `UpdateBanner`**

Create `frontend/src/pwa/UpdateBanner.jsx`:

```jsx
import { RefreshCw } from 'lucide-react';
import { usePwaStatus } from './PwaStatusProvider';

/**
 * UpdateBanner — a thin top banner shown when a new service worker is
 * waiting. Mounted globally at the very top of the JournalShell sticky
 * header. Clicking Reload activates the waiting SW (which auto-reloads
 * the page).
 */
export default function UpdateBanner() {
  const { updateReady, applyUpdate } = usePwaStatus();
  if (!updateReady) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 bg-sheikah-teal-deep text-ink-page-rune-glow px-4 py-2 text-caption"
    >
      <RefreshCw size={14} aria-hidden="true" />
      <span>New version available.</span>
      <button
        type="button"
        onClick={applyUpdate}
        className="font-medium underline underline-offset-2 hover:opacity-80"
      >
        Reload
      </button>
    </div>
  );
}
```

- [ ] **Step 6.5: Run test to verify it passes**

```bash
cd frontend
npx vitest run src/pwa/UpdateBanner.test.jsx
```

Expected: All 3 tests PASS.

- [ ] **Step 6.6: Commit**

```bash
git add frontend/src/pwa/UpdateBanner.jsx frontend/src/pwa/UpdateBanner.test.jsx frontend/src/pwa/PwaStatusProvider.jsx
git commit -m "Add UpdateBanner — sticky top banner for SW updates

Renders nothing by default; when updateReady is true, shows a thin teal
banner with a Reload button that calls applyUpdate (which activates the
waiting SW and reloads the page). role=\"status\" + aria-live=\"polite\"
so screen readers announce the availability without interrupting users
mid-action.

Exports PwaStatusContext from the provider so tests can inject custom
state without re-running the SW registration effect."
```

---

## Task 7: OfflineReadyToast component

A bottom-right toast that appears once when the SW finishes its first install. Auto-dismisses after 4 seconds. Modeled after `DropToastStack.jsx`'s framer-motion + setTimeout pattern.

**Files:**
- Create: `frontend/src/pwa/OfflineReadyToast.jsx`
- Create: `frontend/src/pwa/OfflineReadyToast.test.jsx`

- [ ] **Step 7.1: Write the failing test**

Create `frontend/src/pwa/OfflineReadyToast.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import OfflineReadyToast from './OfflineReadyToast';
import { PwaStatusContext } from './PwaStatusProvider';

function renderWithStatus(value) {
  return render(
    <PwaStatusContext.Provider value={value}>
      <OfflineReadyToast />
    </PwaStatusContext.Provider>,
  );
}

// AnimatePresence stubbed so exit animations don't block synchronous unmount.
vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('OfflineReadyToast', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing when offlineReady is false', () => {
    const { container } = renderWithStatus({
      updateReady: false,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the toast when offlineReady is true', () => {
    renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/ready to work offline/i)).toBeInTheDocument();
  });

  it('auto-dismisses after 4 seconds', () => {
    const dismissOfflineReady = vi.fn();
    renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady,
    });
    expect(dismissOfflineReady).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(dismissOfflineReady).toHaveBeenCalledTimes(1);
  });

  it('clears the timer if unmounted before 4s', () => {
    const dismissOfflineReady = vi.fn();
    const { unmount } = renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady,
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    unmount();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(dismissOfflineReady).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 7.2: Run test to verify it fails**

```bash
cd frontend
npx vitest run src/pwa/OfflineReadyToast.test.jsx
```

Expected: FAIL — `Cannot find module './OfflineReadyToast'`.

- [ ] **Step 7.3: Implement `OfflineReadyToast`**

Create `frontend/src/pwa/OfflineReadyToast.jsx`:

```jsx
import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { usePwaStatus } from './PwaStatusProvider';

const DISMISS_AFTER_MS = 4000;

/**
 * OfflineReadyToast — one-shot bottom-right toast confirming the service
 * worker has finished its first precache. Auto-dismisses after 4s. Modeled
 * on DropToastStack's framer-motion + setTimeout pattern.
 */
export default function OfflineReadyToast() {
  const { offlineReady, dismissOfflineReady } = usePwaStatus();

  useEffect(() => {
    if (!offlineReady) return undefined;
    const timer = setTimeout(dismissOfflineReady, DISMISS_AFTER_MS);
    return () => clearTimeout(timer);
  }, [offlineReady, dismissOfflineReady]);

  return (
    <div className="fixed bottom-4 right-4 z-50 pointer-events-none">
      <AnimatePresence>
        {offlineReady && (
          <motion.div
            role="status"
            aria-live="polite"
            initial={{ x: 300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 300, opacity: 0 }}
            className="flex items-center gap-3 rounded-lg border border-green-400 bg-green-700 px-3 py-2 text-caption text-white shadow-lg pointer-events-auto"
          >
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Ready to work offline.</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 7.4: Run test to verify it passes**

```bash
cd frontend
npx vitest run src/pwa/OfflineReadyToast.test.jsx
```

Expected: All 4 tests PASS.

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/pwa/OfflineReadyToast.jsx frontend/src/pwa/OfflineReadyToast.test.jsx
git commit -m "Add OfflineReadyToast — one-shot install confirmation

Renders nothing by default; when offlineReady is true, shows a bottom-right
green toast that auto-dismisses after 4s. Modeled on DropToastStack's
framer-motion + setTimeout pattern. Cleans up the timer on unmount so the
dismiss callback never fires after the component is gone."
```

---

## Task 8: useInstallPrompt hook

Captures `beforeinstallprompt` once at app boot, exposes `{ canInstall, install, isStandalone }`. Mounted in `App.jsx` (not in `InstallCard`) so the event is captured early — the browser only fires it once per page load.

**Files:**
- Create: `frontend/src/pwa/useInstallPrompt.js`
- Create: `frontend/src/pwa/useInstallPrompt.test.js`

- [ ] **Step 8.1: Write the failing test**

Create `frontend/src/pwa/useInstallPrompt.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useInstallPrompt } from './useInstallPrompt';

function fireBeforeInstallPrompt(promptFn = vi.fn(() => Promise.resolve()), choice = { outcome: 'accepted' }) {
  const event = new window.BeforeInstallPromptEvent('beforeinstallprompt', {
    prompt: promptFn,
    userChoice: Promise.resolve(choice),
  });
  // jsdom doesn't auto-prevent default on synthetic events; the hook calls
  // preventDefault() to suppress the browser's own banner. Stub it so the
  // call doesn't throw.
  event.preventDefault = vi.fn();
  window.dispatchEvent(event);
  return event;
}

function setMatchMedia(matches) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: query.includes('standalone') ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe('useInstallPrompt', () => {
  beforeEach(() => {
    setMatchMedia(false);
    delete window.navigator.standalone;
  });

  it('starts with canInstall=false and isStandalone=false', () => {
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.canInstall).toBe(false);
    expect(result.current.isStandalone).toBe(false);
  });

  it('captures beforeinstallprompt and flips canInstall to true', async () => {
    const { result } = renderHook(() => useInstallPrompt());
    act(() => {
      fireBeforeInstallPrompt();
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
  });

  it('detects standalone via display-mode media query', () => {
    setMatchMedia(true);
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.isStandalone).toBe(true);
  });

  it('detects standalone via navigator.standalone (iOS)', () => {
    Object.defineProperty(window.navigator, 'standalone', {
      value: true,
      configurable: true,
    });
    const { result } = renderHook(() => useInstallPrompt());
    expect(result.current.isStandalone).toBe(true);
  });

  it('install() calls event.prompt() and clears the captured event', async () => {
    const promptFn = vi.fn(() => Promise.resolve());
    const { result } = renderHook(() => useInstallPrompt());
    act(() => {
      fireBeforeInstallPrompt(promptFn);
    });
    await waitFor(() => expect(result.current.canInstall).toBe(true));
    await act(async () => {
      await result.current.install();
    });
    expect(promptFn).toHaveBeenCalledTimes(1);
    expect(result.current.canInstall).toBe(false);
  });

  it('install() is a no-op when no event has been captured', async () => {
    const { result } = renderHook(() => useInstallPrompt());
    await act(async () => {
      await result.current.install();
    });
    expect(result.current.canInstall).toBe(false);
  });

  it('preventDefault is called on the captured event', () => {
    const { result } = renderHook(() => useInstallPrompt());
    let event;
    act(() => {
      event = fireBeforeInstallPrompt();
    });
    expect(event.preventDefault).toHaveBeenCalled();
    expect(result.current).toBeDefined();
  });
});
```

- [ ] **Step 8.2: Run test to verify it fails**

```bash
cd frontend
npx vitest run src/pwa/useInstallPrompt.test.js
```

Expected: FAIL — `Cannot find module './useInstallPrompt'`.

- [ ] **Step 8.3: Implement the hook**

Create `frontend/src/pwa/useInstallPrompt.js`:

```js
import { useCallback, useEffect, useRef, useState } from 'react';

function detectStandalone() {
  if (typeof window === 'undefined') return false;
  // iOS Safari uses navigator.standalone; Chrome/Edge/Firefox use the media
  // query. Both branches return true for an installed PWA.
  if (window.navigator?.standalone === true) return true;
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(display-mode: standalone)').matches;
  }
  return false;
}

/**
 * useInstallPrompt — captures the browser's beforeinstallprompt event so
 * we can trigger the install prompt from a user gesture later (Settings
 * page "Install app" button). The event only fires once per page load,
 * so this hook should be mounted near the top of the tree (App.jsx).
 *
 * Returns:
 *   - canInstall: boolean, true when an install event has been captured
 *     and the user hasn't installed yet
 *   - install(): triggers the prompt; returns a Promise that resolves to
 *     the user's choice ('accepted'|'dismissed')
 *   - isStandalone: boolean, true when the app is already running as an
 *     installed PWA (display-mode: standalone or navigator.standalone)
 */
export function useInstallPrompt() {
  const [canInstall, setCanInstall] = useState(false);
  const [isStandalone, setIsStandalone] = useState(detectStandalone);
  const eventRef = useRef(null);

  useEffect(() => {
    function onBeforeInstallPrompt(event) {
      event.preventDefault();
      eventRef.current = event;
      setCanInstall(true);
    }
    function onAppInstalled() {
      eventRef.current = null;
      setCanInstall(false);
      setIsStandalone(true);
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const install = useCallback(async () => {
    const event = eventRef.current;
    if (!event) return { outcome: 'dismissed' };
    await event.prompt();
    const choice = await event.userChoice;
    eventRef.current = null;
    setCanInstall(false);
    return choice;
  }, []);

  return { canInstall, install, isStandalone };
}
```

- [ ] **Step 8.4: Run test to verify it passes**

```bash
cd frontend
npx vitest run src/pwa/useInstallPrompt.test.js
```

Expected: All 7 tests PASS.

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/pwa/useInstallPrompt.js frontend/src/pwa/useInstallPrompt.test.js
git commit -m "Add useInstallPrompt hook for PWA install flow

Captures beforeinstallprompt at app boot (the browser only fires it once
per page load, so the hook must mount near the top of the tree). Exposes
canInstall + install() + isStandalone for InstallCard's render branches.

Listens for the appinstalled event too, so canInstall flips back to false
and isStandalone flips to true if the user installs while the app is open."
```

---

## Task 9: InstallCard component

Settings page card with four render branches: already-installed (hidden), Android/Chrome with `canInstall` (shows button), iOS Safari (shows instructions), other (shows soft fallback).

**Files:**
- Create: `frontend/src/pwa/InstallCard.jsx`
- Create: `frontend/src/pwa/InstallCard.test.jsx`

- [ ] **Step 9.1: Write the failing test**

Create `frontend/src/pwa/InstallCard.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstallCard from './InstallCard';
import * as installPromptModule from './useInstallPrompt';

function mockHook(value) {
  vi.spyOn(installPromptModule, 'useInstallPrompt').mockReturnValue(value);
}

const ORIGINAL_UA = window.navigator.userAgent;

function setUserAgent(ua) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: ua,
    configurable: true,
  });
}

describe('InstallCard', () => {
  beforeEach(() => {
    setUserAgent('Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0');
  });
  afterEach(() => {
    setUserAgent(ORIGINAL_UA);
    vi.restoreAllMocks();
  });

  it('renders nothing when isStandalone is true', () => {
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: true });
    const { container } = render(<InstallCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the Install button when canInstall is true', async () => {
    const install = vi.fn(() => Promise.resolve({ outcome: 'accepted' }));
    mockHook({ canInstall: true, install, isStandalone: false });
    const user = userEvent.setup();
    render(<InstallCard />);
    const button = screen.getByRole('button', { name: /install app/i });
    expect(button).toBeInTheDocument();
    await user.click(button);
    expect(install).toHaveBeenCalledTimes(1);
  });

  it('renders iOS instructions on iPhone Safari without canInstall', () => {
    setUserAgent(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 Version/16.4 Mobile/15E148 Safari/604.1',
    );
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.getByText(/share/i)).toBeInTheDocument();
    expect(screen.getByText(/add to home screen/i)).toBeInTheDocument();
  });

  it('renders the unsupported fallback when not installable and not iOS', () => {
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.getByText(/your browser/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 9.2: Run test to verify it fails**

```bash
cd frontend
npx vitest run src/pwa/InstallCard.test.jsx
```

Expected: FAIL — `Cannot find module './InstallCard'`.

- [ ] **Step 9.3: Implement `InstallCard`**

Create `frontend/src/pwa/InstallCard.jsx`:

```jsx
import { Smartphone, Share } from 'lucide-react';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import { useInstallPrompt } from './useInstallPrompt';

function isIosSafari() {
  if (typeof window === 'undefined') return false;
  const ua = window.navigator.userAgent;
  return /iPhone|iPad|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS/.test(ua);
}

/**
 * InstallCard — a Settings page card that handles PWA install across the
 * three relevant cases:
 *   1. Already installed → render nothing
 *   2. Chrome/Edge/Android with captured beforeinstallprompt → button
 *   3. iOS Safari (which never fires beforeinstallprompt) → instructions
 *   4. Anything else → soft fallback message
 */
export default function InstallCard() {
  const { canInstall, install, isStandalone } = useInstallPrompt();

  if (isStandalone) return null;

  return (
    <ParchmentCard tone="default" className="flex flex-col gap-3 p-5">
      <div className="flex items-center gap-2">
        <Smartphone size={18} className="text-ink-secondary" aria-hidden="true" />
        <h2 className="font-display text-lede text-ink-primary">Install Abby</h2>
      </div>
      <p className="font-body text-caption text-ink-secondary">
        Get faster access from your home screen — works just like a real app.
      </p>

      {canInstall && (
        <div>
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              install();
            }}
          >
            Install app
          </Button>
        </div>
      )}

      {!canInstall && isIosSafari() && (
        <div className="flex items-start gap-2 rounded-md border border-ink-whisper/30 bg-ink-page-aged/40 px-3 py-2 text-caption text-ink-secondary">
          <Share size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            On iPhone: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
          </span>
        </div>
      )}

      {!canInstall && !isIosSafari() && (
        <p className="text-caption text-ink-whisper italic">
          Your browser doesn't support installing this app yet — try Chrome or Edge on Android, or Safari on iOS.
        </p>
      )}
    </ParchmentCard>
  );
}
```

- [ ] **Step 9.4: Run test to verify it passes**

```bash
cd frontend
npx vitest run src/pwa/InstallCard.test.jsx
```

Expected: All 4 tests PASS.

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/pwa/InstallCard.jsx frontend/src/pwa/InstallCard.test.jsx
git commit -m "Add InstallCard for Settings page

Four render branches:
- Already installed (display-mode: standalone OR navigator.standalone) -> hidden
- canInstall (Chrome/Edge/Android captured beforeinstallprompt) -> Install button
- iOS Safari -> Share -> Add to Home Screen instructions
- Anything else (Firefox desktop, etc.) -> soft fallback message

Uses ParchmentCard + Button so the card matches the rest of the Settings
page styling."
```

---

## Task 10: Wire PwaStatusProvider + UpdateBanner + OfflineReadyToast into App.jsx

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 10.1: Read the current App.jsx to confirm structure**

```bash
sed -n '1,50p' frontend/src/App.jsx
```

Expected: confirms the imports block and the `<Sentry.ErrorBoundary>` wrapping `<SpriteCatalogProvider>` near the bottom.

- [ ] **Step 10.2: Update App.jsx to mount the PWA pieces**

Modify `frontend/src/App.jsx`. Add these imports near the other relative imports (after the `JournalShell` import, alphabetical-ish):

```jsx
import { PwaStatusProvider } from './pwa/PwaStatusProvider';
import UpdateBanner from './pwa/UpdateBanner';
import OfflineReadyToast from './pwa/OfflineReadyToast';
```

Then wrap the existing tree. The relevant block currently is:

```jsx
return (
  <Sentry.ErrorBoundary fallback={ErrorFallback} showDialog={false}>
    {celebration && (
      <BirthdayCelebrationModal
        entry={celebration}
        onDismiss={() => setCelebration(null)}
      />
    )}
    <SpriteCatalogProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<JournalShell />}>
            ...
```

Change to:

```jsx
return (
  <Sentry.ErrorBoundary fallback={ErrorFallback} showDialog={false}>
    <PwaStatusProvider>
      <UpdateBanner />
      {celebration && (
        <BirthdayCelebrationModal
          entry={celebration}
          onDismiss={() => setCelebration(null)}
        />
      )}
      <SpriteCatalogProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<JournalShell />}>
              ...
```

And inside the closing `</BrowserRouter>` block, before `</SpriteCatalogProvider>`, add:

```jsx
        </Routes>
      </BrowserRouter>
      <OfflineReadyToast />
    </SpriteCatalogProvider>
  </PwaStatusProvider>
</Sentry.ErrorBoundary>
```

The full closing tail of the JSX becomes:

```jsx
              {/* (existing legacy redirects) */}
            </Route>
          </Routes>
        </BrowserRouter>
        <OfflineReadyToast />
      </SpriteCatalogProvider>
    </PwaStatusProvider>
  </Sentry.ErrorBoundary>
);
```

`UpdateBanner` is mounted at the top of the tree so it renders above everything else when active; `OfflineReadyToast` is fixed-positioned so its DOM location doesn't matter, but inside the provider so it can `useContext`.

Note: `UpdateBanner` is intentionally OUTSIDE `BrowserRouter` so its sticky positioning isn't constrained by the route's main element. It pushes content down by its own height when visible.

- [ ] **Step 10.3: Run the App tests**

```bash
cd frontend
npx vitest run src/App
```

Expected: any existing App.test.* files still PASS. (If there are no App-level tests, this command runs zero tests and exits cleanly.)

- [ ] **Step 10.4: Run the full frontend test suite**

```bash
cd frontend
npm run test:run
```

Expected: ALL tests pass (existing + the 5 new PWA test files).

- [ ] **Step 10.5: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "Mount PwaStatusProvider + UpdateBanner + OfflineReadyToast in App

UpdateBanner mounts above the router so its sticky layout sits at the top
of the page, above JournalShell. OfflineReadyToast sits fixed at the
bottom-right inside the provider so it can read offlineReady via context."
```

---

## Task 11: Render InstallCard on Settings page

**Files:**
- Modify: `frontend/src/pages/SettingsPage.jsx`

- [ ] **Step 11.1: Read the current SettingsPage to find the best insertion point**

```bash
grep -n "ParchmentCard\|return (\|<div" frontend/src/pages/SettingsPage.jsx | head -30
```

Expected: shows the structure. Look for the top-level JSX `return (` and the first `<ParchmentCard>` (the profile card) — `<InstallCard />` should sit after that.

- [ ] **Step 11.2: Add the import + render**

Modify `frontend/src/pages/SettingsPage.jsx`. Add this import near the other relative imports (after `import Button from '../components/Button';`):

```jsx
import InstallCard from '../pwa/InstallCard';
```

Find the JSX section that renders the profile/avatar `<ParchmentCard>`. After that card's closing `</ParchmentCard>`, add:

```jsx
<InstallCard />
```

Place it as a sibling so it appears as its own card row in the Settings flow.

- [ ] **Step 11.3: Run the Settings page tests**

```bash
cd frontend
npx vitest run src/pages/SettingsPage
```

Expected: existing tests PASS. If there's no existing test file, this command runs zero tests and exits cleanly — that's fine.

- [ ] **Step 11.4: Run the full frontend test suite**

```bash
cd frontend
npm run test:run
```

Expected: ALL tests pass.

- [ ] **Step 11.5: Commit**

```bash
git add frontend/src/pages/SettingsPage.jsx
git commit -m "Render InstallCard on Settings page

Sits after the profile/avatar card so kids and parents who want to install
the app find it in the same place they manage their profile and theme."
```

---

## Task 12: Update index.html

Drop the manual `<link rel="manifest">` and the iOS-specific apple-touch-icon SVG href (vite-plugin-pwa injects a fresh manifest link; we want apple-touch-icon to point at the new 180×180 PNG).

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 12.1: Update `index.html`**

Replace the `<head>` block in `frontend/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>The Abby Project</title>
    <meta name="description" content="Track projects, chores, and homework — earn money, coins, and badges." />
    <meta name="theme-color" content="#f4ecd8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="Abby" />
    <meta name="mobile-web-app-capable" content="yes" />
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

Changes:
- Removed `<link rel="manifest" href="/manifest.webmanifest" />` — vite-plugin-pwa injects this automatically into the built index.html
- Changed `apple-touch-icon` href from `/favicon.svg` to `/apple-touch-icon.png`

- [ ] **Step 12.2: Build and verify the manifest is injected**

```bash
cd frontend
npm run build
grep -c 'rel="manifest"' dist/index.html
```

Expected: prints `1` — the plugin injected exactly one `<link rel="manifest">`.

- [ ] **Step 12.3: Verify the apple-touch-icon points at the PNG**

```bash
cd frontend
grep apple-touch-icon dist/index.html
```

Expected: shows `<link rel="apple-touch-icon" href="/apple-touch-icon.png" />`.

- [ ] **Step 12.4: Commit**

```bash
git add frontend/index.html
git commit -m "Update index.html for vite-plugin-pwa-injected manifest

The plugin injects <link rel=\"manifest\"> into the built index.html
automatically — drop the manual one. Switch apple-touch-icon to the new
180x180 PNG since iOS Safari historically doesn't reliably honor SVG
apple-touch-icons."
```

---

## Task 13: Coverage gate verification

The new files add ~250 lines of code + ~250 lines of test. Verify the coverage thresholds (65/55/55/65) still pass and the `frontend/src/pwa/` folder doesn't need exclusions.

**Files:** none (verification only)

- [ ] **Step 13.1: Run the coverage report**

```bash
cd frontend
npm run test:coverage
```

Expected: coverage report prints. The summary line shows lines/branches/functions/statements all at or above the gate (65/55/55/65). The `src/pwa/*` files appear in the table with high coverage (each test file targets its sibling component thoroughly).

- [ ] **Step 13.2: If coverage drops below threshold, identify the gap**

If a threshold fails:
- The report names the specific file falling short. Read that file and the test that targets it.
- The most likely cause is an untested branch (e.g., `useInstallPrompt`'s SSR-safety guard for `typeof window === 'undefined'`, or the `install()` no-op branch when no event was captured).
- Add a targeted test for that branch. Re-run.

If coverage is fine, this step is a no-op.

- [ ] **Step 13.3: No commit needed for this step** (verification only).

---

## Task 14: Production build verification

Confirm that the Docker build path still works end-to-end: Vite emits `sw.js` and `manifest.webmanifest` into `dist/`, the existing Dockerfile copies `dist/` to `frontend_dist/`, and the new Django routes serve them.

**Files:** none (verification only)

- [ ] **Step 14.1: Build the frontend in production mode**

```bash
cd frontend
npm run build
```

Expected: build completes. Output mentions `vite-plugin-pwa` and lists `dist/sw.js` + `dist/manifest.webmanifest`.

- [ ] **Step 14.2: Verify the dist tree**

```bash
ls -la frontend/dist/sw.js frontend/dist/manifest.webmanifest frontend/dist/pwa-*.png frontend/dist/apple-touch-icon.png frontend/dist/favicon.svg
```

Expected: every file exists.

- [ ] **Step 14.3: Stage them as Django would**

The Docker build copies `frontend/dist` to `frontend_dist/`. For local verification, do the same:

```bash
rm -rf frontend_dist
cp -r frontend/dist frontend_dist
```

- [ ] **Step 14.4: Run the Django PWA URL tests against the real built artifacts**

```bash
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
  DJANGO_SETTINGS_MODULE=config.settings_test \
  python manage.py test config.tests.test_pwa_urls -v 2
```

Expected: all 8 tests still PASS — this time with the real built files in `frontend_dist/` instead of the fixture stubs (the test's `_ensure_pwa_fixture_files()` is idempotent and doesn't overwrite real files).

- [ ] **Step 14.5: Run the full Django test suite**

```bash
DATABASE_URL="sqlite:///tmp_test.db" SECRET_KEY="x" \
  DJANGO_SETTINGS_MODULE=config.settings_test \
  python manage.py test
```

Expected: PASS, no regressions.

- [ ] **Step 14.6: Run the full frontend test suite**

```bash
cd frontend
npm run lint && npm run test:coverage
```

Expected: lint clean, all tests pass, coverage above gate.

- [ ] **Step 14.7: No commit needed for this step** (verification only).

---

## Task 15: Manual smoke test (no automation possible)

Some PWA behaviors only manifest in a real browser. This is a checklist for the implementer to walk through after the automated tests pass.

**Files:** none (manual)

- [ ] **Step 15.1: Run the dev stack**

```bash
docker compose up --build -d
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
```

- [ ] **Step 15.2: Open Chrome DevTools → Application tab on http://localhost:8000**

Navigate to the app, log in. In DevTools:

- **Manifest**: shows the manifest JSON with all four icons (192, 512, maskable, apple-touch). No errors in the manifest panel.
- **Service Workers**: lists `sw.js` with status "activated and running". Scope is `/`.
- **Cache Storage**: shows a Workbox-precache cache populated with the bundle's hashed assets.

If any of those is wrong, that's a real bug — debug before moving on.

- [ ] **Step 15.3: Verify install eligibility**

In DevTools → Application → Manifest, click "Install" or check the install icon in Chrome's URL bar. The dialog should appear with the wax-seal icon and the "Abby" name.

- [ ] **Step 15.4: Verify InstallCard renders correctly**

Navigate to `/settings`. The "Install Abby" card should appear with the "Install app" button visible. Click it — the same install dialog appears.

- [ ] **Step 15.5: Verify update banner**

Make a trivial change (e.g., change a heading text), rebuild and redeploy:

```bash
cd frontend
npm run build
cp -r dist/* ../frontend_dist/
```

Refresh the open browser tab. After a few seconds (the SW poll interval), the `<UpdateBanner>` should appear at the top of the page with a "Reload" button. Click it — the page reloads onto the new bundle.

- [ ] **Step 15.6: Verify offline-ready toast**

Open the app in an Incognito window (fresh SW install). The `<OfflineReadyToast>` should appear briefly in the bottom-right after the SW finishes its first install.

- [ ] **Step 15.7: Verify offline shell load**

In DevTools → Application → Service Workers, check the "Offline" box. Refresh the page. The SPA shell should load (header, navigation, etc.) but API calls should fail with the same error toasts they showed before. This confirms shell-only caching works as designed.

- [ ] **Step 15.8: No commit needed for this step** (manual verification only).

---

## Self-Review

Before considering the plan complete, verify the spec is fully covered:

| Spec section | Implemented in |
|---|---|
| Approach: vite-plugin-pwa generateSW + prompt | Task 4 |
| Shell-only precache, no API caching | Task 4 (`runtimeCaching: []`) |
| Icons: 192/512/maskable/apple-touch | Tasks 2, 3 |
| `frontend/src/pwa/` folder + 5 components | Tasks 5–9 |
| Django routes for PWA root files | Task 1 |
| `sw.js` no-cache header | Task 1 |
| `App.jsx` wrapping | Task 10 |
| `SettingsPage.jsx` mounting | Task 11 |
| `index.html` cleanup | Task 12 |
| Test setup stubs | Task 5 |
| Coverage gate | Task 13 |
| Production build verification | Task 14 |
| Manual smoke checklist | Task 15 |

All sections covered.
