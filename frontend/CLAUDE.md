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

### UI language (October 2026)

Use warm, straightforward language that fits the Meadow presentation. Name the
feature or action directly in navigation, headings, buttons, help, errors,
notifications and accessible labels. Use sentence case. Avoid manuscript or
adventure metaphors for everyday tasks and status (for example, use “Save”,
“Earned” and “Request reward” instead of “Inscribe”, “Sealed” and “Barter”).

| Current display name | Legacy display name / stable route |
| --- | --- |
| Tasks | Quests / `/quests` |
| Homework, Chores, Habits, Projects, 3D Printing, Challenges | Study, Duties, Rituals, Ventures, Forge, Trials (existing tab IDs) |
| Pets | Bestiary / `/bestiary` |
| Rewards | Treasury / `/treasury` |
| Payments, Timecards, Shop, Inventory, Savings goals | Coffers, Wages, Bazaar, Satchel, Hoards (existing tab IDs) |
| Progress | Atlas / `/atlas` |
| Guide | Lorebook (existing `lorebook` tab ID) |
| Memories | Chronicle / `/chronicle` |
| Gallery, Journal, Grades, Timeline | Existing memory tab IDs, including `sketchbook` and `yearbook` |
| Profile | Sigil / `/sigil` |

Keep Meadow place names and meaningful game concepts such as companions,
mounts, eggs, potions, XP, coins and boss challenges. Preserve catalog names
and user-authored content. Route names, saved keys, API fields, enum values and
component identifiers remain compatible; older architectural sections below
use some of these historical names.

The October 2026 Meadow refresh shares bundled Nunito, cream/lavender/mint surfaces, rounded controls and collection tiles across the web app and Play. All legacy font aliases resolve to Nunito. React uses the variable font's real 200–1000 weight range for body copy, labels and headings; Unity retains the shared weight-600 export. Both come from `shared/storybook/fonts`, with runtime copies maintained by `scripts/storybook/sync_presentation.py`. The bundled React `.ttf` is precached for offline typography.

The replaceable Meadow presentation also supplies the welcome screen. Its licensed chick is a generic artwork preview, not evidence of an account's owned species or growth. Today and Bestiary render actual server-confirmed companions through their species `sprite_key`. `cute-chick` and `cute-chick-mount` use privately staged chick/bird portraits when the matching licensed Chick overlay is present; missing or failed portraits recover through the runtime catalog and labelled icon. Other species retain their own runtime artwork. Saved cover keys and cosmetic ownership stay unchanged: `hyrule`/`vigil`/`sunlit`/`snowquill`/`verdant`/`harvest` now display as Memory/Twilight/Honey/Cloud/Clover/Peach Meadow. Baseline art/palette data remains in `shared/storybook/presentation.json`; `themes.js` adds semantic shades for readable UI.

`RpgSprite` defaults to smooth image scaling; use `rendering="pixelated"` explicitly for artwork that needs crisp pixel edges. Today and Companions use `petSpriteKeys` for retained pet rows, selecting the evolved portrait only from server-confirmed `evolved_to_mount`, never growth alone. Missing or failed portraits try `fallbackSpriteKey` before a labelled icon. Failures belong to the image URL, so a fresh catalog URL can recover. `JournalIcons` keeps its named exports with rounded Meadow SVG drawings, readable current-color outlines and soft cover-token fills. Use its shared chapter icons in navigation and `CoinIcon` for progression currency; real money keeps its dollar icon. `ChapterMarker` replaces manuscript section marks with decorative rounded number badges; `chapterMark` returns one-based Arabic labels for headings, chapter taxonomies and shelf medallions. Shared `TabList` uses one tab stop, Left/Right arrows with wrapping, Home/End, automatic selection and reduced-motion-aware active-tab scrolling.

- **Import recovery:** `ProjectIngest` keeps the active job, edited plan, and overrides in a user-scoped device draft (`pages/ingest/ingestDraft.js`) and debounces staged-plan saves to the server. Connection failures resume the existing job. An interrupted creation checks that job and safely retries its idempotent commit; confirmed creation/discard clears the local draft.
- **Drive selection:** `GoogleDrivePickerButton` preloads GIS/Picker before enabling its popup action, requests only `drive.file`, and keeps the token in the current interaction. `AddResourceModal` verifies metadata through Django before filling its explicit-save form; `SourceStep` starts the existing PDF review flow. `BottomSheet.focusSuspended` temporarily yields keyboard/focus ownership to Google's external dialog while dismissal stays disabled. See `docs/operations/google-drive-picker.md` for runtime setup.

2026-04-16 audit landed Plans A–E closing 12 gaps. Key artifacts new contributors should know about:

- **Type scale tokens** in [`index.css`](src/index.css)'s `@theme` block: `--text-micro` (10px), `--text-tiny` (11px), `--text-caption` (12px), `--text-body` (14px), `--text-lede` (18px). Avoid arbitrary `text-[Npx]` — add a token to @theme if the scale doesn't fit.
- **Form primitives** at `frontend/src/components/form/` — `<TextField>` / `<SelectField>` / `<TextAreaField>` bundle label + control + error/helpText with `useId`-driven `htmlFor` + `aria-invalid` + `aria-describedby`. `useFieldIds` hook + `formLabelClass`/`formHelpClass`/`formErrorClass` in [`constants/styles.js`](src/constants/styles.js) keep the three in lockstep. Import via `import { TextField, SelectField, TextAreaField } from '../components/form'`.
- **Button primitives** `<Button>` (5 variants: primary/secondary/danger/ghost/success × 3 sizes sm/md/lg) and `<IconButton>` (required `aria-label`, `console.error` warning in dev via `import.meta.env.PROD` gate). The `buttonPrimary`/`Secondary`/`Danger`/`Ghost`/`Success` class strings in [`constants/styles.js`](src/constants/styles.js) are marked internal — new call sites should use the components.
- **Modal overlay tokens** `--color-modal-wash` / `-vignette-mid` / `-vignette-edge` / `-seal-glow` / `-seal-edge` / `-seal-glow-strong` / `-seal-edge-strong` / `-shadow` / `-shadow-strong` / `-highlight` back the four `.modal-*` CSS classes and follow the active cover. Keep their distinct semantic roles even when two computed values match.
- **Primitive ARIA roles** — see [`components/README.md`](src/components/README.md) for the full cohort table. `Loader`/`EmptyState` → `role="status" aria-busy`, `ErrorAlert` → `role="alert"`, `ProgressBar` → `role="progressbar" aria-valuenow/min/max` (pass `aria-label` when a page renders multiple), `BottomSheet` → `role="dialog"`, `ConfirmDialog` → `role="alertdialog"`. All use `useId()` for stable `aria-labelledby`/`aria-describedby`.
- **Z-index stack** is three tiers: `z-30` (sticky shell), `z-40` (modal backdrop), `z-50` (modal surface + popover + toast + lightbox — shared; toasts under open modals ARE intentionally hideable). Don't introduce new z values without updating the README table.
- **Card placement rule:** page-specific `*Card` / `*Verse` / `*Sigil` components (AssignmentCard, CatalogCard, SkillVerse, RewardCard, CoinBalanceCard, ProjectOverridesCard, StepCard) live as sibling files in their owning `pages/<area>/` subfolder. Promote to the shared layer when a second page imports them; reusable `TomeShelf` and `TomeSpine` already live in `components/atlas/`. The now-deleted `components/Card.jsx` was a back-compat shim for `ParchmentCard`; all 17 call sites were migrated.
- **Per-area shared constants** between a parent component and extracted sibling cards should live in `<area>/<name>.constants.js` — `react-refresh/only-export-components` forbids non-component exports from `.jsx`. Examples: [`pages/achievements/skillTree.constants.js`](src/pages/achievements/skillTree.constants.js) holds `XP_THRESHOLDS` (the level curve); [`components/atlas/mastery.constants.js`](src/components/atlas/mastery.constants.js) holds the atlas vocabulary — `PROGRESS_TIER` / `RARITY_HALO` / `CHAPTER_NUMERALS` / `RARITY_KEYS` / `RARITY_ORDER` maps + `tierForProgress` / `chapterMark` / `countIlluminated` / `isRecentlyEarned` helpers (see Atlas cohort below); [`pages/achievements/collections.constants.js`](src/pages/achievements/collections.constants.js) holds the Reliquary Codex taxonomy (`COLLECTIONS`, `collectionForCriterion`, `groupBadgesByCollection`, `unlockHint`, `ladderSiblings`) scoped to the Badges page.

### Collection navigation (October 2026)

`TomeShelf` and `TomeSpine` retain their existing APIs while rendering wrapping Meadow collection cards. All-`vessel` sets render compact wrapping filter pills at every width. One tablist provides a single tab stop, Left/Right wrapping and Home/End selection; mount and pointer changes do not scroll the page or move unrelated focus. Badges, Lorebook and other collections share this control. Skills uses its separate Wayfinder hierarchy. See `components/README.md` for the descriptor and accessibility contract; `/__design` demonstrates both patterns with local synthetic examples.

### Atlas cohort (`frontend/src/components/atlas/`, lifted 2026-05-10)

The illuminated-manuscript vocabulary the Skills page introduced now lives at the shared layer. Five primitives + the `mastery.constants` module:
- `<IlluminatedVersal letter size progressPct tier showHalo />` — drop-cap with gilt fill tied to progress (sm / md / lg / xl). Mastered tiers (cresting / gilded) wear a `RARITY_HALO` ring. `aria-hidden` — the adjacent body carries the semantic text.
- `<BadgeSigil badge earned earnedAt hint onSelect />` — wax-seal medallion. Earned sigils carry `RARITY_HALO` + foil sheen + `xp_bonus` ledge; unearned render as debossed intaglios with a script `hint` underneath. **`hint` is caller-supplied** — the Reliquary Codex passes `unlockHint(badge)` from `collections.constants`, but the primitive stays domain-agnostic so other surfaces can pass any string.
- `<IncipitBand letter title kicker meta progressPct rarityCounts versalSize />` — hero strip for any folio-style chapter opener. Drop-cap fills with `progressPct`; rarity strand renders only when `rarityCounts` is supplied. Used by `SigilCodex` (Reliquary "Sigil Case") and Yearbook `ChapterCard` (current-year chapter).
- `<ChapterRubric index name icon summary />` or legacy `subject={…}` — §I/§II rubric numeral + display-serif title with a hair-rule beneath. Direct props win over the legacy `subject` object when both are present.
- `<RarityStrand counts compact />` — slim 5-segment band, one segment per rarity sized by total, fill by `earned/total`. `role="img"` with a descriptive aria-label.
- `mastery.constants.js` exports: `PROGRESS_TIER`, `TIER_BADGE_TONE`, `tierForProgress`, `RARITY_HALO`, `CHAPTER_NUMERALS`, `chapterMark`, `countIlluminated`, `RECENT_EARNED_DAYS`, `isRecentlyEarned`, `RARITY_KEYS`, `RARITY_ORDER`.
- **CSS contract** (declared once in [`index.css`](src/index.css), reused everywhere): `.versal-gilt` with `--versal-fill` custom property; `@keyframes halo-rise` / `gilded-glint`; `--color-rarity-{common,uncommon,rare,epic,legendary}`. All animations sit inside the existing `prefers-reduced-motion` block.
- **Current consumers** (18 importers across 4 surfaces — the cohort's reach is why it was promoted): `pages/achievements/` (Skills + Badges), `pages/character/` (Sigil Frontispiece), `pages/lorebook/` + `components/lorebook/` (FirstEncounter, LorebookFolio, LorebookIncipit, TrialSheet), `pages/__design.jsx`, plus the four 2026-05-10 apply phases: `pages/bestiary/` (rarity halos on pets / mounts / Codex tiles + ChapterRubric on Hatchery, extended 2026-05-16 with `IncipitBand` heroes on all four sub-tabs + `TomeShelf variant="vessel"` filter pills on Companions/Mounts + a `SigilCodex`-style `IncipitBand` → `TomeShelf` collection cards → `BestiaryFolio` body for the Codex — see "Bestiary codex alignment" in `apps/pets/CLAUDE.md`), `pages/project/ProjectHeader.jsx` + `PlanTab.jsx` (status-driven versal + milestone numerals), `pages/yearbook/ChapterCard.jsx` (full IncipitBand on current chapter, small versal on past chapters), `components/dashboard/HeroPrimaryCard.jsx` + `AccordionSection.jsx` (versal on action variants + optional chapter numeral on collapsible sections).
- **Tier is `bar` + `chip`, never applied ornament.** A folio shows its tier through the versal's gilt fill, the progress bar, the stat values, and a `RuneBadge` on its kicker (`TIER_BADGE_TONE` maps the five rungs onto the badge's `ink`/`moss`/`teal`/`ember`/`gold` tones) — the same channels `QuestLogEntry` and `SkillVerse` use. A tier-tinted band on the folio verso was tried and removed in 2026-08: it was the app's only decorative-band state signal, its `--color-headband-*` hexes were the only tier colors `applyTheme` never retunes per cover, and it restated a tier already shown three other ways. Collection cards use readable labels and optional progress bars; the former binding headbands are removed.
- **When NOT to apply**: Manage, Settings, Payments, Timecards, ClockPage are deliberately utilitarian surfaces — the audit explicitly flagged these as "do not over-decorate." Don't introduce new rarity tiers, halo colors, or keyframes inside an apply phase; the cohort's value is its consistency.
- Full architecture doc + per-primitive API table lives at [`components/README.md`](src/components/README.md) under "Atlas cohort".

### Intentional hex-literal retentions
The few color values that can't be token references all carry an inline `// intentional:` comment explaining why. Current retentions: `<input type="color">` defaults (user data), file-picker native markup and Google brand SVG. Shared modal close and confirmation controls use the current cover tokens.

### `<CatalogSearch>` ([components/CatalogSearch.jsx](src/components/CatalogSearch.jsx), 2026-05-09)
Icon-prefixed text input used to filter long catalog lists. Fully controlled — pages own the `value` + the memoized filtered list. A clear button appears when the value is non-empty. Wired today on Inventory (filters items by name/description), Badges (filters within Reliquary chapters), Skills (filters skills inside the loaded folio — drops empty subjects), and Rewards (Bazaar shop). Pages should hide it until the source list has at least one entry, and render an `<EmptyState>` when the filter yields nothing so the "no matches — clear the filter" path doesn't read the same as "no items yet". Pinned by [`CatalogSearch.test.jsx`](src/components/CatalogSearch.test.jsx) for the primitive plus the per-page filter test that lives next to each consumer.

## Celebration moments (2026-05)

The app surfaces six purpose-built reveal/toast components mounted near the top of [`App.jsx`](src/App.jsx) so big-moment notifications don't sit lost in the bell. All six respect the global `prefers-reduced-motion` rule in [`index.css`](src/index.css):
- [`CelebrationModal`](src/components/CelebrationModal.jsx) — full-screen reveal for `streak_milestone` (3/7/14/30/60/100) + `perfect_day`. At App boot it polls `GET /api/notifications/pending-celebration/` (returns the most recent unread streak/perfect-day notification — sister to `/api/chronicle/pending-celebration/`); dismissing fires `markNotificationRead`.
- [`PetCeremonyModal`](src/pages/bestiary/PetCeremonyModal.jsx) — sequenced reveals for `hatch_pet` (sparkle) and `evolve` (crown halo), launched from `Hatchery` and `Companions`. Tap-anywhere dismiss. See `apps/pets/CLAUDE.md` for the four modes (hatch/evolve/breed/expedition_return).
- [`RareDropReveal`](src/components/RareDropReveal.jsx) + [`rareDropTiers.js`](src/components/rareDropTiers.js) — escalates `rare`/`epic`/`legendary` drops out of the slide-in [`DropToastStack`](src/components/DropToastStack.jsx) into a center-screen card with rarity glow, queued so multiple rares don't collide.
- [`DailyChallengeClaimModal`](src/components/dashboard/DailyChallengeClaimModal.jsx) + countdown chip on [`DailyChallengeCard`](src/components/dashboard/DailyChallengeCard.jsx) — gold-leaf ring when ready to claim; post-claim modal does the reveal.
- [`ApprovalToastStack`](src/components/ApprovalToastStack.jsx) + [`useApprovalToasts`](src/hooks/useApprovalToasts.js) — child-side toasts for chore/homework/creation/exchange/redemption approvals + rejections, polled from notifications. Seen-IDs persist in `localStorage` per the keys in [`constants/storage.js`](src/constants/storage.js) so a refresh doesn't re-show them.
- [`QuestProgressToastStack`](src/components/QuestProgressToastStack.jsx) + [`useQuestProgressToasts`](src/hooks/useQuestProgressToasts.js) — 4s floater on every active-quest progress increment ("+10 toward Dragon Slayer 62%") so contributing actions feel tied to the quest rather than vanishing into a stat. Driven by polling `getActiveQuest()` for delta detection on `current_progress`.

Plus a small framer-motion equip toast on [`Character.jsx`](src/pages/Character.jsx) — "Now wearing X" floats up on every cosmetic equip/unequip.

## PWA / installable app

[`frontend/src/pwa/`](src/pwa/) + [`vite.config.js`](vite.config.js) + [`config/urls.py`](/config/urls.py). `vite-plugin-pwa` runs in `registerType: 'prompt'` mode with `injectRegister: false` — the SW + manifest are emitted at dist root (NOT under `/static/`) because a service worker MUST serve from `/` to claim root scope and the manifest needs `application/manifest+json`. PWA root files (`sw.js`, `push-sw.js`, `privacy-sw.js`, `registerSW.js`, `manifest.webmanifest`, three icon PNGs, `apple-touch-icon.png`, `favicon.svg`) are routed through a dedicated `_pwa_static_serve` view in [`config/urls.py`](/config/urls.py) that's wired BEFORE the SPA catch-all. **`sw.js` carries `Cache-Control: no-cache`** stamped explicitly by that view so the browser revalidates on every page load — without this, users get stuck on a stale SW that controls a bundle that no longer exists. The `apple-touch-icon` is a 180x180 PNG, never the SVG (iOS rejects SVG touch icons silently). The five providers/components mounted in [`App.jsx`](src/App.jsx):

- **`PwaStatusProvider`** ([`pwa/PwaStatusProvider.jsx`](src/pwa/PwaStatusProvider.jsx)) — wraps `registerSW` from `virtual:pwa-register`, exposes `{updateReady, offlineReady, applyUpdate, dismissOfflineReady}`. Skips registration in `import.meta.env.MODE === 'development'` only — tests (`MODE === 'test'`) DO call `registerSW` so the test mock can capture the callbacks. The `applyUpdate` flow is load-bearing: it (a) calls `updateSW(true)` to activate the waiting SW, (b) **owns the page reload** via a `controllerchange` listener AND a 1.5s `setTimeout` fallback because iOS Safari PWAs and some Android browsers don't reliably fire `controllerchange` after `SKIP_WAITING`, (c) stamps `pwa:last-reload-attempt` in localStorage with a 60s suppress window so the post-reload mount swallows any re-firing `onNeedRefresh` from rolling-deploy sw.js drift across replicas (without this the banner would re-appear within ms of reload, indistinguishable from "the banner never cleared"). The reload window-stamp is cleared on the next clean mount.
- **`UpdateBanner`** ([`pwa/UpdateBanner.jsx`](src/pwa/UpdateBanner.jsx)) — sticky `role="status"` banner in sheikah-teal at the top of the page, shown when `updateReady === true`. Single Reload button calls `applyUpdate`. Renders `null` when no update is waiting.
- **`OfflineReadyToast`** ([`pwa/OfflineReadyToast.jsx`](src/pwa/OfflineReadyToast.jsx)) — one-shot bottom-right framer-motion toast confirming the SW finished its first precache. Auto-dismisses after 4s. Modeled on `DropToastStack`.
- **`InstallPromptProvider` + `useInstallPrompt`** ([`pwa/useInstallPrompt.js`](src/pwa/useInstallPrompt.js)) — captures the browser's `beforeinstallprompt` event so the Settings page can offer a real Install button. **The early-capture in [`main.jsx`](src/main.jsx) is critical**: Chrome fires `beforeinstallprompt` very early after page load — often before `InstallPromptProvider`'s `useEffect` has run. `main.jsx` adds a window-level listener at module load time that stashes the event on `window.__deferredInstallPrompt`; the provider reads from there on mount. Without this stash the event is dropped on Chrome Android and the Install card falls through to "browser doesn't support" messaging. `detectStandalone()` checks both `navigator.standalone` (iOS Safari) and `matchMedia('(display-mode: standalone)')` (Chrome/Edge/Firefox).
- **`InstallCard`** ([`pwa/InstallCard.jsx`](src/pwa/InstallCard.jsx)) — Settings page card that handles five install cases: (1) already standalone → renders nothing, (2) `canInstall` → real Install button via `event.prompt()`, (3) iOS Safari → `Share → Add to Home Screen` instructions (iOS never fires `beforeinstallprompt`), (4) Android Chrome without prompt → `⋮ → Add to Home Screen` instructions, (5) anything else → soft fallback. The `isAndroidChrome()` UA detection deliberately excludes EdgeA, Opera, Samsung Browser, and Facebook in-app webviews because each ships its own install path (or none at all in webviews) and the generic Chrome menu instructions would be wrong.
- **Web Push** ([`pwa/usePushNotifications.js`](src/pwa/usePushNotifications.js) + [`pwa/PushNotificationsCard.jsx`](src/pwa/PushNotificationsCard.jsx)) — per-device opt-in on the Settings page. The SW handlers live in [`public/push-sw.js`](public/push-sw.js), pulled into the generated worker via workbox's `importScripts` rather than switching to `injectManifest`: generateSW stays in charge of the precache + update-prompt behavior documented above. `push-sw.js` is in the `_PWA_ROOT_FILES` list in [`config/urls.py`](/config/urls.py) so it serves from root with the SW's scope. The hook degrades in layers — `supported` (browser has the APIs at all; iOS needs the app installed to the Home Screen), `enabled` (server has a VAPID keypair), then the browser's own `permission` — so the card can always say something true instead of offering a dead button.
- **Push ownership:** `pwa/pushSession.js` verifies/rebinds an existing browser endpoint with the server before showing `subscribed=true`. Logout/account replacement stop new bindings, unsubscribe the current browser immediately, and queue endpoint removal after any pending bind. They send the captured `push_endpoint` when revoking the old credential; account replacement completes revocation before installing the new token. Server removal is scoped to the original user and this endpoint; other devices stay subscribed. Native unsubscribe works offline. A live endpoint requires confirmed ownership removal and token revocation; zero removals or an uncertain pending bind cannot establish safety. If cleanup cannot establish safety, account replacement is blocked with a useful error; logout still clears its local credential and reports the cleanup failure.
- **Test stub** at [`frontend/src/test/pwa-register-stub.js`](src/test/pwa-register-stub.js) — vitest config aliases `virtual:pwa-register` to this stub so tests don't choke on the Vite virtual module.

The worker's root scope differs from the bundle's `/static/` base. Keep
Workbox's `modifyURLPrefix` mapping from `assets/` to `/static/assets/` aligned
with the URLs in the built HTML and lazy imports. For an offline browser check,
disable the browser HTTP cache while keeping Cache Storage intact; otherwise
warm HTTP responses can mask missing service-worker precache routes.

## Journal covers (`frontend/src/themes.js`)

6 cover palettes (`hyrule` / `vigil` / `sunlit` / `snowquill` / `verdant` / `harvest`) stored as `User.theme`; legacy values (`summer`/`winter`/`spring`/`autumn`) map forward via `LEGACY_THEME_ALIASES`. `applyTheme(name)` writes the active cover's colors to CSS custom properties on `<html>` — including a per-theme `tones` block (`goldLeaf`, `moss`, `mossDeep`, `emberDeep`, `royal`, `rose`) that used to be global constants in `index.css`. Vigil is the only dark cover and *inverts* `emberDeep` (light on dark) where light covers darken it — so `text-gold-leaf`, `text-ember-deep`, etc. render as chip text that passes contrast on every cover. Each cover is tuned to pass WCAG AA on three surfaces — `page` (body), `pageAged` (`ParchmentCard tone="default"`), and `pageGlow` (`ParchmentCard tone="bright"`, e.g. `HeroPrimaryCard`). The gate lives in [`src/test/themeContrast.test.js`](src/test/themeContrast.test.js): 216 assertions (every cover × every ink tier + accent tone × every surface) using [`src/utils/contrast.js`](src/utils/contrast.js)'s WCAG helper. **If you add a 7th cover**, supply the full `tones` block and the gate will refuse values that fail 4.5:1 (body) / 3:1 (chip text). The picker lives at `SettingsPage.jsx` — each swatch renders a live sample (title + body + whisper + flame/coin/quest chips) in that cover's exact tones so users can eyeball readability before committing.

## Frontend testing (`frontend/`)

- **Stack:** Vitest 4 + React Testing Library + jsdom + MSW 2 + `@vitest/coverage-v8`. Config lives in `frontend/vitest.config.js` (separate from `vite.config.js` so test-only deps don't leak into production builds).
- **Layout:** tests are colocated next to source as `*.test.{js,jsx}`. Shared scaffolding lives under `frontend/src/test/`:
  - `setup.js` — global jest-dom matchers, `vi.mock('@sentry/react', …)`, jsdom polyfills (`matchMedia`, `IntersectionObserver`, `ResizeObserver`, `createImageBitmap`, `HTMLCanvasElement.{getContext,toBlob}`), and MSW lifecycle (`server.listen` / `resetHandlers` / `close`). Each test clears localStorage and seeds `abby_auth_token=test-session` to match the default authenticated API fixtures. Anonymous cases must explicitly clear that token. Endpoint spies ignore only the client `_abby_session` namespace when asserting route/body contracts.
  - `server.js` + `handlers.js` — single MSW node server with permissive defaults (empty success shapes) for every `/api` route in `frontend/src/api/index.js`. Per-test `server.use(http.get(…))` overrides for specific responses.
  - `render.jsx` — `renderWithProviders(ui, { route, routePath, withAuth })` wraps in `<MemoryRouter>` + `<AuthProvider>`; re-exports RTL helpers and a pre-set-up `userEvent`.
  - `factories.js` — `buildUser` / `buildParent` / `buildProject` / `buildBadge` / `buildChore` / `buildNotification` builders. Use these instead of inlining fixture objects.
  - `themeContrast.test.js` — WCAG AA gate for every journal cover (see "Journal covers" above). Pure-data; uses [`src/utils/contrast.js`](src/utils/contrast.js). Any palette edit that drops a tone below 4.5:1 / 3:1 breaks the frontend-test job.
- **Coverage gate:** thresholds in `vitest.config.js` are 65/55/55/65 (lines/branches/functions/statements). Excluded from coverage: `main.jsx`, `themes.js`, `pages/__design.jsx`, `components/icons/JournalIcons.jsx`, the framer-motion-only journal primitives (`StreakFlame`, `DeckleDivider`, `PageTurnTransition`), `assets/**`, `motion/**`, and the `test/` scaffolding itself.
- **Async test budgets:** `setup.js` gives RTL `findBy*` / `waitFor` conditions 4 seconds; `vitest.config.js` gives complete tests 15 seconds. These apply locally and in CI so multi-step UI/API flows tolerate shared-runner coverage load. Wait for observable state rather than sleeping before assertions; delayed MSW responses in ParentDashboard and Meadow pin both budgets. Keep explicit shorter timeouts when they are part of a test's behavior, and do not add retries to hide failures.
- **Animations:** stub `AnimatePresence` per file when its exit animation would block synchronous unmount assertions:
  ```js
  vi.mock('framer-motion', async () => {
    const a = await vi.importActual('framer-motion');
    return { ...a, AnimatePresence: ({ children }) => children };
  });
  ```
- **Modals:** components that `createPortal(…, document.body)` (BottomSheet, ConfirmDialog, plus any domain `*FormModal.jsx` that uses BottomSheet internally) — query their backdrop/contents off `document.body`, not the RTL container. Prefer role-based queries (`getByRole('dialog', { name: title })` for BottomSheet; `getByRole('alertdialog', { name: title })` for ConfirmDialog) since both primitives now wire `aria-labelledby` via `useId`.
- **Patterns to reuse:** for click-outside handlers that listen on `document` for `mousedown`, dispatch a synthetic event (`outside.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`) inside `act(...)`. For pages that poll on an interval, install `vi.useFakeTimers({ shouldAdvanceTime: true })` BEFORE mount so the component's `setInterval` is scheduled with fake timers.
- **Atlas vocabulary tests** — the cohort under `components/atlas/` exposes stable data attributes so pages can pin their application without reaching into class strings (which churn with the tokens). `IlluminatedVersal` carries `data-versal="true"` plus `data-tier="locked|nascent|rising|cresting|gilded"` and `data-progress` (the rounded percent). `BadgeSigil` carries `data-sigil="true"` plus `data-earned` / `data-rarity`. `RarityStrand` exposes `data-rarity={key}` on each segment. Smoke pattern for "the apply landed": `container.querySelector('[data-versal="true"]')` + assert on `data-tier` / `data-progress`. Tier assertions are the most stable axis — they don't shift with theme tuning. For rarity halo wrappers (Companions, Mounts, Codex), `container.querySelectorAll('[class*="ring-royal"], [class*="ring-moss"], [class*="ring-sheikah-teal"]')` counts the haloes without binding to the exact halo class. Reference patterns: `ProjectHeader.test.jsx` (data-tier per status), `Companions.test.jsx` (halo class count), `AccordionSection.test.jsx` (chapter numeral toggle), `HeroPrimaryCard.test.jsx` (next-action versal initial).
- **CI:** `.github/workflows/ci-cd.yml` has a `frontend-test` job that runs `npm ci && npm run lint && npm run test:coverage`; the `build` job declares `needs: frontend-test`, so a coverage-threshold failure blocks deploy. When adding new pages/components, write tests in the same PR — the gate will catch missing coverage if it dips below the threshold.
- **Interaction tests (REQUIRED for any clickable element that triggers an API call).** Render-only smoke tests cannot catch silent no-ops (button wired to `undefined`), wrong-endpoint bugs, or wrong-body-shape bugs — and we shipped both at once on Dashboard + Habits before the rule was written. For every interactive element that fires a POST/PATCH/DELETE, add a test that:
  1. Renders the page with realistic data so the element appears (use `factories.js` builders).
  2. Uses `spyHandler(method, urlPattern, response)` from [`src/test/spy.js`](src/test/spy.js) for the call under test — it captures `{ url, method, body }` per request into `spy.calls`.
  3. Calls `await user.click(screen.getByRole('button', { name: ... }))`.
  4. `await waitFor(() => expect(spy.calls).toHaveLength(1))`.
  5. Asserts on `spy.calls[0].body` (exact shape) and `spy.calls[0].url` (regex) — both must match what the backend route actually consumes (cross-check against `apps/<x>/views.py` if unsure).
  Default permissive MSW handlers in [`handlers.js`](src/test/handlers.js) stay for smoke tests; only override with a `spyHandler` when verifying an interaction. A page that renders 5 buttons that each fire a request needs 5 interaction tests in addition to its render test. Reference patterns: [`Dashboard.test.jsx`](src/pages/Dashboard.test.jsx) (`tapping a habit on Today...`) and [`Habits.test.jsx`](src/pages/Habits.test.jsx) (`clicking virtue...`).

## Conventions

- **Calendar copies:** `components/AddToCalendar.jsx` uses `utils/calendar.js` for a Google event link and an Apple-compatible `.ics` download. Supply a minimal event from already-authorized, saved data: `{id, title, start, end?, description?, path?}`. Date-only starts stay all-day with an exclusive next-day end; zoned timestamps become UTC, with a default 30-minute reminder window. These are one-time copies, not subscriptions. Caller-authored app paths retain only known navigation tabs; never pass credentials, the current URL, private journal content or parent-only notes. Duties use an editable reminder day validated against their ISO-week schedule (`pages/choresCalendar.js`), because recurrence and the reference on-week are not due dates.

- Import endpoint functions from `frontend/src/api/index.js` (single source of truth) rather than calling `api.get`/`api.post` directly in pages. Use shared components/helpers from `components/`, `constants/`, `utils/` rather than duplicating.
- **Form inputs:** use `<TextField>` / `<SelectField>` / `<TextAreaField>` from `frontend/src/components/form` rather than `<input className={inputClass}>` + hand-rolled `<label>`. The primitives wire `htmlFor`/`id` via `useId`, expose `error` / `helpText` slots with proper `aria-invalid` / `aria-describedby`, and stay in lockstep via the shared `formLabelClass` constant. Justified retentions (file pickers, color pickers, user-data-seeded `<input type="color">`) keep raw markup with a `// intentional:` comment.
- **Buttons:** use `<Button variant="primary|secondary|danger|ghost|success" size="sm|md|lg">` for text buttons and `<IconButton aria-label="...">` for icon-only affordances. The `buttonPrimary`/etc. class strings in `constants/styles.js` are internal (Button/IconButton-only consumers); don't import them into pages. `<motion.button>` wrappers are exempt from the migration — animation primitives stay raw.
- **Cards:** page-specific `*Card` components live as sibling files in their owning `pages/<area>/` subfolder and are imported by the one parent that uses them. Promote to `components/cards/` on the second consumer, not the first. Shared constants between a parent and its extracted cards go in `<area>/<name>.constants.js` (not exported from `.jsx` — the `react-refresh/only-export-components` lint rule forbids it).
- **Type sizes:** use `text-micro` (10px) / `text-tiny` (11px) / `text-caption` (12px) / `text-body` (14px) / `text-lede` (18px) from the `@theme` block rather than arbitrary `text-[Npx]`. If a needed size isn't on the scale, add a token to `@theme` rather than inlining.
- **Spacing tiers:** use three rhythm tiers consistently — `tight` (gap-2, space-y-2 — dense lists, form field groups inside modals), `default` (gap-3, space-y-3 — cards, standard sections, most page content), `loose` (gap-4, space-y-4 — page-level sections, Settings). `PageShell` already enforces this via its `rhythm` prop (`tight`/`default`/`loose`). Inside `PageShell`, prefer the tier that matches the content density rather than mixing arbitrary gap/space values.
- **Tests:** write a colocated `*.test.{js,jsx}` next to any new component, page, hook, or util. Use `frontend/src/test/render.jsx` + `factories.js` rather than inlining provider trees and fixtures. Mock `@sentry/react` is already installed globally — don't re-mock per file. When adding an ARIA attribute to a primitive, query by role (`getByRole('status'|'alert'|'progressbar'|'dialog'|'alertdialog')`) rather than CSS class — matches screen-reader semantics and doesn't brittle-break on styling changes.

## Key entry points
- `src/main.jsx`, `src/App.jsx`.
- `vite.config.js`, `vitest.config.js`.
- `src/test/{setup,server,handlers,render,factories,spy}` — test scaffolding.
- `src/themes.js` — `applyTheme`, `LEGACY_THEME_ALIASES`.
- `src/components/README.md` — canonical design-system doc.
- For page-level architecture see [`src/pages/CLAUDE.md`](src/pages/CLAUDE.md).
