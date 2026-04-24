# Shell-only Progressive Web App

**Date:** 2026-04-24
**Status:** Design — pending implementation plan
**Author:** brainstorming session

## Goal

Make The Abby Project installable as a Progressive Web App on Android and iPhone home screens, with the React shell cached for instant cold-start and a clean prompt-for-update flow on new deploys. No offline write queue, no push notifications — those stay out of v1.

## Non-goals

- **No offline writes.** API calls (`/api/*`) remain network-only. If the user is offline, writes fail with the same error toasts they show today.
- **No runtime caching of API responses.** No IndexedDB cache, no background sync, no stale-while-revalidate strategies.
- **No web push.** The existing in-app notification bell stays the only delivery surface. Web push (VAPID, `PushSubscription`, `notify_parents()` wiring) is a separate future track.
- **No app shortcuts** in the manifest, no share targets, no file handlers.

## Why shell-only

The app is always-online by design (kids use it at home on WiFi; parents use it on phones with data). Shell caching delivers the "opens instantly" feel that makes a PWA feel native, without the cache-invalidation complexity of caching API responses or queuing writes. Future iteration triggers — if real needs surface — would be (in order): offline read of dashboard data → offline clock-in queued writes → web push for parent approval nudges.

## Architecture

### Framework choice: `vite-plugin-pwa`

Standard Vite + React PWA plugin. Wraps Workbox, auto-generates the SW from build outputs, ties cache keys to Vite's content hashes. Matches the project's "framework-standard tools" pattern (Vite, React Router, DRF — everything on-rails defaults).

### Update strategy: prompt, not auto-activate

`registerType: 'prompt'` — the new SW installs but stays in `waiting` state until the user clicks "Reload" in a toast. Aligns with the app's existing "respect the user mid-flow" doctrine (anti-farm gates, journal edit lock, paid-bonus approval dialogs).

### Caching strategy: precache only

Workbox precaches all hashed JS/CSS/HTML/icon/font assets via `globPatterns: '**/*.{js,css,html,svg,png,woff2}'`. Anything not in the precache list is network-only by default. `navigateFallback: '/index.html'` with a denylist for `/api/`, `/admin/`, `/static/`, `/media/`, `/.well-known/` so React Router gets the shell when offline but backend paths are never shadowed.

## Components

### New files

- `frontend/public/pwa-192x192.png`
- `frontend/public/pwa-512x512.png`
- `frontend/public/maskable-icon-512x512.png`
- `frontend/public/apple-touch-icon.png` (180×180)
- `frontend/src/pwa/PwaStatusProvider.jsx` — React context provider that calls `registerSW({ onNeedRefresh, onOfflineReady })` once and exposes `{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }` to children
- `frontend/src/pwa/UpdateBanner.jsx` — sticky top banner shown when `updateReady`; "Reload" button calls `applyUpdate()`
- `frontend/src/pwa/OfflineReadyToast.jsx` — bottom toast shown one-shot when `offlineReady`; auto-dismisses after 4s. Models after `DropToastStack.jsx` for animation + timer primitives
- `frontend/src/pwa/InstallCard.jsx` — Settings page card with Android install button + iOS instructions
- `frontend/src/pwa/useInstallPrompt.js` — hook capturing `beforeinstallprompt` event at app boot
- `frontend/src/pwa/PwaStatusProvider.test.jsx`
- `frontend/src/pwa/UpdateBanner.test.jsx`
- `frontend/src/pwa/OfflineReadyToast.test.jsx`
- `frontend/src/pwa/InstallCard.test.jsx`
- `frontend/src/pwa/useInstallPrompt.test.js`
- `config/tests/test_pwa_urls.py` — pins the new Django routes

### Modified files

- `frontend/package.json` — add `vite-plugin-pwa` and `@vite-pwa/assets-generator` to `devDependencies`
- `frontend/vite.config.js` — register the `VitePWA` plugin with the config below
- `frontend/index.html` — drop manual `<link rel="manifest">` (plugin injects it); keep `viewport-fit=cover`, `theme-color`, and the Apple meta tags
- `frontend/public/manifest.webmanifest` — **deleted** (plugin generates a fresh one)
- `frontend/src/App.jsx` — wrap the tree in `<PwaStatusProvider>`; mount `<UpdateBanner />` and `<OfflineReadyToast />` globally
- `frontend/src/pages/SettingsPage.jsx` — render `<InstallCard />` near the profile section
- `frontend/src/test/setup.js` — stub `navigator.serviceWorker` and `BeforeInstallPromptEvent` for jsdom
- `config/urls.py` — add explicit URL routes for PWA root files (Section: Django routing)

### Icon generation

One-shot CLI run, results committed:

```bash
cd frontend
npx @vite-pwa/assets-generator --preset minimal-2023 public/favicon.svg
```

The minimal-2023 preset emits exactly the 4 PNG sizes we need with a 20%-padded maskable variant. The wax-seal "A" already has visual weight near the center, so it masks cleanly to circle / squircle / rounded-square without clipping.

## Vite plugin config

```js
// frontend/vite.config.js
import { VitePWA } from 'vite-plugin-pwa'

VitePWA({
  registerType: 'prompt',
  injectRegister: false,
  filename: 'sw.js',
  manifestFilename: 'manifest.webmanifest',
  manifest: {
    name: 'The Abby Project',
    short_name: 'Abby',
    description: 'Track projects, chores, and homework — earn money, coins, and badges.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#f4ecd8',
    theme_color: '#f4ecd8',
    icons: [
      { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
      { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
      { src: '/maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  },
  workbox: {
    globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
    navigateFallback: '/index.html',
    navigateFallbackDenylist: [/^\/api\//, /^\/admin\//, /^\/static\//, /^\/media\//, /^\/\.well-known\//],
    runtimeCaching: [],
    cleanupOutdatedCaches: true,
  },
})
```

## Django routing

The SPA catch-all in `config/urls.py:94` (`re_path(r"^(?!static/|\.well-known/).*$", spa_view)`) currently intercepts `/sw.js` and `/manifest.webmanifest`, returning `index.html` for both. This is fatal for a PWA: the SW needs root scope to control the whole app, and browsers reject manifests served as `text/html`.

Add explicit URL routes for the PWA root files BEFORE the catch-all, served from `frontend_dist/`:

```python
# config/urls.py
import re

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
    """Serve a PWA root file from frontend_dist with the right cache headers."""
    response = static_serve(request, path, document_root=str(settings.BASE_DIR / "frontend_dist"))
    if path == "sw.js":
        response["Cache-Control"] = "no-cache"  # browser must check for updates
    return response

urlpatterns += [
    re_path(
        rf"^(?P<path>{'|'.join(re.escape(f) for f in _PWA_ROOT_FILES)})$",
        _pwa_static_serve,
    ),
]
```

`sw.js` MUST carry `Cache-Control: no-cache` so the browser revalidates on every page load — otherwise the user gets stuck on a stale SW that controls a bundle that no longer exists. The PNG icons are content-address-stable (different file = different name) and serve fine via the default `static_serve` headers.

### Test coverage for routing

`config/tests/test_pwa_urls.py` (mirrors the existing `test_well_known_urls.py` pattern):

- Each PWA path returns 200 (not HTML)
- `/sw.js` carries `Cache-Control: no-cache`
- `/manifest.webmanifest` returns `application/manifest+json` (or close — `static_serve` will infer from extension)
- Unknown root files (e.g., `/random.txt`) still hit the SPA catch-all
- The route ordering is correct (PWA files match before the catch-all)

## Update + offline-ready UX

The codebase has no generic `ToastProvider` — `DropToastStack` and `SavingsToastStack` are domain-specific, each with its own polling source. Rather than introduce a generic toast system as part of this spec (out of scope), the PWA layer ships its own minimal status surface:

```jsx
// frontend/src/pwa/PwaStatusProvider.jsx (sketch)
import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { registerSW } from 'virtual:pwa-register'

const PwaStatusContext = createContext({
  updateReady: false,
  offlineReady: false,
  applyUpdate: () => {},
  dismissOfflineReady: () => {},
})

export function PwaStatusProvider({ children }) {
  const [updateReady, setUpdateReady] = useState(false)
  const [offlineReady, setOfflineReady] = useState(false)
  const updateSW = useRef(null)

  useEffect(() => {
    if (import.meta.env.DEV) return  // Vite HMR handles dev updates
    updateSW.current = registerSW({
      onNeedRefresh: () => setUpdateReady(true),
      onOfflineReady: () => setOfflineReady(true),
    })
  }, [])

  const applyUpdate = () => updateSW.current?.(true)
  const dismissOfflineReady = () => setOfflineReady(false)

  return (
    <PwaStatusContext.Provider value={{ updateReady, offlineReady, applyUpdate, dismissOfflineReady }}>
      {children}
    </PwaStatusContext.Provider>
  )
}

export const usePwaStatus = () => useContext(PwaStatusContext)
```

`<UpdateBanner />` mounts at the very top of the existing sticky shell in `JournalShell` (above the pip strip + progress band, sharing their `z-30` layer per the project z-stack convention in `components/README.md`). When `updateReady` is true it renders a thin bar with copy + Reload button; when false it renders nothing (no layout reservation). The only action is "Reload" → `applyUpdate()`. No dismiss — the banner stays until the user reloads. Aligns with the "respect the user mid-flow" principle: visible but not blocking.

`<OfflineReadyToast />` is a one-shot bottom toast that mounts when `offlineReady` becomes true, animates in (modelled after `DropToastStack.jsx`'s framer-motion + setTimeout pattern), and auto-dismisses after 4s by calling `dismissOfflineReady()`. Only fires on first install — subsequent reloads don't re-trigger it because the SW is already activated.

Both components are mounted globally in `App.jsx` outside the page router, so they survive route changes. The provider wraps everything so `useInstallPrompt` and any future PWA hooks share the same context.

## Install card UX

`<InstallCard />` is rendered on `/settings` near the profile section. Three branches:

1. **Already installed** (`window.matchMedia('(display-mode: standalone)').matches` OR `navigator.standalone` on iOS) → render `null`
2. **`canInstall` is true** (Chrome / Edge / Android with `beforeinstallprompt` event captured) → "Install app" primary button. Click calls `event.prompt()`, awaits `userChoice`, clears the captured event regardless of outcome.
3. **iOS Safari** (UA-sniffed) → show static instructions: "Tap Share → Add to Home Screen"
4. **Else** (e.g., Firefox desktop) → show a soft "your browser doesn't support installing this app yet" line

`useInstallPrompt` hook is mounted in `App.jsx` (not in the card) so the `beforeinstallprompt` event is captured at app boot — the event only fires once per page load, and the user might not visit Settings until later.

## Edge cases

1. **localStorage auth token in standalone mode** — PWAs share localStorage with the parent origin. The `abby_auth_token` self-heal in `frontend/src/api/client.js` continues to work unchanged. No code change.

2. **Coolify "Invalid token" loops** — when this occurs to a PWA user, the 401 self-heal triggers `window.location.reload()`, the SW serves the cached shell, the user lands on Login, fresh login replaces the bad token. The PWA actually makes recovery faster than the non-PWA case (cached shell loads instantly). The prompt-for-update flow keeps the SW from going stale relative to the bundle.

3. **Sentry release tagging** — the SW caches the bundle for the current `VITE_SENTRY_RELEASE`. New deploy → new SW → user prompted → user reloads → on the new release for both bundle and Sentry tagging. No mismatch window.

4. **Dev mode** — registration is skipped via `import.meta.env.DEV` early return. The Vite dev server's HMR is incompatible with SW caching; this is the plugin's standard recommendation.

5. **Maskable icon safe zone** — `@vite-pwa/assets-generator`'s `minimal-2023` preset applies a 20% safe-zone padding to the maskable variant. The existing wax-seal "A" centers visual weight, so circle / squircle / rounded-square masks won't clip the letterform.

6. **iOS PWA meta tags** — the existing `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, and `apple-mobile-web-app-title` tags in `index.html` are kept (the plugin doesn't manage these). The `apple-touch-icon` link is updated to point to the new `/apple-touch-icon.png` (180×180 PNG) instead of the SVG, since iOS Safari historically doesn't reliably honor SVG apple-touch-icons.

## Testing

### Frontend tests (Vitest)

- `useInstallPrompt.test.js` — captures `beforeinstallprompt`, exposes `canInstall`, detects standalone via mocked `matchMedia`, clears event after `install()`
- `InstallCard.test.jsx` — four render branches (installed-hidden, canInstall-button, iOS-instructions, fallback-message); click on "Install app" calls the prompt event
- `PwaStatusProvider.test.jsx` — mocks `virtual:pwa-register` via `vi.mock`; asserts `onNeedRefresh` flips `updateReady` to true; asserts `applyUpdate()` calls `updateSW(true)`; asserts dev-mode early return (registerSW never called)
- `UpdateBanner.test.jsx` — renders nothing when `updateReady` is false; renders banner with Reload button when true; click invokes `applyUpdate` from context
- `OfflineReadyToast.test.jsx` — renders nothing when `offlineReady` is false; renders toast when true; auto-dismisses after 4s using `vi.useFakeTimers`

### Backend tests (Django)

- `config/tests/test_pwa_urls.py` — every PWA file path returns the file from `frontend_dist/`, `sw.js` has `Cache-Control: no-cache`, unknown root files fall through to the SPA catch-all

### Coverage

The new files easily clear the 65/55/55/65 thresholds. No exclusion needed for `frontend/src/pwa/`.

## Tunables

None. The PWA layer is declarative — manifest values live in `vite.config.js`, the toast and install copy live in their respective components. Future tuning (e.g., toast `autoDismissMs`, install card copy variants) is small enough to handle inline at the call site.

## Out-of-scope follow-ups

These are deliberately deferred. Each becomes its own design+plan when a real need surfaces:

- Offline read of dashboard / chores / homework via runtime caching
- Offline clock-in queued writes (most likely first follow-up — kids losing WiFi mid-clock-in is the easiest "real need" to imagine)
- Web push notifications for parent-approval nudges
- App shortcuts (e.g., "Quick clock in", "Add homework")
- Background sync for queued writes
- File system access for portfolio export
- Share target so other apps can send photos directly into a Creation log
