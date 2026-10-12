# The Abby Project — Play prototype

A Unity presentation layer connected to the existing Django app. The current public preview opens **Memory Meadow** with temporary art; the licensed preview uses the purchased Meshtint Cute Series companion and forest. Both open a fixed companion home with Rewards, Inbox and Bestiary. Walking, the explorer avatar and the task board have been removed. **The primary product target is Abby's iPhone on iOS; Android is the first available test device.**

## Shared meadow slice

Today opens `/play/` directly. The earlier child-only web page at `/meadow` remains available by its existing URL. It uses the existing private-by-default journal form and its interrupted-save reconciliation. A new eligible journal's confirmed reward receipt appears as a **Memory bloom** on both the web page and Play. Editing a journal, greeting the companion, refreshing, or reopening Play grants nothing. The read-only `/api/chronicle/meadow/` response contains receipt identifiers, dates and counts, never journal words or family replies. It shows the newest 30 blooms and all-time totals, projected from existing journal records; legacy entries without verified awards and administratively deleted entries are not retained as separate collectibles.

Play reads the same authenticated child account, refreshes after browser resume and periodically, and clears the old collection on account changes. Its first visit displays existing blooms without replaying their celebrations. Later new receipts cause one local reaction per origin and child on this device; this acknowledgement is presentation only.

`shared/storybook/presentation.json` and its exported artwork/font are canonical for both clients. Run `python scripts/storybook/sync_presentation.py` after editing them, or `--check` to detect drift. The authored `Assets/AbbyCamp/Presentation/Meadow.asset` holds appearances, palette and shared Nunito font. Rebuilding preserves its appearance references and the authored dragon definition. Replace that definition's portrait or model and animation mapping without changing the companion ID or journal receipt IDs. See [AssetNotes.md](AssetNotes.md) for provenance and replacement details.

For a disposable same-origin React and Unity preview, build both clients and run:

```powershell
python scripts/unity/web_fixture_server.py --frontend-root frontend/dist --port 8089
```

This fixture seeds synthetic accounts and writing skills; it never reads `.env` or the project database. Sign in with the fixture credentials, keep a test memory at `/meadow`, then open `/play/` in the same browser. Physical phone performance, keyboard and lifecycle checks remain necessary.

## Licensed Cute Series preview

The [content/asset coverage guide](../../content/rpg/unity-assets.md) records
owned packs and the matching Chick, egg and Birdseed RPG content. Licensed
React builds use matching Chick/Bird collection portraits. Licensed Unity
shows Chick for an owned selected Base Chick and Bird after confirmed evolution
or selection of its mount. Other species, variants or missing models retain a
clearly labeled preview.

The purchased starter packs replace the temporary companion and forest scenery locally. The Archer remains staged for future uses; the home does not include an explorer. Run `python scripts/unity/stage_meshtint.py`, then
`./scripts/unity/Build-Camp.ps1 -Target Web -PrepareLicensed`. Open the generated
`Assets/AbbyCamp/Licensed/MemoryMeadow.unity` to preview the licensed scene in the
editor. Normal builds select it when present; checkouts without paid sources
retain the public prototype. Matching web portraits are staged by the same
script. See [AssetNotes.md](AssetNotes.md) for source protection and exact
animation mappings. These prepared growth forms do not yet add evolution rules.

## Product goal and next slice

### Owned creature presentation — 2026-10-11

Licensed presentation explicitly maps server `species.sprite_key=cute-chick`
and `potion.slug=base` to Chick, and the confirmed evolved pet or mount to Bird.
Choose a companion or mount in Bestiary; the acknowledged `/activate/` result
changes the appearance child while preserving the fixed actor root. The two
server active flags remain independent, so the last explicitly acknowledged
presentation choice is stored by origin and child and rechecked against active
ownership after reload. An already-active eligible row can be chosen again to
switch between pet and mount presentation. Evolved pets and exploring mounts
remain ineligible for selection.

A confirmed feed of the displayed Chick changes it to Bird when Django returns
evolution. The retained active pet and its evolved flag preserve that form
after fresh reads without activating the newly created mount. Growth alone
does not unlock Bird. Missing models, other species and unsupported variants
retain a labeled preview. Account changes reset the model binding immediately;
delayed old responses cannot change the replacement account. Normal refreshes
reuse the current model, and the development K key cannot override owned art.

Run `Build-Camp.ps1 -PrepareLicensed` once to prepare the new private binding
references before using or exporting an existing licensed scene. Public
checkouts contain no paid binding references. For disposable model/evolution
verification, run `Test-Camp.ps1 -OwnedCreatureArt`; its fixture uses Base Chick
alongside deliberately unsupported legacy variants and another family's data.
The web fixture accepts `--owned-chick-art` for the same coverage. Neither test
loads the project database. React uses the matching private portraits across
Today, Companions, Mounts, species detail, Manage and creature ceremonies;
evolved pet rows use the confirmed mount portrait with the usual fallback.

### Agreed web and Play responsibilities — 2026-10-10

The two clients are one product from Abby's perspective. The web app owns recording and revisiting life: journal and grade entry, homework, projects, chores, memories and family participation. Play owns reward presentation, the child's notification inbox and creature interactions. Eventually Bestiary, pets, mounts, companions, hatching, feeding, evolution, breeding, creature accessories and expeditions belong in Play. Parent approvals, content authoring and family management stay in the web app.

Play opens directly into a fixed companion scene with clearly labeled actions. Player walking, proximity gates and an explorer avatar are not requirements. The forest is a setting for reward reveals, updates and the companion; visiting or tapping it does not earn progress by itself. Journal, grades and other detailed forms remain web entry points for this slice.

The backend remains the authority for rewards, ownership and notification state. Both surfaces use the same account, palette, typography and asset identities. Web navigation should open `/play/` as a real document navigation, without another launch page or engine branding. Play must provide a visible return to Today and route notification actions to the relevant web tab while preserving the existing authenticated session. Browser/system push delivery continues through the existing web service worker when Play is closed.

The home shows confirmed coin balance and recent ledger/drop history, a global unread count and paginated inbox with explicit per-item acknowledgement, the account's real pets/mounts and active companion, and direct links to journal, grades and tasks. A prepared matching model represents the selected owned creature; unsupported species retain a labeled artwork preview. Bestiary supports hatching from owned eggs and potions, feeding from owned food, choosing an active companion or mount, starting and claiming mount expeditions, and breeding two owned mounts. Memory blooms remain one supported reward source, not the main navigation loop.

Migrate Bestiary one capability at a time. Keep existing web routes functional until Play supports their actions, accessible controls, loading/failure states and phone validation. Then move the child navigation and notification destinations together, including already-stored notification links. Retain parent access until an equivalent role-aware flow exists. Do not create two simultaneous automatic consumers of drop, growth or celebration queues: introduce durable event-specific reveal acknowledgement before handing those consumers to Play. Notification read state and reward reveal state have different purposes; marking the inbox read must not discard unseen rewards.

The immediate handoff changes are direct Today-to-Play navigation, automatic branded loading and disabled Unity splash/logo. The walking scene is replaced; existing web Bestiary actions remain available during migration.

### Recording and recognition

The core loop is **record life → save a lasting memory → receive recognition → return for family interaction and reflection**. Abby should be able to add journals, school results, creations, photos, and milestones, and look back on them later in life. Parents should be able to participate through encouragement, shared prompts, memories, and rewards. Game progression is driven by these contributions; the visual theme remains open.

Reward each eligible saved contribution once. Keep content capture available after the day's reward allowance is used. Recognize recording and reflecting on a grade consistently across good and disappointing results. Accumulated milestones can unlock companion progress, customization, album covers, and adventure chapters. Edits and revisits remain interactive while reward eligibility stays tied to distinct contributions.

Journal and grade capture are implemented in the existing web app: recoverable device drafts, confirmed saves, durable XP receipts, a small paw reaction, family replies on shared entries, and reopening memories in their history tabs or Yearbook. Grades retain percentages, points, or letters as recorded, with optional reflections and later corrections. The first grade capture each day is eligible for recognition independent of its mark; further results remain saveable. Stable save and reply request IDs reconcile interrupted requests without duplicate awards or replies. See [the phone capture guide](../../docs/journal-phone-slice.md). Additional memory capture, complete lifetime export, and connecting the reaction to an owned companion in Unity remain additional work.

Journal and grade entries default to **Only you**. Abby can explicitly share an entry with family and change its sharing later. Server access checks protect private entries across web and MCP reads; family replies require a shared entry. Chronicle responses are excluded from the web app's offline API cache so a cached response cannot bypass account or sharing changes. Archive requirements include journal text, structured grades, original photos/audio, dates, parent responses, and full export/backup; the current portfolio export does not cover all of these.

## iPhone direction

The phone prototype has a responsive portrait/landscape layout, safe-area insets, scrollable sheets, keyboard-aware native login, a fixed camera, tap-only companion interaction and direct web entry points. Tap the companion or **Say hello** for a friendly local reaction with no reward or account mutation. Theme selection remains open pending Abby's preferences. Browser viewport checks help development; Android and iPhone hardware still need performance, keyboard, resume, and safe-area testing.

Both rendering profiles use full scene resolution and 4× MSAA. The Web player follows browser pixel density, capped at 2×, and updates it on viewport changes without restarting Play. UI layout, camera margins and tap movement tolerance use the actual canvas pixel-to-CSS ratio, preserving CSS-sized text and touch controls. Density changes while a keyboard is open do not change the remembered portrait/landscape layout. Native/editor UI retains its existing 390-unit short-edge scale. Development captures use the active URP sampling and restore automatic camera aspect/framing after capture; normal builds preserve the saved scene and artwork.

There is no Mac available yet. The existing React home-screen web app handles capture and history; Unity exports a Web scene served at **/play/** on the same HTTPS origin. Opening Play automatically loads it behind the shared-brand progress screen and offers **Back to Today** while loading or after a failure. The Unity splash and logo are disabled in project settings and enforced by a build preprocessor for both scripted and Editor builds. Unity 6.6 supports [iOS Safari 15 and newer and Android Chrome](https://docs.unity.com/en-us/engine/6000.6/manual/platform-specific/webgl/intro/browsercompatibility); Web builds and native iOS builds are separate validation targets. Native packaging can follow when a Mac or cloud build route is available.

The existing backend's skill, pet, quest, and milestone systems can drive long-term progression. Play supports native hatching, feeding, active companion/mount selection and mount expeditions from the account's owned collection. Native breeding, evolving scenery, furnishings and world unlocks remain later slices. Presentation should read authoritative progress and preserve it when the theme or assets change.

iOS also needs remembered login, refresh after app resume, preserved reconciliation for interrupted saves, an accessible HTTPS backend, an iOS build profile, and validation on Abby's actual phone. Native local builds use macOS and Xcode; [Unity's build guide](https://docs.unity3d.com/6000.0/Documentation/Manual/iphone-BuildProcess.html) also describes the cloud build alternative.

## Open and play

Use **Unity 6000.6.5f1**, the selected editor for this project. See [the official release notes](https://unity.com/releases/editor/whats-new/6000.6.5f1).

Install 6000.6.5f1 in Unity Hub under **Installs → Install Editor**, including **Web Build Support**. In **Projects**, select AbbyCamp's editor version and choose 6000.6.5f1. The editor's import upgrades its supported packages; retain the resulting package manifest/lock and project settings together. The original desktop harness was built with 6000.3.2f1.

The original editor, 6000.3.2f1, has Unity's known valid-package signature warning. See [Unity's official notice](https://discussions.unity.com/t/package-manager-error-resolved-new-hub-badge-warning/1706569).

Open `Assets/AbbyCamp/Scenes/Camp.unity`, then press Play. The scene and presentation assets are saved in the repository; rebuilding is optional.

After a local build, run `Builds/Windows/AbbyCamp.exe`. This development build supports the loopback Django server and also connects to remote HTTPS origins.

| Control | Action |
| --- | --- |
| Rewards | Confirmed balance, recent coin/item history and journal blooms; links to reward shop and items |
| Inbox | Paginated updates; explicit Mark read on one item; Open related page keeps the same web session |
| Bestiary | Real owned pets/mounts; hatch, feed, choose an active companion/mount, and start or claim mount expeditions; web links for breeding and species |
| Journal / Grades / Tasks / Today | Same-origin web tabs without another sign-in or credentials in URLs |
| Tap companion / Say hello | Friendly local reaction, with no XP, coins, inventory or ownership change |
| Account | Refresh progress or disconnect only Play |
| Tap ground / arrow keys | No movement; the camera and companion anchor stay fixed |

Escape closes a sheet when no acknowledgement is in progress. K remains a development-only art-swap check. Windows is a development harness, not a product target. Without a child account the garden is a preview; no invented balances, inbox items or owned creatures are shown.

## Account data and handoff

Web builds validate the journal's existing `abby_auth_token` through `/api/auth/me/`, keep credentials in memory and never mint or rotate a token. Parent sessions remain in the web app. Native/editor login retains the existing password-login rotation and never stores passwords or tokens. **Account → Disconnect Play** clears only the local Play session; journal logout revokes the shared token. Account changes abort pending requests, clear all old account presentation and reconnect before accepting new data.

The home refreshes coins, unread count, stable and character on connection, browser resume and every 30 seconds while no sheet is open. Sheets load their corresponding narrow APIs on demand. Recent rewards are earned history, not unclaimed awards. Opening, refreshing and counting down never claim an expedition. No `/api/pulse/`, growth `/seen/` or bulk-read request is made. The legacy client habit methods remain contract-tested but have no home UI caller.

Bestiary reads `/api/pets/stable/`, `/api/inventory/`, `/api/expeditions/` and `/api/coins/` before enabling creature actions. Choose a companion, select an available food, then explicitly **Give 1**. `POST /api/pets/{id}/feed/` consumes one food and confirms the saved growth and any automatic evolution. Choosing a companion or mount uses its existing `/activate/` endpoint. Evolved companions cannot be fed or selected; mounts on an active expedition cannot be selected. A confirmed result triggers a local scene reaction and refreshes the collection and food. The preview artwork retains its identity; selection does not pretend it represents every owned species.

**Hatch a companion** opens a native sheet in Bestiary. Choose an available egg and potion by their item-definition IDs, then explicitly **Hatch with 1 egg + 1 potion**. `POST /api/pets/hatch/` consumes one of each and returns the new saved pet at zero growth, without changing the active companion. Only a complete new-pet receipt confirms the hatch: a previous pet ID, nonzero growth, active/evolved/fed state, or mismatched typed ingredient names leaves the outcome uncertain. Legacy ingredients can omit typed names; Play does not invent catalog IDs or potion compatibility. A confirmed hatch gets one local reaction and fresh collection/inventory reads. **Back to creatures** shows the new companion, where it can be fed or explicitly chosen as active. Duplicate species/potion combinations, including evolved historical pets, are rejected by Django without consuming ingredients. The web hatchery remains available alongside breeding and parent access during migration.

**Mount expeditions** opens the owned mount collection. Choose a mount and a short (2-hour), standard (4-hour) or long (8-hour) trip, then explicitly **Start expedition**. `POST /api/mounts/{id}/expedition/` saves the trip and locks its planned loot without awarding it. An owned active mount may explore; mounts already exploring cannot start another trip or be selected as active. Django enforces the daily rest limit using its own calendar. The detail sheet shows the saved return time and an estimated countdown. Reaching zero locally never enables claiming: refresh must accept the server's active, ready expedition before **Claim expedition loot** sends `POST /api/expeditions/{id}/claim/`.

A complete claim receipt confirms the trip and refreshes the collection, inventory and balance. Fresh claims show actual expedition coins (including coin boosts), separately show any duplicate-find salvage coins, and show refreshed inventory quantities for matching finds. Planned slots can repeat or refer to archived definitions; they are not treated as proof of newly granted inventory. A repeat claim awards zero expedition coins and receives no new celebration. Existing web mount, breeding and notification routes remain available during migration; opening either client never automatically claims or consumes reward reveal queues.

**Breed two mounts** opens a native sheet in Bestiary. Choose the first parent, choose a different second parent, then explicitly **Breed this pair**. `POST /api/mounts/breed/` grants one egg and one potion and starts both parents' existing seven-day rest period. The stable response reports `can_breed` and ceiling-rounded `breeding_cooldown_seconds` from one server clock snapshot; local time never unlocks a pairing. Away mounts retain the existing service's cooldown-only breeding rules. Species/potion compatibility and Cosmic upgrades are chosen by Django, including compatible potion fallback for legacy parents. A complete typed receipt confirms the actual items, chosen species/potion and any Cosmic upgrade. Play shows those saved results and separately shows matching inventory quantities after refresh. Breeding does not hatch a pet or select an active creature; hatching remains a separate explicit action. The web hatchery and parent routes remain available during migration.

Creature actions never automatically retry a POST. A credential-free marker, scoped to server origin and child, is saved in device PlayerPrefs before dispatch. An interrupted or ambiguous feeding, selection, hatch, breeding, expedition start or claim keeps all creature actions disabled, including after closing the sheet, reloading Play, or returning to that account. **Refresh creatures and items**, inspect the updated collection, parent cooldowns, expedition history, inventory quantities and coin balance, then **I checked the updated collection** clears the marker. All four complete reads must succeed before acknowledgement is available. Definite rejection removes the marker but still requires fresh reads before the next action. Other accounts have their own marker and collection; aborted or late responses cannot populate a replacement session. Refreshing never replays a mutation or celebrates a result inferred from history.

Inbox GETs never change read state. **Mark read** acknowledges only that fetched notification ID and waits for a matching confirmed response before updating the row. If the result is uncertain, the user can refresh or explicitly retry the idempotent acknowledgement; the client never retries a POST automatically. Other unread rows remain unchanged. Pagination accepts only bounded same-origin notification page links. Django returns root-relative continuations so the browser retains its public HTTPS origin even when a tunnel reaches the backend over HTTP. A failed initial load shows a refresh prompt instead of a lingering loading label. Notification destinations are mapped to typed internal routes (including legacy links); arbitrary URLs and credential-bearing links are never followed.

Journal and grade shortcuts open their real Chronicle tabs. Tasks, reward shop, items and the remaining Bestiary shortcuts reuse the current web actions. Web session credentials never enter navigation URLs. Native harness links open the corresponding web address but do not transfer its in-memory token to a browser.

## Replace art

Gameplay components and `CampEntityIdentity` live on actor roots. A `VisualPresenter` instantiates only the appearance child from a `VisualDefinition`. Each definition holds its model, local scale/offset/rotation, animation controller, and intent mappings.

The generated dog and fox definitions under `Assets/AbbyCamp/Generated` demonstrate replacing an appearance while preserving identity, the stationary anchor and game progress. Import replacement art into its own directory, create a definition, map Idle/Walk/Celebrate, and assign it. Tap interaction belongs to the root input router, independent of model names. Different rigs can use different animation controllers.

Original third-party models are under `Assets/ThirdParty/Kenney`. Materials/controllers/definitions created for this project are under `Assets/AbbyCamp/Generated`. Sources and original CC0 licenses are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); exact clips and import guidance are in [AssetNotes.md](AssetNotes.md).

## Build and validate

From the repository root in PowerShell:

```powershell
./scripts/unity/Build-Camp.ps1 -Target Web
./scripts/unity/Publish-Web.ps1 -BuildImage -SaveImage -ImageTag abby-unity-web:preview-1
./scripts/unity/Test-WebHosting.ps1 -ImageTag abby-unity-web:preview-1
node --test scripts/unity/test_browser_session.cjs
node --test scripts/unity/test_web_template.cjs
```

The build script uses **6000.6.5f1** at Unity Hub's default Windows installation location. A custom installation path can be passed with `-UnityEditor`. Close this project in the editor before a batch build. Web output is in `Builds/Web` with a `Logs/build-web.log` log. Normal builds preserve the saved scene. Pass `-RebuildScene` only to regenerate the starting camp and replace its scene and generated presentation assets. `-ValidateOnly` performs scene/API checks without exporting; `-Target Windows` retains the desktop harness.

The Web output must be served over HTTP/HTTPS, not opened as a local file. [Coolify hosting instructions](../../docs/unity-web-hosting.md) describe the separate image and `/play/` path routing. PR checks validate source; after merge to main, [Unity Web release jobs](../../docs/operations/unity-web-release.md) compile the licensed player and deploy it after the platform release succeeds. Generated builds and image archives remain ignored. The React service-worker update must also be deployed and accepted by any installed PWA, so it stops substituting the React index for `/play/`.

For local browser checks with disposable API data:

```powershell
python scripts/unity/web_fixture_server.py --port 8089
```

Open `http://127.0.0.1:8089/play/`. This loopback preview uses synthetic child `camp-smoke` and password `only-local-smoke`. It never loads `.env` or opens the project's database. Ctrl+C removes its temporary data. Use the HTTPS Coolify URL for testing on a phone.

Unity menu **Abby Camp → Create or rebuild camp** regenerates the scene and generated presentation assets. This replaces changes to the generated camp, so use it deliberately. **Validate all** checks scene structure, imported models/animations, the dog/fox swap, and API contracts. **Build phone Web prototype** and **Build Windows prototype** also run those checks.

The opt-in development smoke is run by:

```powershell
./scripts/unity/Test-Camp.ps1
```

It uses real Django views against disposable SQLite and seeded reward, inbox, creature and inventory data. The runtime checks fixed framing, direct taps, modal input exclusion, phone layouts, real account rows, pagination, explicit one-item acknowledgement including an injected failure, care, hatching, expeditions and switching to another family's child. Care checks include a feeding committed before an injected HTTP 503, refresh/review without replay, confirmed evolution and active selection. Hatch checks cover a committed hatch followed by HTTP 503, close/reopen and explicit review without replay, duplicate rejection, a confirmed hatch with an exhausted potion, and account replacement during a delayed acknowledgement followed by exhausted eggs. Expedition checks cover all trip lengths, explicit confirmation, readiness and daily rest gates, committed start/claim responses replaced by HTTP 503, review without replay, exact locked rewards, and account replacement during held start/claim acknowledgements. Snapshots verify exact consumption and expedition payouts, with unchanged other-family, drop and skill XP state. API fixture checks retain the legacy habit/cap and journal privacy contracts. It never reads `.env` or uses the project's database. Python must have the repository's Django dependencies installed.

Account-replacement checks use an explicit fixture acknowledgement hold. On either disposable fixture server, `POST /__fixture/hold-next-care/` (also available as `/__fixture/delay-next-care/`) holds the next successful creature response after Django commits. `GET /__fixture/play-state/` exposes `care_responses_pending` and `care_hold_timeouts`. After observing the commit and displaying the replacement account, send `POST /__fixture/release-care/`. The hold expires after 15 seconds if unreleased; smoke requires zero hold timeouts. `prototype_fixture_server.py --check` verifies that a concurrent HTTP snapshot observes the committed hatch and explicit release drains its acknowledgement.

For expedition reconciliation walkthroughs, both fixture servers accept `--fail-first-expedition-start-after-commit` and `--fail-first-expedition-claim-after-commit`. `POST /__fixture/finish-expedition/{id}/` advances only a seeded primary child's active Sun or Trail trip to its return time; it preserves the locked loot. These disposable controls also support held expedition acknowledgements and are never part of the product API.

`Library`, build output, logs, screenshots, and user settings are ignored; source `.meta` files are retained. The package manifest/lock and project settings are included. Journal/grade reactions are currently implemented in React; connecting those saves to an owned Unity companion is a later slice. Real-phone lifecycle/performance and native iOS deployment need their own validation before Abby uses it day to day.

## Native expedition verification — 2026-10-11

Unity 6000.6.5f1 validated the saved scene and 291 API checks and exported the Windows player. The final Windows harness passed 1,258 runtime checks with 28 rendered captures and no runtime errors. It verified explicit trip choices, visible 44px targets, server readiness and daily rest limits, interrupted start/claim review without replay, exact locked coin/item payouts, and account replacement during held start and claim acknowledgements. Both holds were explicitly released with zero timeouts; the other family's full history, inventory and progression remained unchanged. One initial run caught missing duration text on the final Start button; the corrected binary passed the complete unchanged harness. Counts include timing-dependent polling snapshots.

The exported Web player passed a disposable same-origin walkthrough at 393×852 portrait and 844×393 landscape. Lost start and claim acknowledgements preserved the review marker across reload; refresh and explicit review replayed neither action. Claiming stayed disabled until an accepted server-ready refresh. A second, confirmed claim showed its actual 35 coins and refreshed item quantity, with terminal feedback visible at the top. Final snapshots recorded exactly one start and two claims, 49 expedition coins and three items, with unchanged drops, skill XP and the other family's state. Browser logs contained no runtime errors. These viewport checks do not establish physical phone performance or lifecycle behavior.

## Native hatching verification — 2026-10-11

Unity 6000.6.5f1 validated 242 API checks and exported Windows and Web players. The final Windows harness passed 708 runtime checks with 21 captures, including ingredient selection, 44px targets, uncertain-result review, duplicate rejection, confirmed hatching, exhausted supplies and account replacement after a real committed hatch. Saving and terminal hatch feedback remain visible when confirmation starts at the bottom of the sheet. The count includes timing-dependent polling snapshots. One earlier run missed the fixture's fixed two-second care acknowledgement window; the explicit hold/release protocol replaced that window, and both final account-switch cases completed with zero hold timeouts.

Disposable Web walkthroughs at 393×852 portrait and 844×393 landscape verified shared sign-in, an interrupted hatch marker surviving reload, refresh without replay, explicit review and a second confirmed hatch. Final feedback appeared at the top without scrolling. The final snapshot recorded exactly two hatch requests, two saved pets and four consumed ingredients, with unchanged rewards/progression and another family's state. The browser reported no runtime errors.

All 92 pet/shared-response Django tests and 2,723 React tests passed. Frontend lint and production build passed; lint retains six existing warnings. Browser bridge/template checks passed all 32 tests and presentation sync verified eighteen files. These checks use synthetic accounts and disposable SQLite. Physical iPhone/Android touch, lifecycle and performance remain unverified. Source and local exports do not update live Play.

## Sharper rendering verification — 2026-10-11

Unity 6000.6.5f1 exported Windows and Web players with full-resolution Mobile/PC pipelines and 4× MSAA. Both builds passed rendering, scene and 187 API checks. The Windows harness passed 555 runtime checks with fifteen captures: doubling portrait and landscape framebuffers preserved all nine home button rectangles, title size, camera pose/orthographic framing and companion hit targets. Focused-form keyboard resizing preserved touch scale, scrolled the password field into view and recovered after dismissal. Development captures now use the active URP sampling and restore automatic camera aspect/framing.

All 32 browser bridge/template tests passed, covering fractional density, the 2× cap, startup/ready density changes and visual viewport resizing. The exported Web runtime passed a disposable 393×852 portrait and 844×393 landscape walkthrough. A temporary local test page switched its live framebuffer between 1× and 2× while preserving CSS dimensions, readable UI, companion framing, open-sheet geometry and coordinate button hits. The original exported page was restored exactly afterwards, and the browser reported no runtime errors. Presentation sync verified eighteen files. These checks do not establish physical iPhone/Android performance or deploy the updated player.

## Native companion care verification — 2026-10-11

Unity 6000.6.5f1 validated the unchanged public scene and 187 API contracts and exported Windows and Web players. The Windows player passed 383 runtime checks with thirteen rendered captures, including food selection and touch targets, active companion/mount selection, an expedition selection guard, automatic evolution, simultaneous collection reads, and an account change after a feeding committed while its response was delayed. A committed feeding followed by an injected HTTP 503 consumed exactly one food; refresh and explicit review sent no additional feed. Returning to the original account retained its interrupted-action marker, while the second family's creature, food and reward state remained unchanged. Repeating the harness with Django 5.2.18 passed 377 checks; the count includes timing-dependent polling snapshots.

The exported Web player also passed a disposable same-origin browser walkthrough at 393×852 portrait and 844×393 landscape. Opening Play reused the web sign-in. The injected committed-feed failure disabled further care, and its marker survived a browser reload. Refresh and acknowledgement kept exactly one feeding request; a second explicit feeding confirmed evolution and created its mount. The final snapshot recorded exactly two feeds, two consumed foods and unchanged coins/skill XP, with no writes to the second family's account. The browser reported no runtime errors.

The shared response producer and existing pet suite passed all 84 Django tests using a task-local Django 5.2.18 environment. React's 18 shared-fixture tests and complete 2,585-test suite passed, along with lint and the production build. The complete suite used four workers after an unbounded run hit unrelated timeouts; the changed test file passed throughout. Browser bridge/loader checks passed all twenty tests and presentation sync verified eighteen files. These checks use disposable synthetic accounts. Physical iPhone/Android touch, lifecycle and performance validation remains separate. Source and local exports do not update the deployed Play service.

## Fixed Play home verification — 2026-10-10

Unity 6000.6.5f1 validated the public and licensed fixed scenes and 108 API contracts. The Windows development harness passed 224 runtime checks with nine rendered captures, including fixed companion framing, tap/modal exclusion, readable sheet headings, phone targets, real reward/creature rows, 20/5 notification pages, read failure/retry, account replacement and reward invariance. The browser session and loader suites passed 20 checks; the shared presentation check verified 17 files.

The disposable browser walkthrough verified automatic shared sign-in, Journal/Grades/Tasks routes, explicit one-item read acknowledgement and account replacement while an earlier read response was delayed. Opening sheets, paging and greeting the companion left rewards and progression unchanged. Browser viewport checks cover 320×568 and 393×852 portrait and 844×393 landscape; they do not establish physical Android/iPhone performance, touch or lifecycle behavior. The purchased forest and fixed bird are presentation previews; Bestiary lists authoritative owned creatures without assigning that artwork to every saved species. Care, hatching and mount actions still open their existing web screens.

These checks and local exports do not deploy `/play/`; the main CI/CD release jobs or an administrator release must build and publish its web image after the source is integrated.

## Earlier walking prototype verification — 2026-10-10

The following historical checks describe the earlier walking preview, before the fixed Play home.

The 6000.6.5f1 Web export passed scene/asset validation and 41 API contract checks. Browser checks covered 320×568 and 393×852 portrait views, 844×393 landscape, and a simulated keyboard-reduced viewport. The walkthrough verified practice persistence, ground movement and camera follow, direct Tasks access away from the board, companion greetings and appearance changes, credential preservation on rotation, sign-in, scrolling, and sign-out.

Against disposable Django data, an injected HTTP 503 blocked further saves through refresh until history acknowledgement. Neither refresh nor acknowledgement posted another log. One later confirmed save increased the fixture habit to one tap and skill XP from 95 to 105; the capped task remained disabled. This validates request handling and visible browser interaction, not physical touch gestures or a real phone keyboard. The packaged nginx image has a separate nine-check hosting verification. Android Chrome hardware testing is next, followed by iPhone Safari when available.

## Shared browser session verification — 2026-10-10

The handoff passed 25 Django auth/family tests, 12 JavaScript bridge tests, and the complete React suite (2,346 tests; coverage gates, lint, and production build passed). Unity 6000.6.5f1 exported the Web build after scene checks and 42 API contract checks.

Browser checks against disposable loopback Django accounts confirmed automatic adoption, journal/world coexistence, local camp sign-out and reconnection, journal logout, stale-token rejection/clearing, parent-session preservation, and restoration after reloading `/play/`. Switching to another family's child while an earlier save response was delayed removed the old account's tasks and toast; the new account could save its own ritual without inheriting the old uncertainty. The fixture recorded exactly two explicitly requested habit saves, with no automatic retries. Its four password logins came only from the fixture's journal controls, including account changes; opening, reconnecting, and reloading the world added none.

This validates the browser/IL2CPP bridge and live Django boundary. Physical iPhone/Android lifecycle testing remains outstanding. The source patch and local Web export do not update the deployed preview; deployment is a separate step.

## Purchased Cute Series verification — 2026-10-10

All four downloaded starter packs were staged privately, including their PSD
textures, and prepared in Unity 6000.6.5f1. The licensed Web build passed scene,
three-form animation/portrait, material-texture and 56 API contract checks.
React's public fallback and licensed builds passed; 31 focused Meadow tests and
five synthetic archive/import safety checks passed.

A disposable Django/browser walkthrough at 393×852 and 844×393 verified supplied
character/scenery textures, explorer movement and companion following, greeting,
account adoption and keepsakes. One private synthetic journal earned 15 XP and
one bloom on the web page and in Play. Greeting and movement sent no API writes
and left that receipt count unchanged; Play's response did not expose journal
text. The Archer's supplied animation imports report copied-avatar bone
position/rotation warnings. The walkthrough showed movement without obvious
clipping, but this does not establish compatibility for every modular outfit or
animation. Physical Android/iPhone animation and performance checks remain open.

The licensed files and original archive backups remain private/local. No deployed
application is changed by staging assets or updating this source branch.
