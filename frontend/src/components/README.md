# Components

Shared primitives and composition components for The Abby Project. See [CLAUDE.md](../../../CLAUDE.md#frontendsrc) at the repo root for the full architectural overview.

The web app, Memory Meadow and R3F scenes share a soft storybook direction: bundled Nunito, cream pages, lavender and mint tints, rounded surfaces and controls, and clear icons. Shared navigation and currency symbols use Meadow drawings; utility controls use Lucide. `shared/storybook/presentation.json` supplies the baseline palette and companion presentation; `themes.js` adds readable semantic colors and six coordinated covers. Keep paid art in the private asset pipeline. Legacy component and CSS names remain compatibility APIs; they no longer require parchment, wax or leather effects.

React's `Abby Nunito` face uses the bundled variable TTF with real weights 200–1000, rather than stretching a single semibold face across body and heading styles. Heading weight defaults live in the base CSS layer so component weights can override them. The public source and OFL license remain in `shared/storybook/fonts`; `scripts/storybook/sync_presentation.py` maintains its runtime copy and Unity's fixed weight-600 font. The React font is included in the service-worker precache.

The licensed Meadow/welcome companion is a replaceable artwork preview. It does not represent an owned account species, an evolution unlock or earned progression. Use the server's species `sprite_key` for owned companions and preserve their potion and happiness presentation.

`cards/AchievementCard` composes the private achievement kit's matching base and
gold overlay: `variant="wide"` for Profile and `variant="tall"` for badge
collections, challenges and rewards. Its `as`, `className`, `contentClassName`
and DOM props preserve consumer semantics and live controls. Put flex/grid
content layout in `contentClassName`; the outer element owns the canvas.
The 64px source corners and 96px content-safe insets scale from the card width,
while content determines height. Both images must load before the pair appears;
missing/failed art keeps a readable Meadow surface. Loaded parchment scopes
readable light-surface tokens even on dark covers. Keep actual badge/catalog
identity artwork; `AchievementCardIcon` offers explicit book/heart/compass
illustrations, without assigning them to badges or earning rules. The
`/__design#design-achievement-cards` section previews both shapes and all three
icons at 24/32/40/64/96 CSS pixels. See
[the release contract](../../../docs/operations/achievement-card-kit.md).

## Conventions

### Design library and adoption

`/__design` is the local, synthetic implementation library. It runs without a
backend and never writes account data or grants rewards. Its preview controls
cover all six color themes, narrow layouts, larger text, long content, parent
and child examples, and reduced motion. Device settings and real browser zoom
remain the acceptance checks for the complete accessibility behavior.

Use the library's page recipes and interactive states when composing a screen:

- Utility pages use `PageShell`, `PageHeader` and `SectionHeader`; collections
  and progression compose the existing Meadow collection primitives.
- A failed read is an `ErrorAlert` with recovery, not an empty result. Retain
  available rows during refresh, identify unavailable sources, and use
  `FilteredEmptyState` for a filter that hides saved content.
- Forms reuse the field family, `Button`, `IconButton`, `BottomSheet` and
  `ModalActions`. Keep field errors and the user's input together. Passive
  dismissal checks dirty state; an explicitly named discard action may clear
  the local form. Busy writes prevent repeated submission.
  `BottomSheet` and `useFormState` also guard app-update reloads; a manual form
  calls `usePwaUpdateGuard(dirty || saving)` while it owns unsaved work.
- Editable emoji fields use `IconPicker` from `components/form`. It keeps a
  labeled custom text input and opens labeled, keyboard-accessible presets
  without submitting. Pass `value`, `onChange(string)` and the form's busy
  state; retain the field's label, placeholder and length limit. Its optional
  `options` list contains `[emoji, accessibleLabel]` pairs. Habits retain their
  existing presets; chores, rewards, savings, movement and skill/badge editors
  share the broader set. The Forms example in `/__design` previews the picker.
- `StatusBadge` describes workflow state, `RuneBadge` describes a tone or
  catalog tier, and progress bars describe measured progress. Availability
  and retained ownership remain separate, server-confirmed concepts.
- `NotificationToast` supplies paired surfaces and foregrounds for status
  messages, plus a fixed earned-rarity palette. Its owning stack keeps the
  receipt, navigation, expiration and dismissal behavior.
- Parent child selectors use `ChildContext` with a roster verified by
  `useChildContext`; a URL or remembered ID is never authorization. Audience
  copy names the actual readers: “Only me” and “Shared with parents.”
- `AttachmentField` gives selected files a readable name/size, linked help and
  errors, replace/remove controls and optional image preview. Its owning form
  retains processing, validation and the explicit upload/retry contract.

Every specimen includes imports, usage guidance and real consumer links. Keep
its visible language aligned with the current names in `frontend/CLAUDE.md`;
retained route, prop and component names do not dictate product wording.
Promote a domain component when a second real application surface needs it.
The showcase itself is a verification consumer, not a reason to create a
parallel implementation of an existing component.

For a newly changed screen, check narrow and short phone layouts, readable
foreground/background pairs across covers, 44px interactive targets, keyboard
selection and focus restoration, enlarged text and reduced motion. Add
meaningful request-spy tests for writes and source-specific error recovery.
The gallery and shared-foundation browser fixtures exercise these contracts
without production credentials:

```bash
npm run test:pwa -- e2e/design-gallery.pw.js e2e/design-foundations.pw.js
```

Use these focused checks during composition; the full frontend coverage,
web/native builds and required hosted checks still validate the integrated PR.

### Token-first styling

- Color, font, and font-size values come from CSS custom properties declared in [`../index.css`](../index.css)'s `@theme` block.
- Per-cover overrides live in [`../themes.js`](../themes.js).
- Component-level class strings live in [`../constants/styles.js`](../constants/styles.js); status/rarity color maps live in [`../constants/colors.js`](../constants/colors.js).
- Avoid arbitrary Tailwind values (`text-[10px]`, `bg-[#abc123]`). The project type scale lives in `@theme` as `--text-micro` (10px), `--text-tiny` (11px), `--text-caption` (12px), `--text-body` (14px), `--text-lede` (18px). If a value doesn't fit the existing scale, add a token to `@theme` rather than inlining.
- Hex literals in component code should be migrated to token references. Exceptions are HTML5 `<input type="color">` defaults (user data) and official brand-color SVGs (e.g. Google sign-in logo). Each retention carries an inline `// intentional:` comment explaining why.

### Z-index stack

The app uses three explicit layers. Avoid introducing new z values without updating this table.

| Layer | Class | Used by |
|---|---|---|
| Sticky shell | `z-30` | `JournalShell` header (sticky), `HeaderProgressBand` |
| Modal backdrop | `z-40` | `ModalBackdrop`, `BottomSheet` overlay |
| Modal surface / popover / toast / lightbox | `z-50` | `BottomSheet`, `ConfirmDialog`, `DropToastStack`, `CompanionGrowthToastStack`, `AvatarMenu` (dropdown), `NotificationBell` (dropdown), `ProofGallery` (lightbox) |

Everything that floats above page chrome lives at `z-50`. That means a toast emitted while a modal is open can be hidden behind it, and an open modal will block the notification dropdown until dismissed. If that proves wrong for a specific element (e.g. toasts should always be visible), promote it to a new `z-60` row and update this table in the same PR. Do not introduce ad-hoc z-values without updating this table.

### File layout

- Root `components/*.jsx` — domain-agnostic primitives (Button, Loader, EmptyState, BottomSheet, etc.)
- `components/journal/` — shared storybook surface compositions (ParchmentCard, RuneBand, StreakFlame)
- `components/atlas/` — collection and progress primitives (IlluminatedVersal, BadgeSigil, IncipitBand, ChapterRubric, RarityStrand, mastery.constants). See [Atlas cohort](#atlas-cohort) below
- `components/layout/` — page chrome (JournalShell, ChapterNav, QuickActionsFab)
- `components/modal/` — modal building blocks (ModalBackdrop, SealCloseButton, SealPulseRing)
- `components/dashboard/` — Today-page composites (HeroPrimaryCard, ApprovalQueueList)
- `components/cards/` — promoted page-card components (added when a `*Card` from `pages/` is reused twice)
- `components/icons/` — `JournalIcons` exports rounded Meadow SVGs with current-color outlines and soft cover-token fills; names and `size`/`className` props remain compatible. Share these chapter icons across navigation and `CoinIcon` across progression currency; money keeps its dollar icon.

A component lives in `pages/` until it's reused twice; promote to `components/` (or a sub-folder) on the second use.

#### Card placement rule

Page-specific `*Card` components start as sibling files inside their owning page directory:

- `pages/Homework/AssignmentCard.jsx` — used only by `pages/Homework/index.jsx`
- `pages/manage/CatalogCard.jsx` — used only by `pages/manage/CodexSection.jsx`
- `pages/achievements/WayfinderMap.jsx` + `WayfinderSkillDetail.jsx` + `SkillVerse.jsx` + `PrereqChain.jsx` — Skills-only domain code orchestrated by `pages/achievements/SkillTreeView.jsx`. Wayfinder maps categories and subjects, reuses `SkillVerse variant="wayfinder"` for a subject's skills, and opens skill details inline. Keep this navigation and its catalog/progress distinction page-scoped; see [Skills page](../pages/CLAUDE.md#skills-page-pagesachievementsjsx-wayfinder). The former `FolioSpread` + `SkillDetailSheet` layout used the "tome shelf opening onto an illuminated folio" metaphor introduced in the 2026-04-23 Skills redesign. Reusable `TomeShelf`, `TomeSpine` and `ChapterRubric` remain in `components/atlas/` for other surfaces. The five primitives that backed both Skills and Badges (`IlluminatedVersal`, `BadgeSigil`, `IncipitBand`, `ChapterRubric`, `RarityStrand`) and `mastery.constants` were lifted to `components/atlas/` once a third surface (Lorebook) started importing them — see [Atlas cohort](#atlas-cohort)
- `pages/achievements/SigilCodex.jsx` + `CollectionFolio.jsx` + `BadgeDetailSheet.jsx` — used only by `pages/Badges.jsx`. The "Reliquary Codex" structure (seven criterion-family chapters, each a parchment folio with rubric numeral + illuminated drop-cap + rarity strand) replaced the flat `BadgeSigilGrid` in the 2026-04-22 Sigil Case redesign. Kept under `achievements/` because `ManagePanel.jsx` is the single cross-cutting admin surface for badges, and `collections.constants.js` (the Reliquary chapter taxonomy + `unlockHint`) is badge-domain data that doesn't belong at the shared layer
- `pages/character/SigilFrontispiece.jsx` + `TrophySlot.jsx` + `TrophyBadgePicker.jsx` + `CosmeticChapter.jsx` + `CosmeticSigil.jsx` + `StreakGlyph.jsx` — used only by `pages/Character.jsx`. The 2026-04-22 Frontispiece redesign turns the `/sigil` page into a personal author-portrait plate: illuminated initial + trophy seal hero, four `CollectionFolio`-style cosmetic chapters with locked intaglios for un-owned items, and a live hover preview on journal-cover cosmetics. `TrophyBadgePicker` imports `groupBadgesByCollection` from `pages/achievements/collections.constants.js` — the only cross-page reuse, and it's intentional so the picker speaks the Reliquary Codex's chapter taxonomy
- `pages/bestiary/celebration/usePhasedSequence.js` + `SparkleBurst.jsx` + `PotionAura.jsx` — used only by `pages/bestiary/PetCeremonyModal.jsx`. The phased-sequence hook + sparkle/aura primitives back the hatch / evolve / breed lifecycle animations (see CLAUDE.md → "Pet lifecycle animations"). Promote to `components/celebration/` if a second surface (e.g. quest-complete modal) reuses them
- `pages/bestiary/codex/BestiaryFolio.jsx` + `codex.constants.js` + `SpeciesTile.jsx` + `SpeciesDetailSheet.jsx` — used only by `pages/bestiary/codex/BestiaryCodex.jsx`. Mirrors the Reliquary's `SigilCodex` + `CollectionFolio` + `collections.constants.js` shape applied to the Bestiary (chapter taxonomy: Bound in Lore / Bonded / Hatched / Silhouettes — bucketed by progress against each species's `available_potions` set). Kept page-scoped because the chapter predicates are Bestiary-domain — see CLAUDE.md → "Bestiary codex alignment"
- `pages/rewards/RewardCard.jsx` — used only by `pages/rewards/RewardShop.jsx`
- `pages/rewards/CoinBalanceCard.jsx` — used only by `pages/rewards/Rewards.jsx`
- `pages/ingest/ProjectOverridesCard.jsx` — used only by `pages/ingest/ReviewStep.jsx`
- `pages/project/ProjectPlanItems.jsx` (`StepCard` export) — used only by `pages/project/PlanTab.jsx`

Promote to `components/cards/` only when a **second** page imports it. Until then, co-location wins: the card lives next to its only consumer, the parent file stays under ~400 lines, and the import line documents ownership.

Do not pre-emptively promote a card that has only one importer. The cost of moving is small; the cost of premature abstraction is real.

#### Provider contexts live beside the provider, in a `.js` file

`react-refresh/only-export-components` forbids non-component exports from a `.jsx` file, and a React context plus its `use*` hook are exactly that. So a provider ships as two files: `XProvider.jsx` exporting only the component, and a sibling `x.context.js` holding `createContext` + the hook. Current pairs: [`providers/SpriteCatalogProvider.jsx`](../providers/SpriteCatalogProvider.jsx) + [`providers/spriteCatalog.context.js`](../providers/spriteCatalog.context.js), and [`pwa/PwaStatusProvider.jsx`](./pwa/PwaStatusProvider.jsx) + [`pwa/pwaStatus.context.js`](./pwa/pwaStatus.context.js). Import the hook from the `.context.js` module, never re-export it from the `.jsx` — that re-triggers the rule.

#### Per-area shared constants

When a page-area has constants used by both a parent and an extracted card (e.g. XP thresholds, type orderings), house them in a sibling `.constants.js` file rather than exporting from the parent component file. ESLint's `react-refresh/only-export-components` rule forbids non-component exports from a `.jsx` component file; using a separate `.constants.js` keeps both the lint rule happy and the constant in lockstep across consumers.

Examples: [`pages/achievements/skillTree.constants.js`](../pages/achievements/skillTree.constants.js) holds `XP_THRESHOLDS` (the level curve used by Skills domain components); [`components/atlas/mastery.constants.js`](./atlas/mastery.constants.js) holds the Illuminated Atlas shared vocabulary — see [Atlas cohort](#atlas-cohort) for the full export list; [`pages/achievements/collections.constants.js`](../pages/achievements/collections.constants.js) holds the Reliquary Codex taxonomy — `COLLECTIONS` (seven chapters keyed by criterion family), `collectionForCriterion` / `collectionForBadge`, `groupBadgesByCollection`, `rarityCounts`, `unlockHint` (plain-English template for every known `criterion_type` — passed to `<BadgeSigil hint={...}>` by `CollectionFolio`), and `ladderSiblings` (tier progressions for the detail sheet); [`pages/character/character.constants.js`](../pages/character/character.constants.js) holds the Frontispiece taxonomy — `COSMETIC_CHAPTERS` (four cosmetic slots keyed to rubric numerals + drop-cap letters), `STREAK_TIERS` + `streakTier(days)` (flame-size ladder aligned with backend streak milestones), `mergeSlotCosmetics` (dedupe + sort owned against catalog), `slotRarityCounts`, and `cosmeticLockHint`. The Reliquary chapter taxonomy and the cosmetic chapter taxonomy are deliberately page-scoped — only the rarity / progress / chapter-numeral vocabulary is shared.

### Dropdowns

Use `SelectField` from `components/form` for a choice from a list, including
compact toolbar filters (`variant="filter"`). Its shared `Dropdown` control
styles both the trigger and the open list with Meadow tokens across all six
covers. Keep passing `<option>` and `<optgroup>` children and reading
`event.target.value`; option values and saved API payloads stay the same.
The design library's [Dropdowns](/__design#design-dropdowns) section includes
grouped, long, disabled, error and modal examples.
Menu choices wrap; the closed field keeps one line with ellipsis and a full
text tooltip, preserving compact form and filter layouts.

Every dropdown needs a visible `label`, an external label linked by `id`, or
an `aria-label`. Error and help text remain associated with the trigger.
Arrow keys, Home/End and typing move through enabled options; Enter/Space
confirms, Escape cancels, and Tab continues through the form. Opening and
browsing a list does not submit the form or change its saved selection.
Use the existing action-menu components for commands rather than putting
actions in a choice list.

Consumer tests use `selectDropdown(user, control, value)` from
`src/test/selectDropdown.js` to open the real menu and choose an enabled
option. Browser fixtures use `e2e/dropdown-helpers.js` for the same interaction.
Do not change a hidden form control directly in interaction tests.

### Accessibility roles

`AddToCalendar` opens a shared `BottomSheet` with a [Google event template](https://developers.google.com/workspace/calendar/api/concepts/inviting-attendees-to-events) and an [Apple Calendar `.ics` import](https://support.apple.com/guide/calendar/import-or-export-calendars-icl1023/mac). It accepts a saved event via `event`, and optionally `dateEditable`, `dateHelp`, and `validateDate` for choosing a duty reminder day. Invalid or missing dates render no trigger. Keep the trigger outside navigation links/buttons. Exports follow [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545) and never read browser credentials or the current page's query/fragment. Show one-time-copy behavior; later source changes do not update the calendar event.

Shared primitives carry consistent ARIA roles. Match these when building new ones:

| Primitive | Role | Why |
|---|---|---|
| `Loader` | `status` + `aria-busy="true"` | Non-urgent transient state |
| `EmptyState` | `status` | Non-urgent informational region |
| `ErrorAlert` | `alert` | Errors interrupt — assertive politeness |
| `ProgressBar` / `QuillProgress` | `progressbar` + `aria-valuenow/min/max` | Widget with measurable state |
| `BottomSheet` | `dialog` + `aria-modal="true"` + `aria-labelledby` | Modal surface |
| `SelectField` / `Dropdown` | `combobox` + controlled `listbox` / `option` | One tab stop, virtual option focus, selected and disabled states, grouped choices |
| `ConfirmDialog` | `alertdialog` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby` | Destructive-action modal |
| `TomeShelf` / `TomeSpine` | `tablist` + `tab` + `aria-selected` + one tab stop | Wrapping collection cards or compact filter pills; Left/Right wrap, Home/End select first/last, keyboard focus stays with selection |
| `TabList` | `tablist` + `tab` + `aria-selected` + one tab stop | Left/Right wrap and select; Home/End select first/last; horizontal rail scrolling respects reduced motion |

Use React's `useId()` to generate per-instance IDs for `aria-labelledby` / `aria-describedby` so multiple stacked instances don't collide.

`BottomSheet` and `ConfirmDialog` share `modal/useModalFocus.js`: only the topmost modal handles Tab and Escape, and closing it restores focus to its opener. Destructive confirmations initially focus Cancel. Use this shared hook for modal surfaces instead of adding competing document keyboard listeners.

Text buttons, icon buttons (including `size="sm"`) and filter selects share a 44px minimum touch target. Section and page header actions stack on phones and wrap within the available width. Long dialog titles wrap beside the close control; confirmations and header menus scroll within the viewport on short screens. `IncipitBand` uses one decorative versal that grows from 48px on phones to 96px at `sm`, preserving room for its title. `npm run test:pwa -- e2e/mobile-ui.pw.js` checks shared-control geometry at 320, 375, 768 and 1280px and confirmation reachability on a short phone screen.

For icon-only interactive elements, an `aria-label` is mandatory — the upcoming `<IconButton>` primitive enforces this; raw `<button>` tags wrapping a single Lucide icon need it added by hand.

When a `ProgressBar` or `QuillProgress` accepts an `aria-label`, prefer a context-rich one (e.g. `"${skill.name} XP progress toward level ${n+1}"`) over the default if the page renders multiple bars.

`QuillProgress` is a variant of `ProgressBar` with a hand-drawn quill-stroke SVG overlay — use it for mastery/progression contexts (skill XP, category chapters), keep `ProgressBar` for neutral progress (savings goals, assignments complete). Both share the same ARIA contract and `color` prop so they're substitutable when the aesthetic needs to change.

### Page shell + section header

Two primitives keep page-level vocabulary consistent across the journal:

- **`<PageShell width="wide|narrow" rhythm="loose|default|tight" animate variants>`** ([`./layout/PageShell.jsx`](./layout/PageShell.jsx)) — root wrapper for page bodies. Replaces the copy-pasted `<motion.div className="max-w-6xl mx-auto space-y-5">` pattern. Owns the spine width (`max-w-6xl` / `max-w-3xl`), vertical rhythm (`space-y-6` / `space-y-5` / `space-y-3`), and the fade-in animation. Outer horizontal padding stays with `JournalShell` — `PageShell` does NOT add px, so it can't double-pad. Callers that supply `variants` (e.g. the dashboards using `inkBleed`) take over the motion config; otherwise the default `opacity/y` fade applies. Set `animate={false}` for error fallback returns or pages that animate their own body.
- **`<SectionHeader title index kicker count actions as="h2">`** ([`./SectionHeader.jsx`](./SectionHeader.jsx)) — non-collapsible sibling of `<AccordionSection>` for sections that should always be open. Mirrors `AccordionSection`'s vocabulary (kicker, rounded numbered marker via `index`, `RuneBadge` count, supporting body line) so the two read as a family. Use the `actions` slot for right-aligned buttons or filter controls.
- **`<ChapterMarker index>`** ([`./atlas/ChapterMarker.jsx`](./atlas/ChapterMarker.jsx)) — decorative rounded number badge shared by headings and collection folios. Supply a zero-based `index` or a taxonomy's numeric label as children. `chapterMark` supplies one-based Arabic labels; existing shelf medallions display those labels directly. All marks are hidden from assistive technology because adjacent headings name the section. Readable metadata uses prose such as “Chapter 2”.

#### Spacing rhythm — 3 tiers

The audit found `space-y-3` (default), `space-y-6` (loose), and `space-y-2` (tight) dominate. Document the convention; don't introduce new ad-hoc spacings.

| Tier | Vertical | Grid/flex gap | Use for |
|---|---|---|---|
| Loose | `space-y-6` | `gap-4` | Chapter breaks, major page sections |
| Default | `space-y-5` → `space-y-3` | `gap-3` | Cards, list items, rows |
| Tight | `space-y-2` | `gap-2` | Form fields, stacked metadata |

`PageShell rhythm="..."` is the only consumer of this scale; inside pages, just pick from these utilities directly.

### Modal overlay tokens

The four `.modal-*` classes in `index.css` (`modal-ink-wash`, `modal-vignette`, `modal-seal-ring`, `modal-seal-ring-strong`) reference per-cover-overridable `--color-modal-*` tokens. `themes.js` may diverge these per cover — e.g. Vigil's dark surface needs a lighter wash. Three Hyrule defaults (`--color-modal-wash`, `--color-modal-vignette-edge`, `--color-modal-shadow`) happen to share `rgba(45,31,21,0.45)` but represent three distinct semantic roles; do not dedupe.

### Collection navigation

`TomeShelf` and `TomeSpine` retain their existing names and flat item API for callers, but render Meadow collection navigation. Default `codex` items form a responsive grid of cards with horizontal titles, an icon, a count chip, optional progress and a visible current-selection marker. An all-`vessel` set forms compact wrapping filter pills at every width. There is one semantic tablist and one set of controls; phone and desktop layouts share focus and selection.

Pass `{ id, name, icon, chip?, progressPct?, tier?, ariaLabel?, variant? }`. Counts and progress come from the owning page: earned/total badges, trained/total Lorebook entries, and owned/total cosmetics are meaningful proportions. Quest status counts, inventory quantities, media filters and year labels carry no completion percentage. Full titles wrap instead of being truncated or rotated. All colors resolve through the current cover tokens; these controls have no leather, drawer, bookmark or shelf effects.

Use the default cards for collection buckets and `variant: 'vessel'` for compact filters. Skills uses its page-scoped Wayfinder maps because Category → Subject → Skill is a genuine hierarchy. Collection buckets do not become connected paths. `/__design` shows a local Wayfinder drilldown and separate badge, Lorebook and filter examples with synthetic data.

Compatibility hooks `data-spine-id`, `data-spine-variant`, `data-active` and `data-tier` identify items and state. Test roles, selected state, focus, counts and progress; obsolete ornamental hooks have been removed. Keyboard navigation reveals an offscreen destination with the nearest necessary scroll, accounting for `JournalShell`'s marked sticky header and mobile navigation. Selection indicators reserve space so selection does not reflow the controls. Mounting and external selection never scroll the page or take focus from another control.

### Atlas cohort

The Illuminated Atlas vocabulary lives at `components/atlas/`. It's the visual language the Skills page introduced — drop-cap **versals** with gilt fill tied to progress, rarity-haloed **sigils**, **rubric** numerals (§I/§II) for chapter markers, slim **rarity strands** for distribution at a glance, and **incipit bands** for chapter openers. Because every primitive resolves through the cover tokens in `themes.js`, an atlas tile painted on Hyrule and on Vigil reads with the same hierarchy on both — no per-cover branches in component code.

Use these primitives whenever a surface is meant to feel like an authored chapter rather than a form. Current consumers: the Skills Wayfinder (shared progression vocabulary), the Reliquary Codex, the Sigil Frontispiece, the Lorebook folio, Bestiary (all four sub-tabs wear `IncipitBand` heroes; Companions/Mounts use `TomeShelf variant="vessel"` for filter pills; the Codex is a full `IncipitBand` → `TomeShelf` → `BestiaryFolio` shape mirroring SigilCodex), Project detail (status-driven versal + milestone numerals), Yearbook chapter cards (current-year IncipitBand, past-year small versal), and the dashboard hero (versal on clocked / next-action / quest-progress variants + AccordionSection chapter numerals).

| File | Export | Use |
|---|---|---|
| `IlluminatedVersal.jsx` | `<IlluminatedVersal letter size progressPct level maxLevel rarity />` | Drop-cap with gilt fill tied to progress. `size`: `sm` / `md` / `lg` / `xl`. `xl` is hero-incipit territory; `md` is row-leading; `sm` is detail-sheet header. Mastered tiers (cresting / gilded) wear a `RARITY_HALO` ring keyed off `rarity`. `aria-hidden` — caller carries the semantic text in adjacent body |
| `BadgeSigil.jsx` | `<BadgeSigil badge earned earnedAt hint onSelect />` | Wax-seal medallion for any criterion-earned achievement. Earned sigils carry `RARITY_HALO`, foil sheen, and an `xp_bonus` ledge. Unearned sigils render as debossed intaglios; pass `hint` (string) for the script unlock copy underneath. `hint` is caller-supplied so the primitive stays domain-agnostic — Reliquary Codex passes `unlockHint(badge)` from `pages/achievements/collections.constants.js`; other surfaces can pass a different string or omit it |
| `IncipitBand.jsx` | `<IncipitBand letter title kicker progressPct counts />` | Chapter opening band. Versal + display-serif title + script kicker; `counts` (the rarity strand counts shape) renders inline below the title |
| `ChapterMarker.jsx` | `<ChapterMarker index>` or `<ChapterMarker>{label}</ChapterMarker>` | Decorative numbered Meadow waypoint; rounded mint fill with readable cover ink |
| `ChapterRubric.jsx` | `<ChapterRubric index name icon summary />` | Numbered waypoint + section title. Use for nested collection sections within a page |
| `RarityStrand.jsx` | `<RarityStrand counts compact className />` | Slim 5-segment band, one segment per rarity tier sized by total, fill within each segment by `earned/total`. `role="img"` with a descriptive `aria-label` enumerating each segment |
| `mastery.constants.js` | `PROGRESS_TIER`, `TIER_BADGE_TONE`, `tierForProgress`, `RARITY_HALO`, `CHAPTER_NUMERALS`, `chapterMark`, `countIlluminated`, `RECENT_EARNED_DAYS`, `isRecentlyEarned`, `RARITY_KEYS`, `RARITY_ORDER` | Atlas vocabulary. `tierForProgress({ unlocked, progressPct, level, maxLevel })` resolves to one of `PROGRESS_TIER` (`locked` / `nascent` / `rising` / `cresting` / `gilded`) — the same five tiers drive `IlluminatedVersal` fill color, shared collection progress bars, and `SkillVerse` progression states in Wayfinder. `RARITY_HALO[rarity]` is the canonical ring + glow for any earned thing |

**Tier is expressed through `PROGRESS_TIER`'s two channels — `bar` and `chip` — never as applied ornament.** A folio wears its tier as the versal's gilt fill, the progress bar, the stat values, and a `RuneBadge` on its kicker (`TIER_BADGE_TONE` maps the five rungs onto the badge's `ink` / `moss` / `teal` / `ember` / `gold` tones). This matches `QuestLogEntry`, which signals all four of its states purely as surface + border tint, and `SkillVerse`'s legacy folio variant, which tints the versal and level numeral. A tier-tinted band was tried on the folio verso and removed: it was the only element in the app encoding state as a decorative band, its `--color-headband-*` hexes were the only tier colors not resolving through cover tokens, and it restated a tier the card was already showing three other ways. Collection cards use counts and optional progress bars; binding headbands have been removed.

CSS contract (declared once in [`../index.css`](../index.css), reused by every cohort consumer):

- `.versal-gilt` — `background-clip: text` + linear gradient using `--versal-fill` custom property as the fill stop. The variable is set inline by `<IlluminatedVersal>` based on `progressPct`. Underlying letterform is drawn twice (a stroke in `ink-whisper` + the gilt overlay) so the un-illuminated portion stays visible
- `--color-gold-leaf`, `--color-rarity-{common,uncommon,rare,epic,legendary}` — cover-tuned color tokens. Don't write hex literals for these; reach for the token
- `@keyframes halo-rise` (`.animate-halo-rise`) — radial expansion glow on freshly-mastered tiers
- `@keyframes gilded-glint` (`.animate-gilded-glint`) — one-shot foil sheen for sigils earned within the last `RECENT_EARNED_DAYS` (default 7)
- All animations sit inside the `@media (prefers-reduced-motion: reduce)` block already in `index.css` — adding a new atlas primitive doesn't require a new reduced-motion rule

When applying atlas vocabulary to a new page, prefer composition over invention — wrap an existing card in a sigil, lead a section with a rubric, replace a plain title with a versal. Don't introduce a new rarity tier, halo color, or keyframe inside an apply phase; the cohort's value is its consistency.

### Task folio

The Tasks tabs share the folio shell at [`pages/quests/QuestFolio.jsx`](../pages/quests/QuestFolio.jsx): a summary beside the working list on desktop, with the summary above the list on mobile. Each tab supplies its own `letter` / `title` / `kicker` / `stats[]` / `progressPct` / `rarityCounts`. Keep the existing component name for compatibility; the design pattern is **Task folio**.

Challenges composes this shell through [`pages/trials/ChallengesFolio.jsx`](../pages/trials/ChallengesFolio.jsx). Its working list keeps pinned focus and open parent goals visible, shows up to three progressing bonus challenges, and places remaining bonus goals and history in collapsed sections. `/__design#task-folio` renders that same presentation with synthetic data and local pin/detail controls; it does not load or mutate account data.

Per-page tier concepts map onto the Atlas rarity vocabulary via [`pages/quests/quests.constants.js`](../pages/quests/quests.constants.js): `difficultyToRarity(1-5)` + `effortToRarity(1-5)` both fan 1→common…5→legendary, and `buildRarityCounts(items, mapper, isEarned)` reduces a list into the `{common: {earned, total}, …}` shape `RarityStrand` consumes. Project `payment_kind` (required / bounty) and Habit `strength` buckets stay as their own existing chip palettes — they're not forced into the rarity ladder. Ventures + Study render a strand on the verso; Duties + Rituals + Movement omit it because their domain doesn't have a rarity distribution.

Test attributes mirror the rest of the cohort: `data-folio-verso="true"`, `data-tier={locked|nascent|rising|cresting|gilded}`, `data-progress={pct}` on the verso aside; `data-folio-recto="true"` on the recto. Within the recto, working-list sections lead with `<ChapterRubric index name>` so the §I/§II/§III numeral progression reads as the chapter's table of contents.

### Pedestal and card artwork

The private Meshtint pedestal/card family lives in [`../pedestal/`](../pedestal/).
`/__design#design-pedestal` includes all 19 UI assets, a 512px/1024px selector
covering all 35 PNG variants, a measured frame example, and the six native GLBs
with their four supplied loops. The [showcase](../pages/design/PedestalShowcase.jsx)
includes imports and consumer links; the [adoption guide](../../../docs/operations/pedestal-card-ui.md)
documents release pins, private import/build verification, scene placement and
device acceptance.

| Component | Props and use |
| --- | --- |
| [`PedestalImage`](../pedestal/PedestalImage.jsx) | `assetId`, `variantId="web"`, `alt=""`, `className`, optional `fallback`. Renders one complete PNG canvas with lazy loading and loading/error fallbacks. Use a nonempty `alt` for meaningful artwork; the default is decorative. `fallback=""` silences decorative placeholders; stars supply their original glyph. |
| [`StorybookFeature`](../pedestal/StorybookFeature.jsx) | `assetId`, `children`. Complete decorative art sits beside content only when the card has room for a 16rem text column; narrower cards stack it above content, including nested desktop grids. Missing/failed art collapses its column; content retains the real identity, progress and actions. |
| [`PedestalFrame`](../pedestal/PedestalFrame.jsx) | `children`, `label="Framed content"`, `className`. Places independent app content inside the gold frame's measured opening, with padding and keyboard-accessible scrolling. Content remains readable when frame artwork is unavailable. |
| [`PedestalPreview`](../pedestal/PedestalPreview.jsx) | `eggAssetId="normal-egg"`, `animate={true}`, `className`, `stageClassName="h-80"`. Shows a decorative native pedestal/egg scene; `eggAssetId={null}` selects the pedestal alone. Includes local off/retry controls and DOM fallbacks. |

Choose asset IDs from [`PEDESTAL_IMAGE_IDS` and `PEDESTAL_EGG_IDS`](../pedestal/pedestalRelease.js).
Normal callers use the pinned private release automatically; the optional
`staged` prop supplies a release fixture for isolated previews/tests.

```jsx
// Imports from a module directly under src/pages/.
import PedestalImage from '../pedestal/PedestalImage';
import PedestalFrame from '../pedestal/PedestalFrame';
import PedestalPreview from '../pedestal/PedestalPreview';

function ArtworkExample() {
  return <>
    <div className="max-w-xs">
      <PedestalImage assetId="card-front-egg-star" alt="Egg artwork" />
    </div>
    <PedestalFrame label="Artwork example" className="max-w-sm">
      <p>Independent application content.</p>
    </PedestalFrame>
    <PedestalPreview animate={false} />
  </>;
}
```

Images default to the 512px web variant. Request `variantId="native"`
explicitly for the 16 available 1024px variants; the three web-only originals
retain their 512px image. Preserve full proportions, transparent margins and
alpha. These older card faces already contain their emblems; keep live content
beside them. This pedestal family supplies no blank card slots or authored
nine-slice borders; the separate achievement kit supplies explicit blank bases,
gold overlays, and resizing guides.

Each native animation take keeps its own complete mesh, rig and common root.
Playback respects reduced motion, visibility and background state.
`HatchingSoon` is repeating anticipation, not a completed hatch. Keep application
controls in accessible DOM and derive game state and outcomes from server-confirmed
responses.

[Hatching](../pages/bestiary/hatchery/Hatchery.jsx) uses the neutral
Normal Egg/pedestal and `card-front-egg-star`. Storybook is an artwork direction
within the Meadow design system: illustrations follow its typography, cover
colors, rounded surfaces, spacing and accessible controls. `ParchmentCard`
keeps a simple border and normal content padding, with no corner ornaments
or reserved decoration gutters. Legacy `flourish` and `seal` props remain
accepted without drawing decorations. Children stay direct so caller layout,
padding overrides and `space-y-*` rhythm continue to apply.
The daily bonus lights a star only after `awarded`;
`StarRating` retains the existing difficulty scale and accessible numeric label.
Profile's featured badge uses the achievement kit's matching wide base and gold
overlay, with its actual `BadgeArtwork`, live title, and `BadgeRarity` inside the
safe content area. Badge collections, child challenge cards, and reward offers
use matching tall pairs. Badge artwork retains its distinct icon fallback in a
quiet well; equipped profile cosmetics remain independent. The earned badge
detail sheet and pedestal design examples retain the older measured gold frame.
Light, Treasure, and the other finished illustrated fronts remain in the design
gallery without automatic catalog, ownership, rarity, or progression bindings.
Keep paid PNGs, GLBs and derived previews in the private asset workflow outside
Git and public preview hosting.

### RpgSprite

`<RpgSprite spriteKey="slug" icon="🐉" size={32} alt="..." className="..." />`

Renders an RPG-domain icon from the runtime sprite catalog. Call sites provide a `spriteKey` (slug string) and an `icon` emoji fallback — slug resolution and URL lookup happen internally via `useSpriteCatalog()` from `SpriteCatalogProvider`. The explicit `cute-chick` / `cute-chick-fledgling` / `cute-chick-mount` keys first try their privately staged Chick/Fledgling/Bird portraits through `storybook/licensedRpgSprites.js`, gated by a matching licensed Chick overlay. A failed local portrait tries the runtime sprite for the same key before the base-species fallback; other species never inherit this art. `petSpriteKeys` uses the shared `companion/birdEvolution.js` stage resolver for the exact Chick/Base identity, with server-confirmed Fledgling and evolution state. `PetEvolutionGuide` includes Egg → Baby → Middle → Grown for every family across Hatching, owned previews and species details, with the exact Chick form names where applicable. It highlights only the server-confirmed lifecycle stage and grants no ownership or expedition eligibility. Smooth scaling (`image-rendering: auto`) is the default; pass `rendering="pixelated"` when an asset needs crisp pixel edges. The component has three render modes:

- **Static** (`frames === 1`): renders a lazy `<img>` fitted inside the requested size with `object-fit: contain`. Most sprites are static.
- **Animated** (`frames > 1`): renders `<span role="img" aria-label={alt}>` with a CSS `background-position` step animation. The shared `@keyframes sprite-cycle` rule is injected once by `SpriteCatalogProvider`; each instance sets `--sprite-end-x` as an inline custom property so any render size works without separate keyframe declarations.
- **Fallback** (unknown slug, catalog still loading or failed image): tries `fallbackSpriteKey`, then renders the `icon` emoji (or a sparkle when no icon is supplied). Static portraits and animated strips share this recovery path. Failures are bound to the failing URL; a fresh catalog URL is eligible to load without remounting the component.

Props: `spriteKey`, `fallbackSpriteKey` (optional base-species fallback), `icon` (emoji fallback), `size` (px, default `32`), `alt` (accessible label, falls back to `spriteKey`), `className`, `rendering` (`smooth` by default or `pixelated`), `potionSlug` (variant filter) and `dim` (happiness presentation).

A11y: static `<img>` gets `alt`; animated and fallback `<span>` elements get `role="img"` + `aria-label`. The fallback glyph and animated strip's load probe are hidden from assistive technology, so the entity name is announced once. Potion and happiness filters apply to every render mode. Animations respect `prefers-reduced-motion` via a freeze rule in `index.css` — no per-instance motion logic needed.

Do not call `fetchSpriteCatalog` or access `localStorage` directly in pages; go through `useSpriteCatalog().getSpriteUrl` / `.getSpriteMeta` for consistent cache behavior.

### CatalogIcon

`rpg/RewardItem` composes CatalogIcon and BadgeRarity for challenge item promises,
settled receipts and expedition loot. It accepts their existing flattened item
fields, retains the sprite/glyph fallback and omits rarity when an older receipt
did not record it. Supplied effect summaries and zero-valued duplicate conversion
receipts remain readable; presentation never grants an item or computes a payout.

`<CatalogIcon assetId={item.catalog_icon} spriteKey={item.sprite_key} icon={item.icon} size={40} alt={item.name} />`

Use the server-confirmed `catalog_icon` identity on item/challenge/catalog image
surfaces; flattened item responses use `item_catalog_icon`. The private shared
family resolves static PNG URLs beneath its pinned manifest directory. Images
use smooth interpolation and contain sizing at the requested CSS size. A missing
identity/install or failed PNG retains the existing `RpgSprite` fallback chain.
Use empty `alt` for a decorative image whose adjacent label already describes it.
Keep creature/gameplay presentation on its existing renderer and equipped frames
on their existing overlays. Never infer catalog image identity from a shared
legacy sprite key or a parent-authored challenge name.
