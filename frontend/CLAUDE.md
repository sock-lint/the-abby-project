# frontend/

React 19 + Vite 8 + Tailwind 4 SPA served from the same origin as the API via WhiteNoise. All `/api/*` calls use relative URLs through `frontend/src/api/client.js`.

## Stack
- React 19, Vite 8, Tailwind 4, Framer Motion, React Router 7, lucide-react.
- Vitest 4 + React Testing Library + jsdom + MSW 2 + `@vitest/coverage-v8` for tests.
- `@sentry/vite-plugin` uploads source maps to self-hosted Sentry at `logs.neato.digital` during the Dockerfile's frontend-build stage.

## Commands
```bash
cd frontend && npm run dev       # :3000 with /api proxy to :8000
npm run build
npm run lint
npm run test                     # vitest watcher
npm run test:run                 # one-shot run (CI-style)
npm run test:coverage            # run + coverage report (gated in CI)
```

## Source layout
```
frontend/src/
  api/
    client.js        Fetch wrapper with token auth, 401 self-heal
    index.js         All endpoint functions (single import surface)
  hooks/             useApi.js (useAuth, useApi),
                     useParentDashboard.js (parallel-fetch merge of
                     chore + homework + redemption pending queues for
                     parent Today view),
                     useDropToasts.js, useCompanionGrowthToasts.js,
                     useQuestProgressToasts.js, useApprovalToasts.js,
                     useSpeechDictation.js, useInstallPrompt.js
  components/        See components/README.md for token/z-stack/a11y conventions.
    (root)           Button, IconButton, Loader, ErrorAlert, EmptyState,
                     StatusBadge, TabButton, BottomSheet, ConfirmDialog,
                     NotificationBell, ProgressBar, QuillProgress,
                     PageShell (re-export from layout/),
                     SectionHeader, CatalogSearch, SkillTagEditor,
                     Sparkline (dependency-free SVG trend line — consumes
                     the `summary-by-day` endpoints on /api/payments/ and
                     /api/coins/), ShareButton (Web Share API wrapper —
                     renders nothing where navigator.share is missing;
                     text-only payloads because media URLs are presigned
                     and expire).
    form/            TextField, SelectField, TextAreaField (labeled form
                     primitives with useId-driven htmlFor + aria-invalid /
                     aria-describedby wiring), useFieldIds (shared hook),
                     index.js barrel.
    layout/          JournalShell (outer layout — sidebar + header + rune
                     progress band + bottom nav + FAB), ChapterNav,
                     ChapterHub, HeaderStatusPips, HeaderProgressBand,
                     QuickActionsFab + QuickActionsSheet, PageShell.
    atlas/           IlluminatedVersal, BadgeSigil, IncipitBand,
                     ChapterRubric, RarityStrand, TomeShelf, TomeSpine
                     + mastery.constants.js.
    dashboard/       HeroPrimaryCard, VitalPipStrip, AccordionSection,
                     ApprovalQueueList, WeekGlanceBlock, QuickAdjustRow,
                     DailyChallengeCard, DailyChallengeClaimModal.
    rpg/             RpgSprite, BoostStrip.
    pwa/             PwaStatusProvider, UpdateBanner, OfflineReadyToast,
                     InstallPromptProvider, useInstallPrompt, InstallCard.
  constants/         colors.js (STATUS / RARITY color maps), styles.js
                     (inputClass plus internal-only buttonPrimary/
                     Secondary/Danger/Ghost/Success strings consumed by
                     <Button>/<IconButton>, and formLabelClass/HelpClass/
                     ErrorClass shared by the form primitives), storage.js
                     (localStorage key constants).
  utils/             format.js, api.js (normalizeList, fieldErrors), image.js,
                     dates.js (toISODate + quickDueDates for due-date chips),
                     contrast.js (WCAG contrast helper for themeContrast.test.js).
  pwa/               see components/pwa/ above — PwaStatusProvider mounts
                     the registerSW seam.
  themes.js          6 journal covers (hyrule/vigil/sunlit/snowquill/verdant/
                     harvest) + applyTheme(). Each cover ships a `tones`
                     block of accent colors tuned to pass WCAG AA on its
                     own surfaces.
  test/              setup.js, server.js, handlers.js, render.jsx,
                     factories.js, spy.js, pwa-register-stub.js,
                     themeContrast.test.js
```

## Auth wiring

- Token stored in `localStorage` key `abby_auth_token`, sent as `Authorization: Token <key>`.
- **Shared browser session:** the same-origin Unity `/play/` client may reuse this token. Delayed 401s and logout responses clear only the token they used, preserving a newer sign-in. `AuthProvider` reloads on an external tab's auth-token change or localStorage clear, keeping the rendered user/role aligned with the credential. It also drops the cached user snapshot so offline boot cannot hydrate the previous account.
- **Offline identity:** `AuthProvider` stores the last verified user in a versioned `{ token, user }` envelope bound to the exact credential that fetched it. It restores that identity only after a network failure with the matching token. Legacy snapshots and mismatched credentials are rejected; anonymous boots never accept a cached `/auth/me/` success. Login, signup and OAuth replacement clear the old snapshot before installing the new credential. `sessionError` carries OAuth/logout push-cleanup failures to the Login page.
- **Private API responses:** API reads are network-only; the generated worker has no `/api/` runtime cache route. `public/privacy-sw.js` deletes legacy `api-reads` caches on activation and `pwa/privacy.js` also purges them at boot/session changes. Until a prompted worker upgrade activates, `api/client.js` adds a random noncredential `_abby_session` query key to GETs and blob downloads. The key rotates with the credential and page lifetime and replaces an echoed pagination key, so an old URL-only worker cannot match another account's response. Static assets, images and fonts retain their offline caches.
- **401 self-heal in the fetch wrapper** ([api/client.js](src/api/client.js)): when any API call returns 401 AND the request carried an `Authorization` header AND its token is still the stored credential, the client clears `abby_auth_token` and calls `window.location.reload()`. `AuthProvider`'s boot flow then lands on the Login page with no stale token in localStorage. This is the recovery path for users whose stored tokens go invalid (e.g., after a Coolify redeploy we haven't pinned down yet) — without it, non-technical users had to manually purge all site data to escape "Invalid token" loops. The **"only if Authorization was sent"** guard is load-bearing: it prevents boot-time `getMe()` 401s (no header → no reload) from entering an infinite reload loop, and lets the Login page surface "Invalid credentials" without self-reloading. Tests live in the `401 self-heal` describe block of [api/client.test.js](src/api/client.test.js).
- **API error shape** ([api/client.js](src/api/client.js)): every non-2xx response throws an `Error` augmented with two extra fields — `err.status` (HTTP status code as a number) and `err.response` (the parsed JSON body). Callers can branch on specific codes — e.g., `JournalEntryFormModal` catches `err.status === 409` and reads `err.response.existing` to flip into edit mode, and the same modal catches `err.status === 403` for the "entry locked after midnight" case. The default `.message` still carries the human-readable text (`error`/`detail`/stringified body fallback) so generic `catch { toast(err.message) }` paths keep working. When adding a new branching check, prefer status over string-matching `.message`. **For a 400 on a form**, use `fieldErrors(err)` from [utils/api.js](src/utils/api.js): DRF answers with `{field: ["message"]}`, which has no `error`/`detail` key and so falls through to the `JSON.stringify` fallback — the user reads raw JSON in a banner unless the form maps each message onto its own input's `error` prop. Reference: [`PrinterConfigPanel.jsx`](src/pages/forge/PrinterConfigPanel.jsx).

## Design system (`components/README.md` is the canonical doc)


- **Import recovery:** `ProjectIngest` keeps the active job, edited plan, and overrides in a user-scoped device draft (`pages/ingest/ingestDraft.js`) and debounces staged-plan saves to the server. Connection failures resume the existing job. An interrupted creation checks that job and safely retries its idempotent commit; confirmed creation/discard clears the local draft.
