# frontend/src/pages/

Page-level architecture: the Quests hub, the Atlas hub, the Sigil Frontispiece, the Yearbook, the role-split Dashboard, and the page primitives that unify how every page renders.

**Current UI names:** Tasks, Pets, Rewards, Progress, Memories and Profile.
Use the [UI language table](../../CLAUDE.md#ui-language-october-2026) for tab,
action and help wording. Historical names in the architecture below describe
stable routes and component identifiers, not the labels to show users.

## Progression lab

`/manage/rpg-content` adds the staff-parent content workspace alongside the lab.
It browses challenges and items, saves revisioned server drafts, shows reward
wiring and audits, and compares the published and proposed catalogs before
explicit publication. Use the exact reviewed preview and draft revision for
comparison/publication. Editing invalidates old reviews; account changes fence
in-flight responses. Existing item effects are versioned to preserve owned and
promised items. See [`RPG content workbench`](../../../docs/operations/rpg-content-workbench.md).

`/manage/progression-lab` is the staff-parent designer workspace, linked from
Manage → Admin. The metadata endpoint is the authority for staff access;
regular parents recover from its 403 without seeing simulations. All forecasts
come from the server's anonymous, bounded simulator. React keeps editable
assumptions, a current report and an optional comparison in account-scoped
component state. Local JSON imports restore validated routines only and never
run automatically or present old imported results as current forecasts.
Unreached milestones, conditional percentile dates, expired one-time windows
and the model's finite-content subset stay explicit. See
[`Progression Lab`](../../../docs/operations/progression-lab.md) and the shared
producer/consumer checks before changing its response or presentation.

## Google authorization return

Login availability reads the nonmutating `/api/auth/google/config/`; only an
explicit click starts authorization. Login, Settings and Manage's child-link
sheet share `useGoogleAuthorization` and `auth/googleOAuth.js`. Each start uses
a fresh browser verifier, sends only its S256 challenge, and stores the bounded
attempt in sessionStorage scoped to backend/browser origin, initiating
credential fingerprint, actor/family and optional child. No Abby or Google
bearer token is stored there or accepted from navigation URLs.

`main.jsx` captures and scrubs the opaque callback fragment before Sentry
initializes. AuthProvider shares one proof exchange across StrictMode replay,
then uses the existing push-safe session replacement. A reload before the POST
can resume; a reload after an uncertain POST requires a fresh explicit start,
without replaying the mutation. Expired, missing, cancelled and account-switched
attempts keep the current account. Late start/receipt responses cannot navigate
or replace a newer account. Browser Back restores the start controls.

Google return currently supports the hosted same-origin browser app only.
Native and cross-origin API/redirect configurations fail closed with guidance;
there is no arbitrary return URL or native OAuth parity claim. Calendar and
Drive retain their existing authorization contracts; Drive's transient GIS
`drive.file` interaction is independent of this account-link flow.

## Page primitives (added 2026-05, commit `2b240fc`)

`/__design` documents reusable page recipes and interactive recovery states.
Utility screens compose the shared page and section headers. Hub tabs keep
their compact phone layout while retaining an accessible page heading. Return
navigation from a project uses the canonical, account-bound list context in
`project/projectListReturn.js`, preserving only supported filters/search and a
bounded scroll position.

Journal, Grades and Timeline share `useChildContext` and `ChildContext` for
parent selection. A child ID from the URL or per-parent/family remembered
choice is accepted only after a fresh current-account roster verifies it.
Account/family/credential changes fence old responses; entry author and privacy
checks remain intact. Parent Today links directly to the selected child's
timeline. Child creation shows a confirmed username and optional next activity
guidance, without persisting passwords or inventing setup completion.

The 2026-05 audit lifted two layout primitives out of the per-page copy-paste pattern:

- **`<PageShell>`** ([`components/layout/PageShell.jsx`](/frontend/src/components/layout/PageShell.jsx)) — root wrapper replacing the copy-pasted `<motion.div className="max-w-6xl mx-auto space-y-5">`. Owns spine width (`max-w-6xl` wide / `max-w-3xl` narrow), vertical rhythm (3 tiers: `loose` = `space-y-6`, `default` = `space-y-5`, `tight` = `space-y-3`), and the fade-in animation. Does NOT add horizontal padding (that stays in `JournalShell`'s `px-4 md:px-6` to avoid double-padding). Set `animate={false}` for pages handling their own motion; pass `variants` to take over the motion config entirely. Set `as="main"` for `<main>` semantics. Used today across 17 surfaces — Achievements, ActivityPage, Badges, Character, ChildDashboard, ClockPage, CodexPage, DashboardSkeleton, Inventory, Manage, ParentDashboard, Payments, ProjectIngest, ProjectNew, Rewards, SettingsPage and Timecards. Quests-hub tab bodies (Chores, Habits, Projects, Homework, Movement, Forge, Trials) deliberately wear `QuestFolio` instead — they are tabs inside a hub, not page roots.

- **`<SectionHeader>`** ([`components/SectionHeader.jsx`](/frontend/src/components/SectionHeader.jsx)) — non-collapsible sibling of `AccordionSection` for always-open sections. Mirrors the `AccordionSection` vocabulary: kicker, rounded Meadow number marker via zero-based `index`, `RuneBadge` count badge, optional supporting body line via children, and right-aligned `actions` slot. Renders as `h2` by default (configurable via `as` prop — use `h3` for nested). Settings uses six `ParchmentCard` sections with markers 1–6. Shared `ChapterMarker` also replaces manuscript rubric symbols in collection folios; `chapterMark` returns Arabic labels for chapter taxonomies and shelf medallions.

**Mobile readability**: as part of the same audit:
- `HeaderStatusPips` button heights bumped from `h-8` (32px) → `h-11` (44px) with `px-3` to meet mobile tap-target sizing; text changed from `text-xs` → `text-caption`.
- Form modal grids now collapse `grid-cols-1 sm:grid-cols-2` (or `sm:grid-cols-3`) for screens below 640px (Chores, Habits, Manage, Timecards, Trials).
- All raw `text-xs` and `text-sm` replaced with semantic tokens (`text-caption`, `text-body`, `text-tiny`, `text-lede`) across ~110 instances.
- 30+ raw `<button>` elements migrated to `<Button>` or `<IconButton>` primitives across Habits, Chores, Settings, Manage, Inventory, Payments, Trials, ProjectNew, ClockPage, Rewards, Projects, Achievements, and Badges.

## Memory Meadow (first shared storybook slice)

`/meadow` is a lazy-loaded child-only page under `JournalShell`. Child Today
has no Play promotion card. Existing journal/archive and parent
pages keep their current behavior. The page opens the React pet collection.
Pets opens its exact supported owned 3D companion automatically, with direct care and
expedition interaction, View settings and working DOM/2D fallback. Profile
centers the owned Archer character and its saved basic customization.
Legacy `/play/` bookmarks redirect to React Pets; Unity is retired.

Pets keeps the existing `companions`, `mounts`, `codex` and `hatchery` tab IDs.
The Collection and Hatchery tabs advertise the 15 supported Base-potion families. Every family has four lifecycle stages: Egg in inventory, Baby after hatching, Middle from 50 server-confirmed growth, and Grown after confirmed evolution at 100. Exact Base Chick retains the familiar Chick, Fledgling and Bird form names. Shared `PetEvolutionGuide` shows the complete path in companion previews and species details; care, collection, Today, grown-pet and expedition labels use the same form names while nicknames and saved species identities stay intact. `OwnedPetGrid` and `OwnedMountGrid`
also render earlier unsupported rows under Saved collection in their respective
tabs, retaining feeding/evolution, activation, expedition launch/history/claim
and recovery controls. `catalog_available: false` describes new catalog
eligibility, not permission to erase or disable saved care. Breeding is retired; the Hatchery manages eggs and hatching, and grown pets explore through expeditions. Missing models keep DOM/2D controls
available, without substituting a bird for another saved species.

`pages/meadow/meadow.constants.js` adapts generated
`src/storybook/presentation.json` and bundled, hashed image/font URLs. The
source manifest lives at `shared/storybook/presentation.json`; update it
through `scripts/storybook/sync_presentation.py` rather than editing the
generated copy. Art filenames never identify a keepsake. Temporary dragon
portraits can be replaced independently of journal receipts and companion ID.

Capture reuses `JournalEntryFormModal`, first checking the existing
`getTodayJournal` endpoint to choose create or edit. Its private default,
family sharing choice, device drafts and idempotent retry remain intact.
Opt-in `surfaceClassName` / `surfaceStyle` pass through to `BottomSheet` so
the portal's capture and confirmation surfaces use the meadow palette and
bundled Nunito without changing other forms.
The optional second `onSaved` argument reports the form's effective mode,
including a POST 409 recovery into an edit; the meadow uses that value when
deciding whether a confirmed receipt can trigger a new-memory celebration.

`getMeadow` reads `/api/chronicle/meadow/`: verified, body-free journal award
receipts become `memory_bloom` keepsakes. Count is lifetime total; the array
contains the newest 30. A confirmed creation refreshes this endpoint and
celebrates only the saved journal's previously unknown receipt ID. Edits,
known receipt replays, unavailable rewards and uncertain saves never invent
another bloom. Say hello is local companion feedback and grants no reward.
Celebration motion respects `prefers-reduced-motion`.

## Quests hub (commits `3e8c18c`, `69d7b48`)

Reading (`/quests?tab=reading`, redirected from `/reading`) uses
`pages/reading/` and the shared Task folio. Its bookshelf supports Reading,
Want to read, Finished and Paused; saved sessions accept minutes, pages,
chapters, print/ebook/audiobook and optional reflection prompts. Notes are
visible to the reader and their parents, independent of private Journal
entries. `useChildContext` verifies the selected child; the workspace and
in-memory forms reset by account, credential and child. Uncertain writes retain
the exact payload and creation UUID for safe retries. A confirmed save receipt
remains visible when a subsequent read fails. Books with session history cannot
be deleted. Totals come from `/reading/summary/`; local curated recommendations
use book topics/age and publisher sources, without sending notes externally or
granting rewards.

`ReadingDiscovery` presents 64 locally curated publisher-sourced books with
edition details and covers. It sends `interest`, `mood`, `style`, `book_format`,
`length`, `theme`, `q`, `similar_to` and `rotation` to the server; length labels
mean ≤200, 201–349 and ≥350 pages. Matching and ordered series eligibility stay
server-owned, and reflections never enter recommendations. `DiscoveryBookCard`
loads only Open Library cover URLs with `no-referrer` and an accessible fallback;
its WorldCat link searches a catalog without claiming local availability.
Saved books expose nullable `catalog_entry` for “More like this”. “Not interested”
and “Already read” persist preferences without reading history or rewards;
Undo clears that preference. “Show different books” rotates eligible picks.

Parents can send a catalog book with a personal note of at most 500 characters.
`FamilySuggestionForm` retains its exact UUID/payload for uncertain retries.
The paginated pending list shows the saved parent attribution and `on_shelf`;
the child explicitly chooses Save to want to read or Dismiss. Saving uses the
ordinary shelf create and leaves the invitation pending with `on_shelf: true`.
Family suggestions and discovery preferences follow the selected child/account
reset and family-scoping rules above. Producer/consumer coverage lives in the
existing reading API contract test modules.

The daily reading card uses the summary's server-owned `reading_adventure`
progress. New logs dated today contribute minutes toward one daily reward;
audiobooks count and reflections remain optional. Show base XP/Coins before
earning and actual boosted amounts from the persisted `reading_reward` after
earning. Edits and historical logs never promise new credit. Confirmed saves
refresh the shared Pulse for balances and existing notification/drop toasts;
clients never add a receipt's amount to a local balance. Pulse also refreshes
the summary's household day so an open page can show the next day's reward.

The Tasks page consolidates activities under one hub. Seven top-level `ChapterHub` tabs:

| Tab | Slug | Backing page |
|---|---|---|
| Ventures | `ventures` | `pages/Projects.jsx` |
| Duties | `duties` | `pages/Chores.jsx` |
| Study | `study` | `pages/Homework/index.jsx` |
| Rituals | `rituals` | `pages/Habits.jsx` |
| Movement | `movement` | `pages/Movement.jsx` |
| Reading | `reading` | `pages/reading/index.jsx` |
| Trials | `trials` | `pages/trials/index.jsx` |

The hub itself lives at [`pages/quests/index.jsx`](/frontend/src/pages/quests/index.jsx). Legacy routes redirect:
- `/chores` → `/quests?tab=duties`
- `/homework` → `/quests?tab=study`
- `/habits` → `/quests?tab=rituals`
- `/quests?tab=forge` → `/treasury?tab=forge` (preserves only `new=1`)
- `/trials` → `/quests?tab=trials` via `TrialsLegacyRedirect()` in [`App.jsx`](/frontend/src/App.jsx) (preserves older `/trials?scroll=<itemId>` links without consuming the saved scroll).

### Task actions and history

Homework cards and proof sheets show the assignment description, preserving
line breaks without displaying private notes. Sheets opened from Today fetch
missing instructions through the assignment detail endpoint, with loading and
retry states. Parent homework decisions disable review actions while saving;
failures stay with the submission and retry the same decision.

Assigned children can open `/clock?project=ID` from a workable project's
“Work on this project” action. The clock verifies that exact assignment before
offering an explicit clock-in; an unavailable target never falls back to a
remembered project. An existing timer always shows its actual project.

Payments and Timecards use `usePagedList` for complete history, totals and
“Load more” recovery. Requests rebuild page numbers through the known API
helpers with the current filters; server `next` URLs are never fetch targets.
Filter/account changes fence older requests, and refreshing after a decision
reloads the already-loaded pages so an older week remains visible.

Reward requests show an accessible receipt from the saved redemption status
and frozen coin cost, with a direct history view. A failed follow-up read keeps
that receipt and offers read-only refresh instead of repeating the request.

### Shared folio shell

[`pages/quests/QuestFolio.jsx`](/frontend/src/pages/quests/QuestFolio.jsx) is the verso/recto shell shared by Ventures, Duties, Study, Rituals, Movement. Modeled on the former Skills layout at `pages/achievements/FolioSpread.jsx` but parameterized so a tab can fill in its own letter / title / stats / progress without dragging the skill-tree XP math along.
- **Verso** (left, ~220-260px desktop · top banner mobile): `IlluminatedVersal` initial, kicker, Nunito title, stats row, progress bar and optional `RarityStrand`. Tier is expressed through progress and labels.
- **Recto** (right): consumer-supplied children — the working list grouped under `ChapterRubric` numerals (§I, §II, …).

No new tier ladders, halo colors, or keyframes — composition against the existing Atlas cohort.

### Rarity mapping

[`pages/quests/quests.constants.js`](/frontend/src/pages/quests/quests.constants.js) maps per-page tier concepts onto the Atlas `RARITY_KEYS` vocabulary:
- `difficultyToRarity(level)` — Project difficulty 1-5 → common / uncommon / rare / epic / legendary (clamped both ends so off-scale values land on common).
- `effortToRarity` — Homework effort_level uses the same 1-5 ladder; aliased to `difficultyToRarity`.
- `buildRarityCounts(items, mapper, isEarned)` — produces the `{common: {earned, total}, …, legendary: {…}}` shape `RarityStrand` consumes. Empty buckets stay at 0 so the trough still paints.

Ventures + Study render a `RarityStrand` on the verso. Duties, Rituals, Movement, Forge, Trials skip it (their progression isn't difficulty-ranked).

### Challenges sub-architecture

Tasks → Challenges (`/quests?tab=trials`) uses the shared Task folio shell.
The pinned challenge and parent-created goals lead the working list. Up to three
bonus challenges with positive progress appear next, ranked by proportion toward
completion. The remaining bonus goals and history stay in collapsed disclosures.
Every matching goal continues tracking regardless of its placement or whether a
disclosure is open. A pin only features one active goal on Today and in the header;
children do not start or claim goals to make their work count.

- `trials/index.jsx` owns the parent's child selector, goal details and pin actions.
  `ChallengesFolio.jsx` presents the shared `QuestFolio` layout; `challengeFocus.js`
  groups the full server response without changing saved state or eligibility.
  Parents use `CreateGoalForm.jsx`
  to assign count, minute or distance goals, with a period and optional weekly
  repeat. The form previews the activity, date window and reward and retains a
  UUID for identical save retries.
- `ChallengeGoalCard.jsx` presents the server's decimal progress, origin, activity
  rule, planned reward and actual completion receipt. Parent and pinned deadlines
  remain visible; background bonus dates stay in full details. Origin is the
  server-owned `parent|catalog|legacy` field, never inferred from a title. Action
  links open the relevant activity flow; running goals preselect the movement type.
  Closing details restores focus to a live goal button or the disclosure when a
  pin change moved its original opener.
- `goalDisplay.js` formats progress and household-local deadlines. Do not derive
  eligibility, paid amounts or recurrence from the browser clock.
- `hooks/useChallenges.js` shares scoped server data, refreshes after Pulse and
  pin changes, and fences responses by account/credential/selected-child identity.
- Existing boss/collection components and routes remain reference and legacy
  compatibility surfaces; the new page does not spend saved quest scrolls.
- `/__design#task-folio` demonstrates these same presentation components with
  synthetic goals and local-only pin/detail and parent/child preview controls.

### 3D Prints in Rewards

Rewards → 3D Prints (`/treasury?tab=forge`) supports both reward requests and project parts. Backend contract lives in [`apps/printing/CLAUDE.md`](/apps/printing/CLAUDE.md);
the frontend half is under [`pages/forge/`](/frontend/src/pages/forge/):

- `index.jsx` — request orchestrator with a simple page header, parent review
  queue, request cards and closed history. Children can accept frozen coin
  quotes; saved mutation receipts remain visible when refresh fails.
- `usePrintRequestRefresh.js` — shared by Rewards and project Materials:
  refreshes request summaries every 10 seconds during printing or 45 seconds
  for other open requests. Awaits each read, skips hidden browser tabs, pauses
  while a request/decision sheet is open, and cleans up on completion/unmount.
- `../manage/PrintingSection.jsx` — parent-only monthly budgets, coin rates,
  printer status/registry and unmatched-job reconciliation. Its role gate
  prevents administration reads for children. The request page links here.
- `../project/ProjectPrints.jsx` — Materials entry for a verified project,
  opening the same request form with `project_id` and showing its scoped
  requests. Parent Today counts all pending print pages separately from bulk
  approvals and links to the review flow, which requires slicer/quote inputs.
- `PrintRequestCard.jsx` — thumbnail (placeholder when null), colour chip,
  needed-by, `StatusBadge`, the reason, live `ProgressBar` while a job runs, and
  the **decoded** `latest_job.failure_reason` on failure — never an HMS code.
- `PlateFilenameChip.jsx` — the minted `plate_filename` with a copy button.
  Request cards show it only with the parent-only `showPlateFilename` prop.
  Shared by the card and the approval sheet because that string *is* the flow:
  matching is `normalize_subtask_name(reported) == request.slug`, so a plate
  saved under the wrong name lands as an unlinked job someone has to hand-link.
- `PrintRequestModal.jsx` — the child's submit form. Link **or** upload; links
  POST JSON, an upload switches to multipart (which is why `createPrintRequest`
  accepts either an object or a `FormData`). The `/print-requests/preview/`
  scrape on blur/paste is soft — a preview `error` renders as a hint, never a
  blocker, because `enrich_request_metadata` gets another shot after submit.
- `ApprovalSheet.jsx` — grams + minutes from the slicer, notes, Approve/Reject.
  A **409** carries `problems[]` and the budget summary; the sheet renders them
  and offers an explicit "Approve anyway" that re-POSTs with `force: true`.
  Branching is on `err.status`, never on the message string.
- `BudgetPanel.jsx` — parent-only. Two independently-capped dimensions; a null
  cap renders "No cap" (zero is a real cap meaning "nothing this month") and a
  negative remaining renders as an ember overage rather than being clamped.
  Inline cap editor, append-only adjustment form, recent ledger.
- `FilamentChip.jsx` — one loaded spool, read-only on the printer card and a
  button in the request form. Honest about absence: a null `hex` (unread tag)
  is a dashed outline, never black — `#000000` is real black filament — and a
  null `remain_percent` (any spool without an RFID tag, i.e. every third-party
  roll) renders no number rather than "0%".
- `FilamentPicker.jsx` — the swatch row above the Colour field. Reads
  `live.filaments` from each active printer's status, dedupes by name+colour,
  and **fills the free-text field in** rather than replacing it: the AMS
  reports what is loaded *now*, and the plate may be sliced days later. It
  stores the readable name, never a slot. Renders nothing — not an error, not
  an empty state — when the printer is asleep or the call fails, because the
  form has to keep working exactly as it did before.
- `PrinterStatus.jsx` — polls `GET /api/printers/<id>/status/` on the
  `ProjectIngest` pattern (setTimeout recursion, ref cleared on unmount,
  `document.hidden` skip), 10s while a job is open and 45s idle. It reads our
  fan-out snapshot rather than opening MQTT: the X1's broker tolerates ~four
  clients total, shared with Studio / Handy / Home Assistant.
- `UnlinkedJobsPanel.jsx` — parent-only Handy escape hatch. Picker is filtered to
  `LINKABLE_REQUEST_STATUSES` so a rejected or cancelled request can never
  absorb a print. It also has to be *emptyable* — every print a parent runs
  for themselves lands here and matches nothing — so each row carries
  **Dismiss** (soft hide, reversible from the "Show N cleared prints" toggle)
  and **Delete** (irreversible, behind a `ConfirmDialog`). The page fetches
  the cleared rows as a second `listPrintJobs({unlinked, dismissed})` call
  rather than a flag on the first, so the default list stays exactly what
  needs attention. The server refuses both actions on a running or linked
  job; the panel renders that refusal in its `ErrorAlert` rather than
  no-op'ing.
- `PrinterConfigPanel.jsx` — parent-only printer registry. Credentials are
  write-only; blank fields on an edit mean "keep what is stored". The server
  refuses an incomplete printer, so a 400 comes back keyed by field
  (`{access_code: [...]}`) and `fieldErrors` from [`utils/api.js`](/frontend/src/utils/api.js)
  hangs each message on its own input rather than letting the client's
  `JSON.stringify` fallback print raw JSON in the banner. Anything the form has
  no input for still falls through to the banner. Cards render
  `credential_hint` (or `last_error`) beneath the meta line — the red badge on
  its own never said *which* field was blank.
- `forge.constants.js` — tone maps, `formatGrams` / `formatMinutes` /
  `formatCap`, `usagePercent`, `budgetProgress`, `jobProgressLabel`,
  `isJobOpen`, `describeFilament`.

Children see their own requests, confirmed pricing and per-request print
progress. Parents additionally see the approval queue. Hardware administration
lives under Manage → 3D Printing, and calendar/notification destinations use
Rewards while saved Tasks links remain compatible.

## Atlas hub ([`pages/atlas/index.jsx`](/frontend/src/pages/atlas/index.jsx))

### Shared collection navigation

The October 2026 collection refresh replaces book spines and labeled drawers with the shared Meadow picker in `components/atlas/TomeShelf.jsx` and `TomeSpine.jsx`. Their existing descriptor API remains compatible. Default collection cards wrap in a responsive grid with readable titles, counts, optional saved progress and a current-selection marker. All-`vessel` filters use compact wrapping pills on phones and desktop, with one keyboard-navigable tablist.

This updates Badges, Lorebook, Bestiary Codex, Character cosmetics, Trials status chapters, Yearbook, journal chapter selection and the admin Codex. Inventory, Sketchbook, Companion/Mount filters and Trials kinds use the compact variant. Earned/trained/owned proportions come from existing server data; quantities, quest status counts and years do not imply completion. Skills keeps the separate Wayfinder hierarchy. The `/__design` page demonstrates both patterns with local synthetic data and no account data required.

Three top-level `ChapterHub` tabs — **Skills** ([`pages/Achievements.jsx`](/frontend/src/pages/Achievements.jsx)), **Badges** ([`pages/Badges.jsx`](/frontend/src/pages/Badges.jsx)), **Sketchbook** ([`pages/Portfolio.jsx`](/frontend/src/pages/Portfolio.jsx)). Skills and Badges are siblings, not sub-tabs. Badge admin (create/edit/delete) lives under Skills → Manage because [`ManagePanel`](/frontend/src/pages/achievements/ManagePanel.jsx) is a single cross-cutting admin surface for categories/subjects/skills/badges — don't duplicate it on the Badges tab.

A fourth tab — **Yearbook** — sits inside the Atlas hub: lifelong chronological chapter timeline with `ChapterCard` variants (current/past/future), `TimelineEntry` with kind-iconed rows, `EntryDetailSheet` (BottomSheet), and `ManualEntryFormModal` for the parent-only add-memory flow.

### Skills page ([`pages/Achievements.jsx`](/frontend/src/pages/Achievements.jsx), "Wayfinder")

The **Wayfinder** follows the existing Category → Subject → Skill hierarchy. [`SkillTreeView`](/frontend/src/pages/achievements/SkillTreeView.jsx) opens on the category overview, then navigates through a category's subject map, a subject's skill rows, and an inline skill detail. [`WayfinderMap.jsx`](/frontend/src/pages/achievements/WayfinderMap.jsx) supplies the category and subject maps and their heading. Names and icons come from the real catalog; each map shows one level of the hierarchy rather than placing the entire skill tree in one diagram.

**Catalog versus progress:** `getSkillCatalog()` gathers all pages of the existing `/api/subjects/` and `/api/skills/` list endpoints in parallel. These flat catalog lists supply counts and ID destinations for prerequisite navigation. Actual private skill progress comes from `getSkillTree(categoryId)` at `/api/skills/tree/{categoryId}/`: category summary, nested subjects, XP, levels, authored level names, unlock states, and prerequisites. Catalog entries must not stand in for a user's progress. Category summary level is an aggregate, not a prerequisite stage or a completion percentage. The orchestrator fences stale responses so a slower previous request cannot replace the active category.

**Subject and skill views:** selecting a subject renders [`SkillVerse`](/frontend/src/pages/achievements/SkillVerse.jsx) with `variant="wayfinder"`, retaining the shared skill XP and tier vocabulary. [`WayfinderSkillDetail`](/frontend/src/pages/achievements/WayfinderSkillDetail.jsx) renders inline with the selected skill's actual XP, level name, unlocked state, and required skills and levels. Prerequisite destinations are resolved by ID through the catalog, including requirements in a different subject or category.

**Navigation and search:** breadcrumbs expose the current category and subject; Back uses an in-memory history so following a cross-category requirement can return to the skill that opened it. Each visit starts at the overview; navigation is not restored from localStorage. [`CatalogSearch`](/frontend/src/components/CatalogSearch.jsx) filters skill names and descriptions within the current category or subject. These views use the existing backend responses and authorization.

Parent View|Manage toggle in the header routes to [`ManagePanel`](/frontend/src/pages/achievements/ManagePanel.jsx).

### Badges page ([`pages/Badges.jsx`](/frontend/src/pages/Badges.jsx), "Sigil Case — Reliquary Codex")

View-only illuminated codex that groups badges into seven criterion-family chapters (Chronos · Ventures · Mastery · Coffers · Scholar · Adventure · Reliquary), mirroring how [`apps/achievements/criteria.py`](/apps/achievements/criteria.py) already buckets criterion types by subsystem.

- [`SigilCodex`](/frontend/src/pages/achievements/SigilCodex.jsx) orchestrates — an [`IncipitBand`](/frontend/src/components/atlas/IncipitBand.jsx) hero, seven shared collection cards showing earned/total counts, and the selected [`CollectionFolio`](/frontend/src/pages/achievements/CollectionFolio.jsx). Chapter selection and remembered defaults remain page-owned.
- [`collections.constants.js`](/frontend/src/pages/achievements/collections.constants.js) owns the taxonomy: `COLLECTIONS` array (id/rubric/letter/name/kicker/criteria), `collectionForCriterion` (falls back to `reliquary` for unknowns so new backend criteria never render as "undefined"), `groupBadgesByCollection`, `rarityCounts`, `unlockHint` (plain-English template for every known criterion_type; falls back to `badge.description` for unknowns), `ladderSiblings` (same-criterion_type progressions for the detail sheet).
- Each folio is a `<section aria-labelledby>` with a rubric numeral (§I–§VII), an `IlluminatedVersal` drop-cap whose gilt fills with chapter progress, a slim [`RarityStrand`](/frontend/src/components/atlas/RarityStrand.jsx) (5-segment distribution band sized by per-rarity totals, inner fill by earned/total), and the 2/3/4/5-col sigil grid. Empty chapters still render the header + "no seals yet in this chapter" whisper so the codex skeleton reads consistently for fresh users.
- [`BadgeSigil`](/frontend/src/components/atlas/BadgeSigil.jsx): earned sigils keep `RARITY_HALO` + foil sheen + `animate-gilded-glint` for recents (≤ 7d via `isRecentlyEarned`) and now show a `+{xp_bonus} XP` gilt ledge. Unearned sigils render as **debossed intaglios** — pressed ring with inset shadow, grayscaled icon, and a single-line font-script `unlockHint(badge)` line beneath the name. `aria-label` still ends in `· not yet earned`.
- [`BadgeDetailSheet`](/frontend/src/pages/achievements/BadgeDetailSheet.jsx) accepts `allBadges` + `earnedIds` so it can render (a) a `"from the reliquary of {chapter} · §N"` script chip, (b) a "to earn" / "you earned this by" unlock card with the plain-English hint, and (c) a ladder strip of Tier I/II/III rungs when 2+ badges share a criterion_type (current rung highlighted; earned siblings styled moss; later rungs dashed + muted). Pass-through from `Badges.jsx` via `useMemo`'d `earnedIds` Set.
- **Hint-vs-description dedupe**: the detail sheet suppresses the hint card when `unlockHint(badge)` falls back to `badge.description`, so the same prose doesn't render twice (description already sits under the rarity ribbon). Sigil tiles are unaffected — they never show the description, so the hint always renders on unearned tiles.
- **Accessibility**: every folio exposes `role=region` via `<section aria-labelledby>`; `RarityStrand` carries `role="img"` with a descriptive aria-label ("4 of 21 sealed — 2 of 7 common, 1 of 6 uncommon, …"). All gilt / flourish / glint effects sit inside the existing `@media (prefers-reduced-motion: reduce)` rules in [`index.css`](/frontend/src/index.css).
- Reads `/api/achievements/summary/` + `/api/badges/`. The backend omits unearned collectible goals that exceed achievable supported capacity, including relevant saved legacy progress; earned badges remain visible and selectable as trophies. Use `catalog_available` when combining responses. The retired `BadgeSigilGrid.jsx` is gone; `SigilCodex` is the only consumer in the tree.

### Sketchbook page ([`pages/Portfolio.jsx`](/frontend/src/pages/Portfolio.jsx))

Flattens the `/api/portfolio/` response (`{projects, homework}`) into one unified item list, then re-groups based on the active mode. Toolbar: four filter pills (`All` / `Projects` / `Homework` / `Timelapses`) with live counts + a `By project` / `By date` sort toggle. By-date groups by `"MMMM YYYY"` (newest first). Each tile is a `<button>` — click opens an inline lightbox (fixed overlay at `z-50`, prev/next `IconButton`s, click-backdrop-to-close) scoped to the current filtered/ordered set.

- **Audio playback** (2026-05): when the active tile is a Creation that carries an `audio` attachment, the lightbox renders an `<audio controls>` next to the image — fix for the upload-but-never-playback latent bug.
- Trash icon in the top-right corner is gated by `canDelete = user.role === 'parent' || item.ownerId === user.id` and routes through [`ConfirmDialog`](/frontend/src/components/ConfirmDialog.jsx) (`role="alertdialog"`, "Remove" label).
- Delete endpoints: `DELETE /api/photos/{id}/` for project photos (permissioned `destroy` on [`ProjectPhotoViewSet`](/apps/portfolio/views.py) — owner or parent; both the row AND the storage blob go), `DELETE /api/homework-proofs/{id}/` for proofs (new [`HomeworkProofViewSet`](/apps/homework/views.py) — destroy-only; the parent `HomeworkSubmission` stays so approval history remains intact).
- The [`PortfolioView`](/apps/portfolio/views.py) response includes `user` on each photo and `user_id` on each homework item so the frontend can gate `canDelete` without an extra lookup.

## Character page / Frontispiece (`/sigil`, route redirected from `/character`, 2026-04-22 redesign)

The inside-cover plate of the journal — personal author-portrait rather than a dashboard. Architecture in [`pages/character/`](/frontend/src/pages/character/):

- [`SigilFrontispiece.jsx`](/frontend/src/pages/character/SigilFrontispiece.jsx) — compact identity/name/level header with the uploaded profile picture and its frame (initial fallback), separately labeled saved avatar preview, compact trophy and real streak statistics. “Customize avatar” opens the dedicated `/profile/customize` screen; Profile does not contain wardrobe editing controls.
- [`avatar-customize/`](/frontend/src/pages/avatar-customize/) — the live preview remains beside the options on desktop and above them on phones, with a separately scrolling options panel and Save/Undo actions. Layout measures the marked shell header and bottom navigation. The authenticated avatar catalog supplies base-specific appearance controls and compatible shared accessory choices. Base identity and equipment are saved separately in `avatar_configuration`: a Knight can reuse the same bow/quiver IDs as an Archer when its attachment bindings are prepared; source pack is provenance, not an equipment restriction. Only prepared base avatars are offered. Current Archer configuration maps to the existing private renderer, including fitted hood hair and saved ordinary hair under a crown. Drafts remain in memory for the same account and credential; Save adopts the confirmed server configuration, failed saves retain the draft, Undo restores the saved look, and the editor Back action asks before discarding. Wardrobe changes do not acquire inventory, grant XP/Coins or change earned cosmetics.
  A reviewed private v2 release renders the 2,880 identity combinations with supplied Idle and requires empty wardrobe slots. Schema 3 adds all wardrobe modules to each complete matching rig, with source-derived rigid bone attachments and palette texture aliases; the frontend can resolve 276,480 combined selections after that release is verified and reviewed. Only the selected pieces render. The hood uses supplied fitted hat hair while retaining the saved underlying hairstyle; the crown retains that hairstyle. Equipment never changes identity-based framing. Older static releases retain the original 64 appearances, and older releases never omit an unsupported saved piece just to render a different look. Missing private models/textures or renderer failure keeps customization and existing Profile controls usable. Idle pauses offscreen, in background tabs and for reduced motion; costume and wardrobe changes reset loading and local playback.
- [`TrophySlot.jsx`](/frontend/src/pages/character/TrophySlot.jsx) + [`TrophyBadgePicker.jsx`](/frontend/src/pages/character/TrophyBadgePicker.jsx) — a wide `AchievementCard` pairs the kit's blank base and gold overlay around the real badge artwork, live name, rarity, and chooser action. The empty slot says "Choose an earned badge"; absent or failed private art preserves the same readable controls. The `BottomSheet` groups earned badges through `groupBadgesByCollection` and displays them in matching tall cards: selecting a badge sets the trophy, and selecting the current trophy clears it (null payload). Generic kit icons do not replace actual badge identities. The older measured frame remains in earned badge details and design examples.
- Two [`CosmeticChapter.jsx`](/frontend/src/pages/character/CosmeticChapter.jsx) folios offer Frames and Titles through the existing DOM presentation. Each [`CosmeticSigil.jsx`](/frontend/src/pages/character/CosmeticSigil.jsx) is equipped, owned or locked; locked supported offers remain noninteractive until owned. Counts exclude unavailable items. [`SavedCosmetics.jsx`](/frontend/src/pages/character/SavedCosmetics.jsx) keeps earlier accessories and unavailable items under Saved collection, with a button to remove a previous active selection. New accessories and accessory equip are unavailable; saved avatar preferences remain independent from earned cosmetics.
- **Color themes**: Profile shows the current Meadow palette name and links to `/settings#appearance`; Settings owns the only selector. The palette stays selected when clicked again. Inventory theme actions use the same destination; saved cover keepsakes cannot expose a second remove control. Theme display names derive from `themes.js` while saved catalog names and ownership remain compatible.
- Per-area shared logic lives in [`character.constants.js`](/frontend/src/pages/character/character.constants.js) — `COSMETIC_CHAPTERS` (slot → rubric/letter/name/kicker), `STREAK_TIERS` + `streakTier(days)` (flame sizing ladder aligned with backend milestone thresholds 1/7/30/100), `mergeSlotCosmetics(slot, owned, catalog, activeId)` (dedupe + sort: equipped → owned → locked, each sub-sorted by rarity then name), `slotRarityCounts` (feeds the strand), `cosmeticLockHint` (server acquisition source, then description, then a neutral ownership hint). Locked cosmetic tiles link to a supplied internal activity/challenge path without equipping or pinning it.
- [`Character.jsx`](/frontend/src/pages/Character.jsx) is a thin orchestrator: parallel fetches via `useApi` for `getCharacterProfile` + optional `getAvatarCatalog` + `getCosmetics` + `getCosmeticCatalog` + `getBadges` + `getAchievementsSummary`, with `useMemo`'d `allBadges`/`earnedBadges` passed to the picker. Equip/unequip + trophy-set all optimistically mutate via `refresh()` without a full page reload.

## Dashboard (role-split)

`Dashboard.jsx` loads `/api/dashboard/` and routes by role. Loading and retry
feedback remain at that shared entry point.

Child Today leads with the running timer or backend's first `next_actions`
recommendation. Your tasks preserves that feed's cross-kind urgency order before
limiting the initial list to five; Show all reveals the rest. Active projects
are always visible under Continue a project, followed by the exact pinned goal
from `useChallenges`. Challenge errors retain their retry, and an unavailable
response never becomes an empty-pin claim. Reflection follows work, then the
since-last-visit recap, status shortcuts and collapsed Rewards & earnings.
The automatic daily bonus uses the same challenge response inside that earnings
disclosure; its closed summary acknowledges a confirmed award. Recent items,
savings and badges follow. Saved accordion preferences remain honored.
An empty priority feed says No urgent tasks right now: this filtered feed cannot
prove that all work is complete or that a family has never assigned anything.

Parent Today shares one account-bound `ParentReviewProvider` with header and
navigation. `useParentDashboard` aggregates chores, homework, redemptions,
creations, proposals, exchanges, prints, pending/disputed timecards and approved
real-world rewards awaiting delivery. A failed source stays unavailable;
loading or partial reads never claim an all-clear. Successful review mutations
invalidate the shared source, and Pulse's body-free family revision catches
co-parent decisions, work changes and household-day rollover. The provider
clears previous-account results and ignores late responses.

`ApprovalQueueList` keeps inline evidence and optional rejection notes. Rows
show waiting age, default to oldest first within each child, and support explicit
selection. Every selected batch shows its work/reward/exchange consequences
before confirmation; proposals and delivery requests cannot be bulk approved.

The always-visible family overview uses `/dashboard/`'s additive
`family_overview`: household-local homework due/overdue/review counts, scheduled
chore status, parent goal progress, recent confirmed accomplishments and
secondary clocked estimates. Its server projection uses bounded family-scoped
queries and never reads journal/reflection bodies. Child links select the same
verified context used by Homework, Chores, Habits, Challenges, Shop, Reading and
Memories. Shared chores are explicitly labelled All children. Parent task/roster
lists read bounded known-endpoint pages before filtering; a failed page cannot
look like an empty child workspace. Child/account changes reset forms and fence
late callbacks.

Parent quick actions lead with Assign homework, New chore and Create goal;
manual corrections and the available Clock follow. New chore/habit sheets lead
with task, child and schedule; rewards are optional and advanced XP, skill,
icon and order controls stay in Advanced. Alternating-week chores preview their
reference week without changing schedule eligibility. Setup suggestions remain
optional links, with no invented completion claims.

### Submission dates and reviewed work

`SubmissionTiming` gives chores two primary dates: Scheduled for (the saved
schedule's `due_on`) and Done on (the saved household `submitted_on`). Chore
rows do not add timing/status badges to this pair or rewrite historical timing
classifications or rewards. Daily
chores use their scheduled day; weekly chores retain the existing Sunday end of
their scheduled week. One-time forms call their single optional date Scheduled
date; unscheduled chores say No scheduled date.

Completion details keeps exact submission timestamps, parent decisions, changed
one-time schedules and legacy recorded periods out of the primary date pair.
Weekly `completed_date` is a Monday period identifier, not evidence of the
original deadline or the day the child did the work. Legacy rows say Not recorded and never infer the original scheduled date. Saved snapshot
timezones take precedence; older timestamps use the current household timezone,
with the app's Phoenix default when it is unavailable.

Homework retains its saved deadline, submission and parent decision, with a
changed `current_due_date` labelled Current due. Neither client rewrites the
server-owned `timing_snapshot` v1 values. Timing labels do not show reward
percentages.

Parent homework and chore pages expose `ReviewedWorkHistory` after a child is
verified by the current roster. It loads known endpoint pages, shows approved
and rejected work, fences child/account/credential changes, and refreshes from
page one after confirmed review events while open. Parent Today uses the same
saved timing component in its approval queue. Assignment cards keep saved
submission dates on both parent and child views. Project/challenge completion
is labelled Completion recorded because approval or delayed processing can
determine that timestamp; it is not proof of when the child physically worked.
Habits retain tap-history semantics, rather than acquiring invented deadlines.

Timecards show saved work notes and automatic clock-out warnings. A disputed
card offers Resolve and approve with a parent note. Mark as paid opens the
existing Greenlight completed-transfer form with the exact child and week;
no money is sent by Abby. Real-world/combined reward approval stays approved
until the parent explicitly confirms handover in Shop's separate delivery queue.
Digital inventory is credited once at approval; delivery never spends more
coins or grants another item. Old fulfilled histories remain unchanged.

## Global header + FAB

`JournalShell` wraps avatar (mobile) + `HeaderStatusPips` (middle, role-aware) + `NotificationBell` (right) in a `sticky top-0 z-30` container that also includes the `HeaderProgressBand` — a labeled, keyboard-accessible summary of the pinned active challenge. Its progress and detail link come from `useChallenges`; an account without a pin receives an inert spacer. The sticky container has a `bg-ink-page` backdrop so page content doesn't bleed through on scroll.

**Gotcha:** the mobile `overflow-x: hidden` guard lives on `body` (not `main`) in `index.css` — putting it on `main` turns `<main>` into a scroll container which traps `position: sticky` inside the main's overflow instead of the window.

**Your tasks on child Today** uses the ranked `next_actions` feed without
regrouping by kind. Backend urgency and tie-breaking stay intact across homework,
chores and habits. Pending homework is excluded server-side; rejected submissions
remain actionable. Homework rows still open `HomeworkSubmitSheet` inline, while
chore and habit rows use their existing endpoints and refresh the dashboard.

`QuickActionsFab` replaces the old `ClockFab` — single bottom-right button that opens `QuickActionsSheet` with role-aware contextual actions: child sees Clock in · Add homework · Submit due (only when a due assignment exists) · Ask for a print (deep-links to `/quests?tab=forge&new=1`, which opens the submit modal on mount) · View challenges (without spending a scroll) · Contribute to hoard (only when an active savings goal exists); parent sees Clock in · Create homework for a kid · Adjust coins · Adjust payment. Reward shop is deliberately **not** in quick actions — browsing rewards is a considered choice and belongs on the Treasury page. Clock-in is still the most common action and is the default focus when opened. The FAB continues to show a running-timer chip while clocked in so the at-a-glance signal is preserved.

## Notifications constants parity

[`components/NotificationBell.jsx`](/frontend/src/components/NotificationBell.jsx) renders a type-specific lucide icon and falls back to a sensible default route when the backend `link` field is empty, via the `NOTIFICATION_TYPE_META` map in [`components/notifications.constants.js`](/frontend/src/components/notifications.constants.js) (`{icon, accent, route}` per type — e.g. `badge_earned` → Award icon, gold accent, `/atlas?tab=badges`). The default route is the safety net: notifiers that forget to set `link` still navigate to a relevant page rather than no-op'ing the click.

**Parity gate**: [`notifications.constants.test.js`](/frontend/src/components/notifications.constants.test.js) hardcodes the backend `NotificationType` enum; the test fails CI when a new value lands on the backend without an entry here, so the bell can't silently degrade to the generic Bell + no-route fallback. Unknown types still fall back gracefully to `BellRing` + null route — but the parity test is what makes that a fail-loud rather than fail-silent path.

## Account lifecycle in Settings

Settings → Account details embeds `settings/AccountLifecycle.jsx`. A fresh,
account/family/credential-bound preview controls contact handoff, self-deletion
and last-active-parent family closure. Contact handoff changes only the display
contact; all parents retain equal access. Parent self-deletion requires an
active same-family successor for shared authored work; personal assignments
and private journals are deleted rather than transferred.
Child-authored shared homework assignments, chores and habits stay with an
active family parent automatically; the child has no successor picker or
parent-only actions. Without an active parent to keep shared work, the preview
blocks deletion until one is active.
Confirmation uses the current Abby password and exact username or family
identifier, held only in memory. Busy forms block repeated writes and dismissal, failures retain the
form, and delayed reads/writes cannot affect a replacement session. A closure
conflict requires a fresh member-count/version review and a new confirmation.
Successful deletion uses `signOutDeletedAccount(capturedToken)` for conditional
local sign-out, without sending a logout request with a deleted credential.

## Profile pictures and characters

`accounts.User.avatar` ImageField → `upload_to="avatars/"`. Self-uploaded through Profile's page-specific `ProfilePictureEditor` component, labeled “Profile picture”; the saved avatar is labeled separately from the profile picture. The hidden file picker has an accessible name and an Upload/Change picture button. Remove picture opens `ConfirmDialog` and sends `PATCH /api/auth/me/ {avatar: ""}`. Upload runs `downscaleImage` (`maxDim: 512`) before multipart delivery. Late preprocessing and responses are fenced by account identity, credential and mounted state. `SigilFrontispiece` and `AvatarMenu` show the saved picture with an initial fallback; the selected frame decorates the Profile picture. `MeView.patch` accepts multipart/JSON; a file replaces the old image, and the empty-string sentinel clears it. `AuthProvider.setUser` refreshes Profile and navigation after the confirmed response.

## Daily reflection and challenges

Child Today owns `dashboard/WellbeingCard.jsx`: today's affirmation and a gentle
entry point to the same Journal shown in Memories. It previews today's saved
entry, names its sharing state, and links to `/chronicle?tab=journal`.
`useJournalCapture` is shared by Today, Journal and Quick actions. It refreshes
`getTodayJournal` before opening the shared `JournalEntryFormModal`, holds
capture on loading/read failures, and chooses create or edit from confirmed
server state. Account/credential keys fence private preview and capture state.
The modal offers one writing field, an optional title, dictation and gentle
ideas, with the existing per-account drafts and immutable save reconciliation.
New entries default private; edits and create-conflict recovery preserve the
existing entry's sharing choice. Confirmations show only server-receipted XP
and Coins, suppress reward celebrations for edits and known saved retries, and
refresh shared balances after saving. The flat daily 2 Coin bonus accompanies
normal journal progression; it is not a promise of the entire coin payout.
Migrated `daily_note` memories appear alongside journals, remain private and
read-only, and offer no sharing or family conversation controls. Timeline and
entry-detail surfaces enforce the same legacy-note privacy.
Parents do not render Today's card. Profile owns identity, picture, character,
frames and titles.
Challenges remains under Tasks → Challenges (`/quests?tab=trials`). Every matching
goal tracks automatically; pinning controls which one is featured. Today displays
`PinnedChallengeCard` and the automatic `DailyChallengeCard` (labeled Today's
bonus). The bonus uses cumulative minutes or an approved task and shows the
actual server-paid Coins/XP without a Claim action. Permanent badge recognition
remains under Progress, separate from time-limited challenges.

## Page list

```
pages/
  Dashboard.jsx                Thin role router — loads /dashboard/ once,
                               branches to ChildDashboard / ParentDashboard
  ChildDashboard.jsx           Child body (HeroPrimaryCard + VitalPipStrip
                               + quest log + WellbeingCard + AccordionSections)
  dashboard/WellbeingCard.jsx   Child Today's affirmation + shared journal entry point
  ParentDashboard.jsx          Parent body (ApprovalQueueList + Week at a
                               glance + Quick adjusts)
  _dashboardShared.js          formatWeekdayDate, mapProjectTone,
                               streakMultiplier helpers shared across both
                               bodies
  Projects, ProjectDetail, ProjectNew, ProjectIngest
  ClockPage
  Chores                       Backing tab for /quests?tab=duties
  Homework/                    index.jsx + sibling AssignmentCard.jsx —
                               backing tab for /quests?tab=study
  Habits                       Backing tab for /quests?tab=rituals
  Movement                     Backing tab for /quests?tab=movement
  Inventory
  bestiary/                    BestiaryHub — Companions/Mounts party tabs
                               + Codex + Hatchery (4 sub-tabs all speaking
                               the Atlas template — see apps/pets/CLAUDE.md
                               for the alignment details)
  quests/                      QuestsHub orchestrator (7 tabs) + QuestFolio
                               shell + quests.constants
  forge/                       3D print requests — index + PrintRequestCard,
                               PlateFilenameChip, PrintRequestModal,
                               ApprovalSheet, BudgetPanel, PrinterStatus,
                               PrinterConfigPanel, UnlinkedJobsPanel,
                               forge.constants
  trials/                      Automatic goals (ChallengeGoalCard,
                               CreateGoalForm, goalDisplay), retained legacy
                               ActiveQuestFolio/QuestCodex/QuestTile,
                               trials.constants)
  Character.jsx, character/    Sigil Frontispiece, TrophySlot,
                               TrophyBadgePicker, CosmeticChapter,
                               CosmeticSigil, character.constants
  avatar-customize/            Dedicated live avatar preview, shared equipment
                               controls, account-bound draft and explicit Save
  Timecards, Payments, Rewards
  Achievements                 Skills tab inside AtlasHub (skill tree +
                               parent View|Manage toggle)
  Badges                       Sibling tab inside AtlasHub — sigil case,
                               view-only
  Portfolio                    Sketchbook tab inside AtlasHub
  yearbook/                    Atlas 4th tab — lifelong chronological
                               chapter timeline; ChapterCard with
                               current/past/future variants, TimelineEntry,
                               EntryDetailSheet (BottomSheet),
                               ManualEntryFormModal, JournalEntryFormModal
  Manage                       Parent CRUD (Children + Co-parents + Project
                               Templates + Rewards + Categories + Subjects
                               + Skills + Badges + Admin)
  SettingsPage                 PageShell width="narrow" rhythm="loose" +
                               six SectionHeader-led ParchmentCard sections
  Login, Signup
```

Page-level `*Card` / `*Verse` / `*Sigil` components (AssignmentCard, CatalogCard, SkillVerse, RewardCard, CoinBalanceCard, ProjectOverridesCard, StepCard) live as sibling files in their owning subfolder. Promote to `components/cards/` only when reused twice.

## Key entry points
- `Dashboard.jsx` — role router.
- `quests/index.jsx`, `quests/QuestFolio.jsx`, `quests/quests.constants.js`.
- `forge/index.jsx`, `forge/forge.constants.js`, `forge/PlateFilenameChip.jsx`.
- `trials/index.jsx`, `trials/QuestCodex.jsx`, `trials/trials.constants.js`.
- `Achievements.jsx`, `achievements/SkillTreeView.jsx`, `achievements/SigilCodex.jsx`, `achievements/collections.constants.js`.
- `Character.jsx`, `character/SigilFrontispiece.jsx`, `character/character.constants.js`.
- `ChildDashboard.jsx`, `dashboard/WellbeingCard.jsx`.
- `yearbook/JournalEntryFormModal.jsx`.
- `Portfolio.jsx`.
