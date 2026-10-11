# Components

Shared primitives and composition components for The Abby Project. See [CLAUDE.md](../../../CLAUDE.md#frontendsrc) at the repo root for the full architectural overview.

The web app, Memory Meadow and Unity Play share a soft storybook direction: bundled Nunito, cream pages, lavender and mint tints, rounded surfaces and controls, and clear icons. Shared navigation and currency symbols use Meadow drawings; utility controls use Lucide. `shared/storybook/presentation.json` supplies the baseline palette and companion presentation; `themes.js` adds readable semantic colors and six coordinated covers. Keep paid art in the private asset pipeline. Legacy component and CSS names remain compatibility APIs; they no longer require parchment, wax or leather effects.

React's `Abby Nunito` face uses the bundled variable TTF with real weights 200–1000, rather than stretching a single semibold face across body and heading styles. Heading weight defaults live in the base CSS layer so component weights can override them. The public source and OFL license remain in `shared/storybook/fonts`; `scripts/storybook/sync_presentation.py` maintains its runtime copy and Unity's fixed weight-600 font. The React font is included in the service-worker precache.

The licensed Meadow/welcome companion is a replaceable artwork preview. It does not represent an owned account species, an evolution unlock or earned progression. Use the server's species `sprite_key` for owned companions and preserve their potion and happiness presentation.

## Conventions

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
| `ConfirmDialog` | `alertdialog` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby` | Destructive-action modal |
| `TomeShelf` / `TomeSpine` | `tablist` + `tab` + `aria-selected` + `aria-orientation="horizontal"` | Keyboard-navigable category switcher; centers within its rail without scrolling the page or taking focus on mount |
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
| `mastery.constants.js` | `PROGRESS_TIER`, `TIER_BADGE_TONE`, `tierForProgress`, `RARITY_HALO`, `CHAPTER_NUMERALS`, `chapterMark`, `countIlluminated`, `RECENT_EARNED_DAYS`, `isRecentlyEarned`, `RARITY_KEYS`, `RARITY_ORDER` | Atlas vocabulary. `tierForProgress({ unlocked, progressPct, level, maxLevel })` resolves to one of `PROGRESS_TIER` (`locked` / `nascent` / `rising` / `cresting` / `gilded`) — the same five tiers drive `IlluminatedVersal` fill color, shared `TomeSpine` foot-bands, and `SkillVerse` progression states in Wayfinder. `RARITY_HALO[rarity]` is the canonical ring + glow for any earned thing |

**Tier is expressed through `PROGRESS_TIER`'s two channels — `bar` and `chip` — never as applied ornament.** A folio wears its tier as the versal's gilt fill, the progress bar, the stat values, and a `RuneBadge` on its kicker (`TIER_BADGE_TONE` maps the five rungs onto the badge's `ink` / `moss` / `teal` / `ember` / `gold` tones). This matches `QuestLogEntry`, which signals all four of its states purely as surface + border tint, and `SkillVerse`'s legacy folio variant, which tints the versal and level numeral. A tier-tinted band was tried on the folio verso and removed: it was the only element in the app encoding state as a decorative band, its `--color-headband-*` hexes were the only tier colors not resolving through cover tokens, and it restated a tier the card was already showing three other ways. `TomeSpine` keeps its headband — there the band depicts a physical object (the cloth cap on a binding), which is a different job from signalling state.

CSS contract (declared once in [`../index.css`](../index.css), reused by every cohort consumer):

- `.drawer-case` + `.drawer-face` / `.drawer-face-open` — the `vessel` variant's cabinet. **`codex` and `vessel` must not share their physical vocabulary.** They deliberately share outer dimensions (so a mixed shelf keeps its snap-rail layout), which means everything else has to carry the distinction: a tome rests **on** a `.shelf-board` and, when active, lifts, tilts open on its binding, and unfurls a bookmark ribbon; a drawer sits **in** a `.drawer-case`, is debossed into it while shut, and when active slides out toward the viewer with its pull gripped — no rotation, and **no ribbon**, since a drawer has no bookmark. Sharing the ribbon and the plank across variants was what made a row of drawers read as a row of books

- `.spine-leather` + `--color-leather-{locked,nascent,rising,cresting,gilded}` — the tome binding. Each tier mixes **its own accent token** into a dark leather base via `color-mix`, so a shelf reads as a row of dyed morocco and the tier ladder is legible across it, and so a journal-cover swap retunes the shelf. They were previously five near-identical tans inside a 1.9° hue band — one binding at five exposures — as fixed hexes `applyTheme` never touched, which also left the shelf pale tan on the dark Vigil cover
- `.spine-foil` — gilt-stamped spine title. Its gradient puts `--foil-tone-bottom` at the **50% stop**, i.e. the middle of every title, so that stop must stay light against dark leather; legibility is carried by the class's deboss `drop-shadow` (how real gilt stamping reads — pressed in, with a dark edge) rather than by tuning fill colors per tier. `locked` keeps dark foil because its cloth stays pale

- `.versal-gilt` — `background-clip: text` + linear gradient using `--versal-fill` custom property as the fill stop. The variable is set inline by `<IlluminatedVersal>` based on `progressPct`. Underlying letterform is drawn twice (a stroke in `ink-whisper` + the gilt overlay) so the un-illuminated portion stays visible
- `--color-gold-leaf`, `--color-rarity-{common,uncommon,rare,epic,legendary}` — cover-tuned color tokens. Don't write hex literals for these; reach for the token
- `@keyframes halo-rise` (`.animate-halo-rise`) — radial expansion glow on freshly-mastered tiers
- `@keyframes gilded-glint` (`.animate-gilded-glint`) — one-shot foil sheen for sigils earned within the last `RECENT_EARNED_DAYS` (default 7)
- All animations sit inside the `@media (prefers-reduced-motion: reduce)` block already in `index.css` — adding a new atlas primitive doesn't require a new reduced-motion rule

When applying atlas vocabulary to a new page, prefer composition over invention — wrap an existing card in a sigil, lead a section with a rubric, replace a plain title with a versal. Don't introduce a new rarity tier, halo color, or keyframe inside an apply phase; the cohort's value is its consistency.

### Quest folios

The five tabs under `<ChapterHub>` at `/quests` (Ventures · Duties · Study · Rituals · Movement) share one folio shell at [`pages/quests/QuestFolio.jsx`](../pages/quests/QuestFolio.jsx). It's modelled on the former Skills tome's `FolioSpread` — two-page parchment spread with a gutter shadow on desktop, single column on mobile — but parameterised so each tab fills in its own `letter` / `title` / `kicker` / `stats[]` / `progressPct` / `rarityCounts` without dragging the skill-tree XP math along.

Per-page tier concepts map onto the Atlas rarity vocabulary via [`pages/quests/quests.constants.js`](../pages/quests/quests.constants.js): `difficultyToRarity(1-5)` + `effortToRarity(1-5)` both fan 1→common…5→legendary, and `buildRarityCounts(items, mapper, isEarned)` reduces a list into the `{common: {earned, total}, …}` shape `RarityStrand` consumes. Project `payment_kind` (required / bounty) and Habit `strength` buckets stay as their own existing chip palettes — they're not forced into the rarity ladder. Ventures + Study render a strand on the verso; Duties + Rituals + Movement omit it because their domain doesn't have a rarity distribution.

Test attributes mirror the rest of the cohort: `data-folio-verso="true"`, `data-tier={locked|nascent|rising|cresting|gilded}`, `data-progress={pct}` on the verso aside; `data-folio-recto="true"` on the recto. Within the recto, working-list sections lead with `<ChapterRubric index name>` so the §I/§II/§III numeral progression reads as the chapter's table of contents.

### RpgSprite

`<RpgSprite spriteKey="slug" icon="🐉" size={32} alt="..." className="..." />`

Renders an RPG-domain icon from the runtime sprite catalog. Call sites provide a `spriteKey` (slug string) and an `icon` emoji fallback — slug resolution and URL lookup happen internally via `useSpriteCatalog()` from `SpriteCatalogProvider`. Smooth scaling (`image-rendering: auto`) is the default; pass `rendering="pixelated"` when an asset needs crisp pixel edges. The component has three render modes:

- **Static** (`frames === 1`): renders a lazy `<img>` fitted inside the requested size with `object-fit: contain`. Most sprites are static.
- **Animated** (`frames > 1`): renders `<span role="img" aria-label={alt}>` with a CSS `background-position` step animation. The shared `@keyframes sprite-cycle` rule is injected once by `SpriteCatalogProvider`; each instance sets `--sprite-end-x` as an inline custom property so any render size works without separate keyframe declarations.
- **Fallback** (unknown slug, catalog still loading or failed image): tries `fallbackSpriteKey`, then renders the `icon` emoji (or a sparkle when no icon is supplied). Static portraits and animated strips share this recovery path. Failures are bound to the failing URL; a fresh catalog URL is eligible to load without remounting the component.

Props: `spriteKey`, `fallbackSpriteKey` (optional base-species fallback), `icon` (emoji fallback), `size` (px, default `32`), `alt` (accessible label, falls back to `spriteKey`), `className`, `rendering` (`smooth` by default or `pixelated`), `potionSlug` (variant filter) and `dim` (happiness presentation).

A11y: static `<img>` gets `alt`; animated and fallback `<span>` elements get `role="img"` + `aria-label`. The fallback glyph and animated strip's load probe are hidden from assistive technology, so the entity name is announced once. Potion and happiness filters apply to every render mode. Animations respect `prefers-reduced-motion` via a freeze rule in `index.css` — no per-instance motion logic needed.

Do not call `fetchSpriteCatalog` or access `localStorage` directly in pages; go through `useSpriteCatalog().getSpriteUrl` / `.getSpriteMeta` for consistent cache behavior.
