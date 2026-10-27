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

## Native development prototype (October 2026)

React remains the full application UI. The lazy companion presentation uses
React Three Fiber 9 with React 19 and Three.js; Capacitor 8 packages the web
renderer, not React Native. The Android and iOS shells are development projects
identified as `digital.neato.abby.prototype` / **Abby Prototype**. They do not
establish mobile parity or signed-release readiness.

From `frontend/`, build and copy local assets with an explicit isolated staging
backend. PowerShell example (replace the reserved example origin):

```powershell
$env:ABBY_NATIVE_ENVIRONMENT = 'staging'
$env:ABBY_NATIVE_API_ORIGIN = 'https://staging.abby.example'
npm run native:sync
npm run native:android  # Android Studio, SDK 36 and supported JDK required
npm run native:ios      # Run on macOS with Xcode for signing/device installation
```

`npm run build:native` builds only `dist-native/`; the existing `npm run build`
continues producing Django's `/static/` web build in `dist/`. Native mode reads
the two explicit shell variables above, rejects missing/credential-bearing/
non-HTTPS origins and the known production host, and skips web `.env` files.
It binds `VITE_API_URL` to that origin for API calls, pagination and the public
sprite catalog. Staging isolation and synthetic accounts must be verified on
the selected server; a hostname/configuration check does not verify its data.

The Capacitor configuration has no `server.url`; built assets are copied into
the app. Native boot disables service-worker generation/registration, browser
install/update prompts and Web Push initialization/teardown. Existing web PWA
privacy-cache purges, shared browser sessions and worker checks remain active.
Google account sign-in/linking requires the hosted same-origin browser return;
the frontend refuses native or cross-origin Google redirects. Its browser
transaction uses an S256 proof and a single-use exchange, with callback values
scrubbed before telemetry. See `src/pages/CLAUDE.md#google-authorization-return`.
Allow only the selected local WebView origins in staging Django/media CORS
(Capacitor defaults: `capacitor://localhost` on iOS, `https://localhost` on
Android); validate API and model/media requests separately.

Use isolated synthetic staging identities: this prototype still uses the
legacy rotating DRF token and browser-style credential storage. Independent
secure device sessions, native push, OAuth/system-browser return transactions,
durable drafts, file/share/download adapters, back/deep links, signing and full
workflow acceptance remain gated follow-up work. Do not distribute this shell
as a production mobile application or use production credentials.

Validation: `npm run test:native-config`, affected colocated Vitest checks,
`npm run lint`, `npm run test:run` or the coverage gate, both web/native builds,
and `npx cap sync`. Real iPhone/Android installs, keyboard/safe-area behavior,
capture/save recovery and graphics/performance measurements remain required;
generated projects and desktop viewport checks do not satisfy those gates.

The lazy avatar, companion and pedestal scenes import `src/three/console.js`.
Stable R3F 9 still constructs Three's deprecated `Clock` before `onCreated`;
`Timer` is not compatible with that clock API. The shared Three console hook
filters only its exact deprecation warning and preserves other diagnostics.
Remove the filter when the installed stable renderer migrates away from Clock.

## Source layout
```
frontend/src/
  api/
    client.js        Fetch wrapper with token auth, 401 self-heal
    index.js         All endpoint functions (single import surface)
  hooks/             useApi.js (useAuth, useApi),
                     useParentDashboard.js (parallel-fetch merge of
                     all parent review and delivery sources, shared by
                     ParentReviewProvider with Today/header/navigation),
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
                     Dropdown (themed combobox/listbox used by SelectField),
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
                     DailyChallengeCard, PinnedChallengeCard (automatic goal/bonus state).
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
                     the registerPromptWorker seam and update guards.
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
- **Shared browser session:** tabs on the same origin share the browser token; Unity is retired and no longer consumes it. Delayed 401s and logout responses clear only the token they used, preserving a newer sign-in. `AuthProvider` reloads on an external tab's auth-token change or localStorage clear, keeping the rendered user/role aligned with the credential. It also drops the cached user snapshot so offline boot cannot hydrate the previous account.
- **Offline identity:** `AuthProvider` stores the last verified user in a versioned `{ token, user }` envelope bound to the exact credential that fetched it. It restores that identity only after a network failure with the matching token. Legacy snapshots and mismatched credentials are rejected; anonymous boots never accept a cached `/auth/me/` success. Login, signup and OAuth replacement clear the old snapshot before installing the new credential. `sessionError` carries OAuth/logout push-cleanup failures to the Login page.
- **Private API responses:** API reads are network-only; the generated worker has no `/api/` runtime cache route. `public/privacy-sw.js` deletes legacy `api-reads` caches on activation and `pwa/privacy.js` also purges them at boot/session changes. Until a prompted worker upgrade activates, `api/client.js` adds a random noncredential `_abby_session` query key to GETs and blob downloads. The key rotates with the credential and page lifetime and replaces an echoed pagination key, so an old URL-only worker cannot match another account's response. Static assets, images and fonts retain their offline caches.
- **Upstream HTML recovery:** A deployment proxy can return an HTML error page with a successful HTTP status. The JSON client retries a GET once using a fresh noncredential `_abby_retry` query key, preserving its credential, cancellation signal and `no-store` policy. It stops if the credential changed or the request was cancelled, and never retries mutations or ordinary HTTP/network errors. Recovered reads leave a warning breadcrumb; persistent malformed responses still reach Sentry and show a temporary-unavailability message. This does not change the upstream proxy's status or cache configuration.
- **Gateway statuses during a deploy:** a deploy swaps containers while tabs keep polling (the 30s `/api/pulse/` beat most of all), so the proxy answers in-flight reads with 502/503/504. A request that passes `retryGateway: true` (today only `getPulse`) is retried once after `GATEWAY_RETRY_DELAY_MS`, leaving a warning breadcrumb, with the same credential and cancellation checks as the HTML recovery above; mutations, other requests and every other status are never retried. A gateway status that persists after the retry is thrown; for an opted-in GET the client no longer captures it itself but attaches `err.deferredReport` (`{error, extra}`, with `extra.attempts`) for the caller to report (see THE-ABBY-PROJECT-3X below). Any other 5xx, and every non-opted-in request, is captured at once as before. Sentry issue THE-ABBY-PROJECT-3V (GitHub #296, repeated `API 504: GET /pulse/`) was this shape; the cause is inferred from its status, route and timing against the deploy window, not reproduced against a live proxy. The same opt-in also pauses the HTML-recovery retry for `GET`s by `GATEWAY_RETRY_DELAY_MS` (callers without it keep the immediate retry): THE-ABBY-PROJECT-3W (GitHub #298) was `/api/pulse/` answering HTML 200 on both attempts, which an immediate replay can land inside one deploy window. As with 3V, the deploy-window cause is inferred, not reproduced against a live proxy; the regression test simulates a short HTML outage. THE-ABBY-PROJECT-3X (GitHub #303) was the same `/api/pulse/` HTML 200 on both attempts, seen during the deploy of #294 — the deploy window outlasted the one paused retry, so tuning the retry delay cannot close this class. A persistent HTML 200 on an opted-in GET therefore also attaches `err.deferredReport` instead of capturing, and `PulseProvider` captures it once when `PULSE_OUTAGE_BEATS` (3) consecutive beats fail (`extra.consecutiveFailedBeats`; the same Sentry message and grouping), resetting on any successful beat or account change. A real outage still reaches Sentry after about a minute; a deploy swap does not. Writes never defer. As before, the deploy-window cause is inferred from route/status/timing, not reproduced against a live proxy.
- **401 self-heal in the fetch wrapper** ([api/client.js](src/api/client.js)): when any API call returns 401 AND the request carried an `Authorization` header AND its token is still the stored credential, the client clears `abby_auth_token` and calls `window.location.reload()`. `AuthProvider`'s boot flow then lands on the Login page with no stale token in localStorage. This is the recovery path for users whose stored tokens go invalid (e.g., after a Coolify redeploy we haven't pinned down yet) — without it, non-technical users had to manually purge all site data to escape "Invalid token" loops. The **"only if Authorization was sent"** guard is load-bearing: it prevents boot-time `getMe()` 401s (no header → no reload) from entering an infinite reload loop, and lets the Login page surface "Invalid credentials" without self-reloading. Tests live in the `401 self-heal` describe block of [api/client.test.js](src/api/client.test.js).
- **API error shape** ([api/client.js](src/api/client.js)): every non-2xx response throws an `Error` augmented with two extra fields — `err.status` (HTTP status code as a number) and `err.response` (the parsed JSON body). Callers can branch on specific codes — e.g., `JournalEntryFormModal` catches `err.status === 409` and reads `err.response.existing` to flip into edit mode, and the same modal catches `err.status === 403` for the "entry locked after midnight" case. The default `.message` still carries the human-readable text (`error`/`detail`/stringified body fallback) so generic `catch { toast(err.message) }` paths keep working. When adding a new branching check, prefer status over string-matching `.message`. **For a 400 on a form**, use `fieldErrors(err)` from [utils/api.js](src/utils/api.js): DRF answers with `{field: ["message"]}`, which has no `error`/`detail` key and so falls through to the `JSON.stringify` fallback — the user reads raw JSON in a banner unless the form maps each message onto its own input's `error` prop. Reference: [`PrinterConfigPanel.jsx`](src/pages/forge/PrinterConfigPanel.jsx).

## Design system (`components/README.md` is the canonical doc)

`/__design` is an interactive synthetic pattern library with six-theme and
content/layout previews. It shows complete data, form, dialog, notification,
family-context and page-composition patterns, plus imports and real consumers.
Use its recipes and the adoption checklist in `components/README.md` when
changing a screen; keep examples aligned with actual shared components.

### UI language (October 2026)

Use warm, straightforward language that fits the Meadow presentation. Name the
feature or action directly in navigation, headings, buttons, help, errors,
notifications and accessible labels. Use sentence case. Avoid manuscript or
adventure metaphors for everyday tasks and status (for example, use “Save”,
“Earned” and “Request reward” instead of “Inscribe”, “Sealed” and “Barter”).

| Current display name | Legacy display name / stable route |
| --- | --- |
| Tasks | Quests / `/quests` |
| Homework, Chores, Habits, Projects, Challenges | Study, Duties, Rituals, Ventures, Trials (existing tab IDs) |
| Pets | Bestiary / `/bestiary` |
| Rewards | Treasury / `/treasury` |
| Payments, Timecards, Shop, Inventory, Savings goals | Coffers, Wages, Bazaar, Satchel, Hoards (existing tab IDs) |
| 3D Prints (Rewards) | Forge / `/treasury?tab=forge`; old Tasks links redirect |
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

The October 2026 Meadow refresh shares bundled Nunito, cream/lavender/mint surfaces, rounded controls and collection tiles across React and the companion presentation. All legacy font aliases resolve to Nunito. React uses the variable font's real 200–1000 weight range for body copy, labels and headings; The retired Unity reference retains the shared weight-600 export. Both come from `shared/storybook/fonts`, with runtime copies maintained by `scripts/storybook/sync_presentation.py`. The bundled React `.ttf` is precached for offline typography.

The replaceable Meadow presentation also supplies the welcome screen. Its licensed chick is a generic artwork preview, not evidence of an account's owned species or growth. Today and Bestiary render actual server-confirmed companions through their species `sprite_key`. Exact Base Chick and the 14 registered Meshtint families use their pinned stage portraits when the private releases and retained Chick supplemental portraits are installed. Missing or failed portraits recover through registered runtime artwork and a labelled icon. The generic registered-art renderer remains available after the separate prelaunch cleanup removes the explicitly retired first-party content. Saved cover keys and cosmetic ownership stay unchanged: `hyrule`/`vigil`/`sunlit`/`snowquill`/`verdant`/`harvest` now display as Memory/Twilight/Honey/Cloud/Clover/Peach Meadow. Django and React share these labels and seasonal aliases through `shared/catalog/theme-presentation.json`, copied into React by `scripts/storybook/sync_presentation.py`. Baseline art/palette data remains in `shared/storybook/presentation.json`; `themes.js` adds semantic shades for readable UI.

`RpgSprite` defaults to smooth image scaling; use `rendering="pixelated"` explicitly for artwork that needs crisp pixel edges. Today and Companions use `petSpriteKeys` for retained pet rows. The shared pure-data `companion/birdEvolution.js` resolves the exact Chick/Base identity from server-confirmed `evolution_stage` and `evolved_to_mount`, never growth alone, for 2D portraits, 3D selection, form names and the existing Bird motion adapter. The generic `companion/lifecycle.js` and four-stage `PetEvolutionGuide` use `shared/catalog/companion-lifecycle.json` for Egg → Baby → Middle → Grown across every species; `lifecycle_stage` comes from the server. Egg is the pre-hatch inventory stage, with family art names kept separate from stage IDs. See `docs/operations/companion-lifecycle.md`. Nicknames remain separate from stage names; saved species/potion identities do not change. Missing or failed portraits try `fallbackSpriteKey` before a labelled icon. Failures belong to the image URL, so a fresh catalog URL can recover. `JournalIcons` keeps its named exports with rounded Meadow SVG drawings, readable current-color outlines and soft cover-token fills. Use its shared chapter icons in navigation and `CoinIcon` for progression currency; real money keeps its dollar icon. `ChapterMarker` replaces manuscript section marks with decorative rounded number badges; `chapterMark` returns one-based Arabic labels for headings, chapter taxonomies and shelf medallions. Shared `TabList` uses one tab stop, Left/Right arrows with wrapping, Home/End, automatic selection and reduced-motion-aware active-tab scrolling.

**Achievement card artwork:** private family `abby-achievement-card-kit` 1.0.0
adds matching wide (1024×512) and tall (1024×1280) base/overlay pairs plus three
512px icons. `avatar/achievementCardKit.js` resolves their explicit `wide`,
`tall`, and `icon-512` variants through image URLs; the older pedestal resolver
assumes square canvases, and `loadAsset` accepts GLBs only. Use the shared
`AchievementCard` surface for wide Profile achievements and tall collection,
challenge, and reward cards. Preserve 64px corner slices, scaled 96px safe
insets, alpha, and live text/state/actions. Existing catalog artwork stays
distinct; generic book/heart/compass icons establish no badge assignment or
entitlement. See [the integration runbook](../docs/operations/achievement-card-kit.md).

**Supported offers and saved collections:** use Django's read-only
`catalog_available` fields through `utils/catalogAvailability.js`; React does
not infer acquisition eligibility from an icon or model filename. New pet
offers cover 15 Base-potion families: Chick and the 14 exact namespaced
identities in `shared/catalog/companion-roster.json`. Server-confirmed
`lifecycle_stage` selects their Baby/Middle/Grown presentation; the compatible
Chick `evolution_stage` selects Chick below 50 growth, Fledgling from 50,
and Bird after confirmed evolution at 100. See
`docs/operations/companion-lifecycle.md` and `docs/operations/bird-evolution.md`.
The owner-approved prelaunch retirement removes the explicit unused first-party
species, eggs, potion types and pet accessories. Saved collection components
remain for other unavailable/custom rows with their existing care, activation
and expedition controls; they are not a promise to preserve the retired list.
Unknown identities never receive the Chick/Bird model. Collection counts use
supported rows and the server's supported `total_possible`.
Profile offers Frames and Titles; Settings → Appearance is the single Color
theme selector. Any remaining unavailable custom cosmetics retain removal of a
previous selection. Inventory retains unavailable
items but omits their blocked action. Shop, challenge and badge surfaces respect
availability without presenting unreachable unlocks. See the
[asset boundary](../content/rpg/react-three-fiber-assets.md) and
[shared contract checks](../contracts/api/README.md) before extending offers.

**Earned identity:** navigation uses the current account's saved look from the
existing account-bound pulse. The header, account menu, sidebar and Profile
share `IdentitySummary`, `IdentityPortrait` and `IdentityChips`: the equipped
frame surrounds the picture, a confirmed level docks beneath it, and soft chips
show the full title and featured badge with their existing catalog artwork.
The header uses only the title and badge icons beside the portrait on the existing row,
with accessible title/badge names and hover labels. Phone headers omit the
account-name text; the profile-menu trigger retains its full accessible
description, and the menu and Profile keep full name/title/badge labels.
`pulse.header.level`
comes from the signed-in account; zero is valid and missing levels stay hidden.
Only a pulse identity matching the current user may supply navigation's saved
look or level. Today leads with task guidance below its
heading. Successful Profile equip/unequip/trophy writes refresh the pulse;
failed writes do not change navigation. Project-detail `maker_signature` represents the assigned
child, with the same family access checks as the project, and is read-only.
Shared `components/identity` portraits draw distinct vector ornaments inside
their layout footprint, with a protected photo opening and an initial fallback.
Titles keep live text and their own catalog icon. The frame collection previews
these same portraits. This presentation adds no ownership or reward mutations.

**Rarity feedback:** badges use the server's `coin_bonus` as a base bonus, never
as evidence of a historical payout. Challenge reward previews and future
receipts carry `item_rarity` and exact catalog identity; shared `RewardItem`
also handles expedition fields and sparse older receipts without inventing a
tier. Drop reveals retain nullable `salvage_coins`, display server-provided
effect summaries and link to the existing explicit inventory/profile/pet
controls. They do not consume or equip an item. Inventory offers All / Rare+
and Recently updated / Rarest; its timestamp is not an acquisition date.
Food choosers and inventory display authoritative `effect_summary` without
calculating growth in React. Locked cosmetics prefer current
`acquisition_sources` hints and internal navigation; rarity alone establishes
no earning path.

**Pet interactions:** the Pets home opens its exact owned appearance automatically.
Tapping says hello; Hop/Fly together and Look around use only staged, manifest-named
supplied takes. Each take keeps its complete matching rig and the idle framing.
Retained licensed bird turns reverse before returning to idle; shared Bird and
roster playback preserve their manifest-declared motion and native loop behavior.
Play is repeatable local presentation,
with no progression or currency mutation. Motion respects reduced-motion,
hidden/offscreen/background state and the View setting. Feed and expedition
actions remain explicit DOM controls; acknowledgements follow successful server
receipts. Grown pets show today's expedition directly on their home. Server
availability/relative deadlines govern daily start and return refreshes; the
phone clock never grants a trip or claims its loot.

Missing hatching supplies and food link to Tasks and challenge rewards.
Confirmed hatches offer a care link with `?tab=companions&pet=<owned-id>`;
Companions resolves that ID only against the signed-in stable and removes it
when care closes. A successful feed into the server-confirmed Middle stage
shows a quiet text acknowledgement, including in the DOM fallback. Earned
egg/potion and food receipts link to Hatchery or care; previews, salvaged items
and parent views of a child's rewards never offer self-use actions. Collection
read failures show retry controls and preserve loaded rows during refresh.

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

### Hatchery discovery

Hatchery's Explore companions section is visible only to staff users and browses
their supported codex independently of inventory. BestiaryHub enables this
presentation only when the authenticated user's `is_staff` is `true`; Hatchery
hides it by default. All users retain their owned eggs, compatible potion choices,
incubation, and hatching controls. With the section, the recipe shows the egg
icon, recipe selections focus the section's single preview, and a skip link
passes over the section. Without it, parents see the selected owned egg's
family preview with its chosen potion; children follow the surprise rule below.
Only server-returned available potion pairs
are offered. A typed, presentation-only natural egg projects exact registered
family artwork; it never supplies inventory IDs to incubation. Recipe selections
can focus that preview, while browsing never changes the recipe or makes a write.
The single family preview is portrait-first and supports Egg/Baby/Middle/Grown;
optional 3D keeps the existing exact bindings, motion controls and reduced motion.

**Child surprise previews:** `companion/previewAccess.js` applies the owner's
rule to non-staff children (`useSurpriseRestricted`). Companion art, 3D and form
names appear only for an exact species/potion appearance in the child's stable,
up to its server-confirmed stage (`ownedAppearanceStages`); growth counters,
codex discovery, a null/blank legacy potion slug and missing or failed stable
reads unlock nothing. `FamilyStagePreview` takes a `stages` allowance and clamps
its selection every render; `PetEvolutionGuide` keeps generic stages and
thresholds but withholds unreached form names (`revealedStages`, or a
creature's own stages). Collection draws only an exact owned appearance
(`SpeciesPortrait`) and locks unowned grown forms without loading their art.
Challenge cards, detail sheets and Today's pinned card use
`useChallengeSurprise`: an elemental challenge illustration (it depicts the
Baby) appears only once that exact appearance hatched, and a catalog
description clause naming a later or elemental form (Shadow Trail, Ember/Frost
Summit) is dropped until reached. `useSurpriseOwnership` shares one stable read
across surfaces that mount together and reveals nothing until it loads. Django
applies the same rule to Guide copy (`apps/lorebook/services.py`), so the Guide,
practice trials and the Manage Guide route all receive the child's text.
See `docs/operations/companion-lifecycle.md`.

Each codex potion's additive acquisition_challenges lists current guaranteed
bundles separately from saved attempts. Automatic attempts freeze their name,
target and reward items; historical legacy quests freeze reward items only and
retain the existing Trials name/target behavior. Show the returned attempt's name,
target and progress; follow its server path rather than inventing goal IDs. No saved
attempt means unknown progress, not zero. Discovery must not call the materializing
GET /api/challenges/ merely to browse. Owned and incubating states come from the
existing stable/incubation responses; failed reads stay explicitly unknown.
Accepted ready hatches remain usable while the discovery catalog loads or fails.
The owner-accepted Bee/Bat adoption adds their four exact elemental pairs and
one-time Hive/Cave guarantees through the server policy. Runtime delivery still
requires canonical publication/readback and the ordinary MAIN release gates.

The owner-accepted Snake/Hermit Crab release is the fourteenth canonical runtime
pin. The positive server policy supports thirty-one exact species/potion pairs;
Coil/Shore challenges guarantee each new natural egg and global Fire/Ice potion
bundle once after ten qualifying accomplishments within 180 days. React uses
server-confirmed offers, incubation readiness, hatch receipts and species-wide
expedition allowance; it grants no progress from artwork or rarity.

The separate `assets.snake-hermit-crab.evaluation.lock.json` preserves the
historical private review pin alongside the earlier evaluation locks. Ordinary
runtime and canonical browser checks use active-lock defaults without an explicit
staged prop. The optional loopback fixture routes art by exact family and image
identity. Native takes come from `appearance_bindings` v1 without renaming source
IDs; the Middle Snake's supplied `slither-foward-*` spelling is intentional. No
Evolve clip is supplied, so confirmed growth selects that element's destination
idle. Missing exact art retains care/claim controls. Physical-phone and native
shell acceptance remain separate from desktop/browser evidence.

Ghost/Potted Plant receiving preparation uses
`shared/catalog/elemental-ghost-potted-plant.json`, with its manifest unset and
acquisition/artwork acceptance disabled. Neither an active nor an evaluation
release pin exists yet. Ordinary runtime delivery stays unavailable; synthetic
tests supply an explicit fixture and establish contract behavior only. The
exact natural eggs remain `meshtint-ghost-egg` and
`meshtint-potted-plant-egg`; their form names and server-confirmed stages remain
Ghost/Spook/Phantom and Seed/Sprout/Flower Pot Monster. Future challenge image
handles depict only the Baby appearance and obey the existing exact-pair child
surprise restriction. Missing exact portraits never fall back to a tinted Base
image. Wisp/Sprout guarantees and shared expedition limits remain server-owned;
receiving registration cannot activate them or grant ownership.

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

The app surfaces reveal/toast components mounted near the top of [`App.jsx`](src/App.jsx) so big-moment notifications don't sit lost in the bell. These respect the global `prefers-reduced-motion` rule in [`index.css`](src/index.css):
- [`CelebrationModal`](src/components/CelebrationModal.jsx) — full-screen reveal for `streak_milestone` (3/7/14/30/60/100) + `perfect_day`. At App boot it polls `GET /api/notifications/pending-celebration/` (returns the most recent unread streak/perfect-day notification — sister to `/api/chronicle/pending-celebration/`); dismissing fires `markNotificationRead`.
- [`PetCeremonyModal`](src/pages/bestiary/PetCeremonyModal.jsx) — sequenced reveals for `hatch_pet` (sparkle) and `evolve` (crown halo), launched from `Hatchery` and `Companions`. Tap-anywhere dismiss. See `apps/pets/CLAUDE.md` for the three modes (hatch/evolve/expedition_return).
- [`RareDropReveal`](src/components/RareDropReveal.jsx) + [`rareDropTiers.js`](src/components/rareDropTiers.js) — escalates `rare`/`epic`/`legendary` drops out of the slide-in [`DropToastStack`](src/components/DropToastStack.jsx) into a center-screen card with rarity glow, queued so multiple rares don't collide.
- [`DailyChallengeCard`](src/components/dashboard/DailyChallengeCard.jsx) shows Today's automatic bonus with actual paid Coins/XP and no Claim action. `PinnedChallengeCard` features the chosen goal without controlling whether work counts. The old claim modal is retained only as a legacy component.
- [`ApprovalToastStack`](src/components/ApprovalToastStack.jsx) + [`useApprovalToasts`](src/hooks/useApprovalToasts.js) — child-side toasts for chore/homework/creation/exchange/redemption approvals + rejections, polled from notifications. Seen-IDs persist in `localStorage` per the keys in [`constants/storage.js`](src/constants/storage.js) so a refresh doesn't re-show them.
- [`QuestProgressToastStack`](src/components/QuestProgressToastStack.jsx) + [`useQuestProgressToasts`](src/hooks/useQuestProgressToasts.js) — 4s floater on every active-quest progress increment ("+10 toward Dragon Slayer 62%") so contributing actions feel tied to the quest rather than vanishing into a stat. Driven by polling `getActiveQuest()` for delta detection on `current_progress`.

Plus a small framer-motion equip toast on [`Character.jsx`](src/pages/Character.jsx) — "Now wearing X" floats up on every cosmetic equip/unequip.

## PWA / installable app

[`frontend/src/pwa/`](src/pwa/) + [`vite.config.js`](vite.config.js) + [`config/urls.py`](/config/urls.py). `vite-plugin-pwa` runs in `registerType: 'prompt'` mode with `injectRegister: false` — the SW + manifest are emitted at dist root (NOT under `/static/`) because a service worker MUST serve from `/` to claim root scope and the manifest needs `application/manifest+json`. PWA root files (`sw.js`, `push-sw.js`, `privacy-sw.js`, `registerSW.js`, `manifest.webmanifest`, three icon PNGs, `apple-touch-icon.png`, `favicon.svg`) are routed through a dedicated `_pwa_static_serve` view in [`config/urls.py`](/config/urls.py) that's wired BEFORE the SPA catch-all. **`sw.js` carries `Cache-Control: no-cache`** stamped explicitly by that view so the browser revalidates on every page load — without this, users get stuck on a stale SW that controls a bundle that no longer exists. The `apple-touch-icon` is a 180x180 PNG, never the SVG (iOS rejects SVG touch icons silently). The five providers/components mounted in [`App.jsx`](src/App.jsx):

- **`PwaStatusProvider`** ([`pwa/PwaStatusProvider.jsx`](src/pwa/PwaStatusProvider.jsx)) — registers the generated `/sw.js` through [`registerPromptWorker`](src/pwa/registerPromptWorker.js), exposing `{updateReady, offlineReady, updateBlocked, updateError, registerUpdateGuard, applyUpdate, dismissOfflineReady}`. Development and native runtimes skip browser registration. The native registration seam detects waiting/installed workers and posts `SKIP_WAITING`; it never reloads. The installed plugin's prompt client reloads on control even when given `false`, so it cannot own this flow. The provider (a) refuses activation while dirty/busy guards are active, (b) checks guards again before its `controllerchange` or 1.5s fallback reload, retaining an explicit retry if work opened during activation, and (c) stamps `pwa:last-reload-attempt` in localStorage with a 60s suppress window against repeated deployment prompts. The stamp is cleared when that repeated prompt is suppressed. Guards retain only IDs and booleans, never form data. `BottomSheet` and `useFormState` register automatically; manual forms use [`usePwaUpdateGuard`](src/pwa/usePwaUpdateGuard.js).
- **`UpdateBanner`** ([`pwa/UpdateBanner.jsx`](src/pwa/UpdateBanner.jsx)) — in-flow `role="status"` banner above the page, shown when `updateReady === true`. Reload calls `applyUpdate`; dirty/busy work disables it and explains how to continue. A failed activation leaves a useful retry message. Renders `null` when no update is waiting.
- **`OfflineReadyToast`** ([`pwa/OfflineReadyToast.jsx`](src/pwa/OfflineReadyToast.jsx)) — one-shot `NotificationToast` confirming the app shell was saved on the device. Tasks and memories still require a connection; no offline write queue is implied. Auto-dismisses after 4s.
- **`InstallPromptProvider` + `useInstallPrompt`** ([`pwa/useInstallPrompt.js`](src/pwa/useInstallPrompt.js)) — captures the browser's `beforeinstallprompt` event so the Settings page can offer a real Install button. **The early-capture in [`main.jsx`](src/main.jsx) is critical**: Chrome fires `beforeinstallprompt` very early after page load — often before `InstallPromptProvider`'s `useEffect` has run. `main.jsx` adds a window-level listener at module load time that stashes the event on `window.__deferredInstallPrompt`; the provider reads from there on mount. Without this stash the event is dropped on Chrome Android and the Install card falls through to "browser doesn't support" messaging. `detectStandalone()` checks both `navigator.standalone` (iOS Safari) and `matchMedia('(display-mode: standalone)')` (Chrome/Edge/Firefox).
- **`InstallCard`** ([`pwa/InstallCard.jsx`](src/pwa/InstallCard.jsx)) — Settings page card that handles five install cases: (1) already standalone → renders nothing, (2) `canInstall` → real Install button via `event.prompt()`, (3) iOS Safari → `Share → Add to Home Screen` instructions (iOS never fires `beforeinstallprompt`), (4) Android Chrome without prompt → `⋮ → Add to Home Screen` instructions, (5) anything else → soft fallback. The `isAndroidChrome()` UA detection deliberately excludes EdgeA, Opera, Samsung Browser, and Facebook in-app webviews because each ships its own install path (or none at all in webviews) and the generic Chrome menu instructions would be wrong.
- **Web Push** ([`pwa/usePushNotifications.js`](src/pwa/usePushNotifications.js) + [`pwa/PushNotificationsCard.jsx`](src/pwa/PushNotificationsCard.jsx)) — per-device opt-in on the Settings page. The SW handlers live in [`public/push-sw.js`](public/push-sw.js), pulled into the generated worker via workbox's `importScripts` rather than switching to `injectManifest`: generateSW stays in charge of the precache + update-prompt behavior documented above. `push-sw.js` is in the `_PWA_ROOT_FILES` list in [`config/urls.py`](/config/urls.py) so it serves from root with the SW's scope. The hook degrades in layers — `supported` (browser has the APIs at all; iOS needs the app installed to the Home Screen), `enabled` (server has a VAPID keypair), then the browser's own `permission` — so the card can always say something true instead of offering a dead button.
- **Push ownership:** `pwa/pushSession.js` verifies/rebinds an existing browser endpoint with the server before showing `subscribed=true`. Logout/account replacement stop new bindings, unsubscribe the current browser immediately, and queue endpoint removal after any pending bind. They send the captured `push_endpoint` when revoking the old credential; account replacement completes revocation before installing the new token. Server removal is scoped to the original user and this endpoint; other devices stay subscribed. Native unsubscribe works offline. A live endpoint requires confirmed ownership removal and token revocation; zero removals or an uncertain pending bind cannot establish safety. If cleanup cannot establish safety, account replacement is blocked with a useful error; logout still clears its local credential and reports the cleanup failure.
- **Registration tests** mock `registerPromptWorker` in provider tests and use synthetic worker events in its own tests. The legacy virtual-module stub remains for compatible reference consumers; production registration uses the native seam above.

The worker's root scope differs from the bundle's `/static/` base. Keep
Workbox's `modifyURLPrefix` mapping from `assets/` to `/static/assets/` aligned
with the URLs in the built HTML and lazy imports. For an offline browser check,
disable the browser HTTP cache while keeping Cache Storage intact; otherwise
warm HTTP responses can mask missing service-worker precache routes.

## Journal covers (`frontend/src/themes.js`)

6 cover palettes (`hyrule` / `vigil` / `sunlit` / `snowquill` / `verdant` / `harvest`) stored as `User.theme`; legacy values (`summer`/`winter`/`spring`/`autumn`) map forward via `LEGACY_THEME_ALIASES`. `applyTheme(name)` writes the active cover's colors to CSS custom properties on `<html>` — including a per-theme `tones` block (`goldLeaf`, `moss`, `mossDeep`, `emberDeep`, `royal`, `rose`) that used to be global constants in `index.css`. Vigil is the only dark cover and *inverts* `emberDeep` (light on dark) where light covers darken it — so `text-gold-leaf`, `text-ember-deep`, etc. render as chip text that passes contrast on every cover. Each cover is tuned to pass WCAG AA on three surfaces — `page` (body), `pageAged` (`ParchmentCard tone="default"`), and `pageGlow` (`ParchmentCard tone="bright"`, e.g. `HeroPrimaryCard`). The gate lives in [`src/test/themeContrast.test.js`](src/test/themeContrast.test.js): 216 assertions (every cover × every ink tier + accent tone × every surface) using [`src/utils/contrast.js`](src/utils/contrast.js)'s WCAG helper. **If you add a 7th cover**, supply the full `tones` block and the gate will refuse values that fail 4.5:1 (body) / 3:1 (chip text). The single Color theme picker lives under Settings → Appearance at `SettingsPage.jsx`; Profile and Inventory link to `/settings#appearance`. Profile owns picture upload/removal and the separately labeled character appearance. Palette display names come from `themes.js`, including Inventory and saved cover keepsakes; item IDs, ownership and stored keys stay unchanged. Selecting the active theme does nothing, saving disables other theme choices, and ownership load failures show an error/retry rather than locked themes. Each swatch renders a live sample (title + body + whisper + flame/coin/quest chips) in that cover's exact tones so users can eyeball readability before committing.

## Frontend testing (`frontend/`)

### Dedicated deployed browser checks

`npm run test:live-config` runs synthetic safety tests without network access.
`npm run test:live -- --credentials-file <absolute-0600-json-path>
--deployment-proof-file <absolute-0600-json-path> --result-file
<absolute-0600-json-path> --expected-commit <40-lowercase-hex>` runs the separate
`playwright.live.config.js` against `https://abby.bos.lol`. It requires the
reserved `abby-live-checks` family, `abby_loop_parent` / `abby_loop_child`, and
their provisioned IDs. Keep these files outside checkouts. The controller uses
an immutable reviewed harness installation; never give changed PR code these
credentials. Its root-owned `frontend/.abby-live-source.json` records
`{schemaVersion:1,sourceCommit:<harness-sha>}` independently of the expected
deployment SHA.

The suite signs in through the real forms, holds authenticated reads until
each identity is verified, and uses real deployed responses. Credentialed
fetches refuse redirects; request guards abort unexpected writes. The observed
uncredentialed, non-navigation Cloudflare JavaScript detection POST at or below
`/cdn-cgi/challenge-platform/h/g/jsd/oneshot` is discarded without forwarding
or failing the read-only smoke; other writes retain their failure checks. Health must
identify the expected commit and pinned Coolify application before login and
after browser checks. Each successful run uses four `/api/auth/` POSTs: two
logins and two token-revoking logouts. Dashboard reads can update only the
dedicated users' activity/profile state. This small smoke suite does not claim
cross-family or complete workflow acceptance.

The wrapper requires Linux, serializes shared-account runs with a private
per-user lock, and drains the Playwright/browser process groups before
unlocking. An uncleared group retains the lock for investigation. Browser
traces, screenshots, video, HAR and saved authentication state are disabled;
raw Playwright output is discarded and temporary artifacts removed. Only the
allowlisted result JSON is retained. Its expiry cannot exceed the deployment
proof's expiry or five minutes after completion. Existing `test:pwa` fixture
tests explicitly exclude the live suite and remain independent of deployed
credentials.

### Local application tests

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

Prepared companion roster: `companion/sharedRosterRelease.js` resolves the exact
14 namespaced family identities, server stages and global Base potion from
`shared/catalog/companion-roster.json`. `sharedRosterPlayback.js` loads each
native take with its own rig on demand and disposes replaced takes.
`FamilyStagePreview` previews Egg/Baby/Middle/Grown locally; no preview creates
ownership or progression. Hatching's `PetEvolutionGuide` resolves family form
labels only for exact registered egg identities and the selected potion's
`metadata.variant`; unknown/conflicting eggs keep generic stage labels and
the egg stage stays highlighted before hatching. Hatching and evolution preserve the exact saved companion identity. The existing Chick/Bird and pedestal pins remain
intact; seven retained portraits use the inventory-pinned private supplemental
import. Dummy is separate future training art with no product binding. Read
[the adoption runbook](../docs/operations/companion-lifecycle.md) for intake,
non-destructive reconciliation, rollback pins and remaining phone acceptance.
Run `ABBY_ROSTER_FULL_MOTIONS=1 npx playwright test e2e/roster.pw.js` with private
assets to exercise the actual current renderer; absent payloads explicitly skip.


Fire/Ice Chick and Wolf presentation uses the separately pinned
`abby-elemental-companions` canonical release and `sharedElementalRelease` /
`sharedElementalPlayback`, shared by Live and Hatchery previews. Exact
`appearance_bindings` v1 keeps potion identity separate from native `source-*`
take IDs. Each take owns its rig/materials/mixer; four Chick transition payloads
preload the confirmed destination, while reduced motion skips directly to it.
`sharedElementalPortraits` selects the declared `icon` variant at every size;
missing art never substitutes Base or a CSS recolor. Only exact elemental
Chick/Wolf identities receive those model/portrait bindings. The application registry also enables the four exact owner-accepted
Dragon/Mushroom elemental pairs through their separate pinned release. The pinned canonical release
is verified; application rollout uses the ordinary MAIN deployment gates.
Read [Fire and Ice companions](../docs/operations/fire-ice-companions.md) for
verification, remaining acceptance and rollback. With private art installed,
`ABBY_ELEMENTAL_FULL_MOTIONS=1 npx playwright test e2e/elemental.pw.js` exercises
all four families: 358 logical stage bindings / 356 native takes, plus
Live/Hatchery stages and the four Bird transition payloads. Public CI
without private art explicitly skips those browser acceptance scopes.

Dragon/Mushroom rollout uses the separately pinned
`abby-elemental-dragon-mushroom` 1.0.0 descriptor in
`shared/catalog/elemental-expansion.json` and the verified manifest
`bed65d84a4079dec2275f9dc4f3e3933c820cda378603eac790b263afa53ea05`.
The owner accepted all twelve actual app previews. This branch prepares their
positive-policy activation. Canonical index/manifest/payload readback and the
fresh standard import pass; keep the PR draft until fresh current-base validation
and independent review finish. The elemental adapters
select an exact family by species/sprite,
retain native motion identities (including Dragon Middle's `source-fly-idle`),
use unique logical motion IDs for aliased menu choices,
and preserve labelled unavailable presentation when its exact art is absent.
Hatchery hints require server-confirmed compatible variants. The private art
and physical-phone acceptance work is recorded separately in
[the preparation runbook](../docs/operations/elemental-dragon-mushroom.md).

Bee/Bat Fire/Ice uses `shared/catalog/elemental-bee-bat.json` and the accepted
`abby-elemental-bee-bat` 1.0.0 manifest
`7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5`.
Canonical publication/readback precedes adding its active pin alongside all
twelve earlier pins. The server policy enables 27 exact pairs; Bee's one-time
Hive guarantees require five qualifying accomplishments, Bat's Cave guarantees
ten, each within 180 days with a natural egg and global potion. The immutable
`review-...-acquisition-icon` handles remain distinct from quest identity.
The evaluation lock and loopback path remain explicit historical review inputs;
canonical acceptance exercises ordinary component defaults. Missing exact
artwork stays unavailable. Publication evidence, source drift, validation,
rollback and separate physical-phone acceptance are recorded in
[the Bee/Bat runbook](../docs/operations/elemental-bee-bat.md).
