# Components

Shared primitives and composition components for the Hyrule Field Notes UI. See [CLAUDE.md](../../../CLAUDE.md#frontendsrc) at the repo root for the full architectural overview.

## Conventions

### Token-first styling

- Color, font, and font-size values come from CSS custom properties declared in [`../index.css`](../index.css)'s `@theme` block.
- Per-cover overrides live in [`../themes.js`](../themes.js).
- Component-level class strings live in [`../constants/styles.js`](../constants/styles.js); status/rarity color maps live in [`../constants/colors.js`](../constants/colors.js).
- Avoid arbitrary Tailwind values (`text-[10px]`, `bg-[#abc123]`). The project type scale lives in `@theme` as `--text-micro` (10px), `--text-tiny` (11px), `--text-caption` (12px), `--text-body` (14px), `--text-lede` (18px). If a value doesn't fit the existing scale, add a token to `@theme` rather than inlining.
- Hex literals in component code should be migrated to token references. The exceptions documented in the codebase are: HTML5 `<input type="color">` defaults (user data), official brand-color SVGs (e.g. Google sign-in logo), and theme-invariant decorative palettes (e.g. wax-seal gradient stops in `ConfirmDialog`/`SealCloseButton`). Each retention carries an inline `// intentional:` comment explaining why.

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
- `components/journal/` — Hyrule-themed surface compositions (ParchmentCard, RuneBand, StreakFlame)
- `components/atlas/` — illuminated-manuscript primitives (IlluminatedVersal, BadgeSigil, IncipitBand, ChapterRubric, RarityStrand, mastery.constants). See [Atlas cohort](#atlas-cohort) below
- `components/layout/` — page chrome (JournalShell, ChapterNav, QuickActionsFab)
- `components/modal/` — modal building blocks (ModalBackdrop, SealCloseButton, SealPulseRing)
- `components/dashboard/` — Today-page composites (HeroPrimaryCard, ApprovalQueueList)
- `components/cards/` — promoted page-card components (added when a `*Card` from `pages/` is reused twice)
- `components/icons/` — custom SVG icon set (lucide-react covers the rest)

A component lives in `pages/` until it's reused twice; promote to `components/` (or a sub-folder) on the second use.

#### Card placement rule

Page-specific `*Card` components start as sibling files inside their owning page directory:

- `pages/Homework/AssignmentCard.jsx` — used only by `pages/Homework/index.jsx`
- `pages/manage/CatalogCard.jsx` — used only by `pages/manage/CodexSection.jsx`
- `pages/achievements/TomeSpine.jsx` + `TomeShelf.jsx` + `FolioSpread.jsx` + `SkillVerse.jsx` + `ChapterRubric` (now in `components/atlas/`) + `PrereqChain.jsx` + `SkillDetailSheet.jsx` — Skills-only domain code at `pages/achievements/SkillTreeView.jsx`. The "tome shelf opening onto an illuminated folio" metaphor replaced the older pennant-ribbon + stanza-grid in the 2026-04-23 Skills redesign. The five primitives that backed both Skills and Badges (`IlluminatedVersal`, `BadgeSigil`, `IncipitBand`, `ChapterRubric`, `RarityStrand`) and `mastery.constants` were lifted to `components/atlas/` once a third surface (Lorebook) started importing them — see [Atlas cohort](#atlas-cohort)
- `pages/achievements/SigilCodex.jsx` + `CollectionFolio.jsx` + `BadgeDetailSheet.jsx` — used only by `pages/Badges.jsx`. The "Reliquary Codex" structure (seven criterion-family chapters, each a parchment folio with rubric numeral + illuminated drop-cap + rarity strand) replaced the flat `BadgeSigilGrid` in the 2026-04-22 Sigil Case redesign. Kept under `achievements/` because `ManagePanel.jsx` is the single cross-cutting admin surface for badges, and `collections.constants.js` (the Reliquary chapter taxonomy + `unlockHint`) is badge-domain data that doesn't belong at the shared layer
- `pages/character/SigilFrontispiece.jsx` + `TrophySlot.jsx` + `TrophyBadgePicker.jsx` + `CosmeticChapter.jsx` + `CosmeticSigil.jsx` + `StreakGlyph.jsx` — used only by `pages/Character.jsx`. The 2026-04-22 Frontispiece redesign turns the `/sigil` page into a personal author-portrait plate: illuminated initial + trophy seal hero, four `CollectionFolio`-style cosmetic chapters with locked intaglios for un-owned items, and a live hover preview on journal-cover cosmetics. `TrophyBadgePicker` imports `groupBadgesByCollection` from `pages/achievements/collections.constants.js` — the only cross-page reuse, and it's intentional so the picker speaks the Reliquary Codex's chapter taxonomy
- `pages/bestiary/celebration/usePhasedSequence.js` + `SparkleBurst.jsx` + `PotionAura.jsx` — used only by `pages/bestiary/PetCeremonyModal.jsx`. The phased-sequence hook + sparkle/aura primitives back the hatch / evolve / breed lifecycle animations (see CLAUDE.md → "Pet lifecycle animations"). Promote to `components/celebration/` if a second surface (e.g. quest-complete modal) reuses them
- `pages/rewards/RewardCard.jsx` — used only by `pages/rewards/RewardShop.jsx`
- `pages/rewards/CoinBalanceCard.jsx` — used only by `pages/rewards/Rewards.jsx`
- `pages/ingest/ProjectOverridesCard.jsx` — used only by `pages/ingest/ReviewStep.jsx`
- `pages/project/ProjectPlanItems.jsx` (`StepCard` export) — used only by `pages/project/PlanTab.jsx`

Promote to `components/cards/` only when a **second** page imports it. Until then, co-location wins: the card lives next to its only consumer, the parent file stays under ~400 lines, and the import line documents ownership.

Do not pre-emptively promote a card that has only one importer. The cost of moving is small; the cost of premature abstraction is real.

#### Per-area shared constants

When a page-area has constants used by both a parent and an extracted card (e.g. XP thresholds, type orderings), house them in a sibling `.constants.js` file rather than exporting from the parent component file. ESLint's `react-refresh/only-export-components` rule forbids non-component exports from a `.jsx` component file; using a separate `.constants.js` keeps both the lint rule happy and the constant in lockstep across consumers.

Examples: [`pages/achievements/skillTree.constants.js`](../pages/achievements/skillTree.constants.js) holds `XP_THRESHOLDS` (the level curve, shared by `SkillTreeView.jsx`, `SkillVerse.jsx`, `SkillDetailSheet.jsx`, `FolioSpread.jsx`, and `TomeSpine.jsx`); [`components/atlas/mastery.constants.js`](./atlas/mastery.constants.js) holds the Illuminated Atlas shared vocabulary — see [Atlas cohort](#atlas-cohort) for the full export list; [`pages/achievements/collections.constants.js`](../pages/achievements/collections.constants.js) holds the Reliquary Codex taxonomy — `COLLECTIONS` (seven chapters keyed by criterion family), `collectionForCriterion` / `collectionForBadge`, `groupBadgesByCollection`, `rarityCounts`, `unlockHint` (plain-English template for every known `criterion_type` — passed to `<BadgeSigil hint={...}>` by `CollectionFolio`), and `ladderSiblings` (tier progressions for the detail sheet); [`pages/character/character.constants.js`](../pages/character/character.constants.js) holds the Frontispiece taxonomy — `COSMETIC_CHAPTERS` (four cosmetic slots keyed to rubric numerals + drop-cap letters), `STREAK_TIERS` + `streakTier(days)` (flame-size ladder aligned with backend streak milestones), `mergeSlotCosmetics` (dedupe + sort owned against catalog), `slotRarityCounts`, and `cosmeticLockHint`. The Reliquary chapter taxonomy and the cosmetic chapter taxonomy are deliberately page-scoped — only the rarity / progress / chapter-numeral vocabulary is shared.

### Accessibility roles

Shared primitives carry consistent ARIA roles. Match these when building new ones:

| Primitive | Role | Why |
|---|---|---|
| `Loader` | `status` + `aria-busy="true"` | Non-urgent transient state |
| `EmptyState` | `status` | Non-urgent informational region |
| `ErrorAlert` | `alert` | Errors interrupt — assertive politeness |
| `ProgressBar` / `QuillProgress` | `progressbar` + `aria-valuenow/min/max` | Widget with measurable state |
| `BottomSheet` | `dialog` + `aria-modal="true"` + `aria-labelledby` | Modal surface |
| `ConfirmDialog` | `alertdialog` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby` | Destructive-action modal |
| `TomeShelf` / `TomeSpine` | `tablist` + `tab` + `aria-selected` + `aria-orientation="horizontal"` | Keyboard-navigable category switcher |

Use React's `useId()` to generate per-instance IDs for `aria-labelledby` / `aria-describedby` so multiple stacked instances don't collide.

For icon-only interactive elements, an `aria-label` is mandatory — the upcoming `<IconButton>` primitive enforces this; raw `<button>` tags wrapping a single Lucide icon need it added by hand.

When a `ProgressBar` or `QuillProgress` accepts an `aria-label`, prefer a context-rich one (e.g. `"${skill.name} XP progress toward level ${n+1}"`) over the default if the page renders multiple bars.

`QuillProgress` is a variant of `ProgressBar` with a hand-drawn quill-stroke SVG overlay — use it for mastery/progression contexts (skill XP, category chapters), keep `ProgressBar` for neutral progress (savings goals, assignments complete). Both share the same ARIA contract and `color` prop so they're substitutable when the aesthetic needs to change.

### Page shell + section header

Two primitives keep page-level vocabulary consistent across the journal:

- **`<PageShell width="wide|narrow" rhythm="loose|default|tight" animate variants>`** ([`./layout/PageShell.jsx`](./layout/PageShell.jsx)) — root wrapper for page bodies. Replaces the copy-pasted `<motion.div className="max-w-6xl mx-auto space-y-5">` pattern. Owns the spine width (`max-w-6xl` / `max-w-3xl`), vertical rhythm (`space-y-6` / `space-y-5` / `space-y-3`), and the fade-in animation. Outer horizontal padding stays with `JournalShell` — `PageShell` does NOT add px, so it can't double-pad. Callers that supply `variants` (e.g. the dashboards using `inkBleed`) take over the motion config; otherwise the default `opacity/y` fade applies. Set `animate={false}` for error fallback returns or pages that animate their own body.
- **`<SectionHeader title index kicker count actions as="h2">`** ([`./SectionHeader.jsx`](./SectionHeader.jsx)) — non-collapsible sibling of `<AccordionSection>` for sections that should always be open. Mirrors `AccordionSection`'s vocabulary (script kicker, atlas chapter numeral via `index`, `RuneBadge` count, supporting body line) so the two read as a family. Use the `actions` slot for right-aligned buttons or filter controls.

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

Use these primitives whenever a surface is meant to feel like an authored chapter rather than a form. Current consumers: the Skills tome shelf, the Reliquary Codex, the Sigil Frontispiece, the Lorebook folio, Bestiary (pet/mount/Codex rarity halos + Hatchery section rubrics), Project detail (status-driven versal + milestone numerals), Yearbook chapter cards (current-year IncipitBand, past-year small versal), and the dashboard hero (versal on clocked / next-action / quest-progress variants + AccordionSection chapter numerals).

| File | Export | Use |
|---|---|---|
| `IlluminatedVersal.jsx` | `<IlluminatedVersal letter size progressPct level maxLevel rarity />` | Drop-cap with gilt fill tied to progress. `size`: `sm` / `md` / `lg` / `xl`. `xl` is hero-incipit territory; `md` is row-leading; `sm` is detail-sheet header. Mastered tiers (cresting / gilded) wear a `RARITY_HALO` ring keyed off `rarity`. `aria-hidden` — caller carries the semantic text in adjacent body |
| `BadgeSigil.jsx` | `<BadgeSigil badge earned earnedAt hint onSelect />` | Wax-seal medallion for any criterion-earned achievement. Earned sigils carry `RARITY_HALO`, foil sheen, and an `xp_bonus` ledge. Unearned sigils render as debossed intaglios; pass `hint` (string) for the script unlock copy underneath. `hint` is caller-supplied so the primitive stays domain-agnostic — Reliquary Codex passes `unlockHint(badge)` from `pages/achievements/collections.constants.js`; other surfaces can pass a different string or omit it |
| `IncipitBand.jsx` | `<IncipitBand letter title kicker progressPct counts />` | Chapter opening band. Versal + display-serif title + script kicker; `counts` (the rarity strand counts shape) renders inline below the title |
| `ChapterRubric.jsx` | `<ChapterRubric index title meta />` | Compact rubric numeral (§I, §II, …) drop-cap + section title. Use for nested folio sections within a page |
| `RarityStrand.jsx` | `<RarityStrand counts compact className />` | Slim 5-segment band, one segment per rarity tier sized by total, fill within each segment by `earned/total`. `role="img"` with a descriptive `aria-label` enumerating each segment |
| `mastery.constants.js` | `PROGRESS_TIER`, `tierForProgress`, `RARITY_HALO`, `CHAPTER_NUMERALS`, `chapterMark`, `countIlluminated`, `RECENT_EARNED_DAYS`, `isRecentlyEarned`, `RARITY_KEYS`, `RARITY_ORDER` | Atlas vocabulary. `tierForProgress({ unlocked, progressPct, level, maxLevel })` resolves to one of `PROGRESS_TIER` (`locked` / `nascent` / `rising` / `cresting` / `gilded`) — the same five tiers drive `IlluminatedVersal` fill color, `TomeSpine` foot-bands, and `SkillVerse` level straps. `RARITY_HALO[rarity]` is the canonical ring + glow for any earned thing |

CSS contract (declared once in [`../index.css`](../index.css), reused by every cohort consumer):

- `.versal-gilt` — `background-clip: text` + linear gradient using `--versal-fill` custom property as the fill stop. The variable is set inline by `<IlluminatedVersal>` based on `progressPct`. Underlying letterform is drawn twice (a stroke in `ink-whisper` + the gilt overlay) so the un-illuminated portion stays visible
- `--color-gold-leaf`, `--color-rarity-{common,uncommon,rare,epic,legendary}` — cover-tuned color tokens. Don't write hex literals for these; reach for the token
- `@keyframes halo-rise` (`.animate-halo-rise`) — radial expansion glow on freshly-mastered tiers
- `@keyframes gilded-glint` (`.animate-gilded-glint`) — one-shot foil sheen for sigils earned within the last `RECENT_EARNED_DAYS` (default 7)
- All animations sit inside the `@media (prefers-reduced-motion: reduce)` block already in `index.css` — adding a new atlas primitive doesn't require a new reduced-motion rule

When applying atlas vocabulary to a new page, prefer composition over invention — wrap an existing card in a sigil, lead a section with a rubric, replace a plain title with a versal. Don't introduce a new rarity tier, halo color, or keyframe inside an apply phase; the cohort's value is its consistency.

### Quest folios

The five tabs under `<ChapterHub>` at `/quests` (Ventures · Duties · Study · Rituals · Movement) share one folio shell at [`pages/quests/QuestFolio.jsx`](../pages/quests/QuestFolio.jsx). It's modelled on the Skills tome's `FolioSpread` — two-page parchment spread with a gutter shadow on desktop, single column on mobile — but parameterised so each tab fills in its own `letter` / `title` / `kicker` / `stats[]` / `progressPct` / `rarityCounts` without dragging the skill-tree XP math along.

Per-page tier concepts map onto the Atlas rarity vocabulary via [`pages/quests/quests.constants.js`](../pages/quests/quests.constants.js): `difficultyToRarity(1-5)` + `effortToRarity(1-5)` both fan 1→common…5→legendary, and `buildRarityCounts(items, mapper, isEarned)` reduces a list into the `{common: {earned, total}, …}` shape `RarityStrand` consumes. Project `payment_kind` (required / bounty) and Habit `strength` buckets stay as their own existing chip palettes — they're not forced into the rarity ladder. Ventures + Study render a strand on the verso; Duties + Rituals + Movement omit it because their domain doesn't have a rarity distribution.

Test attributes mirror the rest of the cohort: `data-folio-verso="true"`, `data-tier={locked|nascent|rising|cresting|gilded}`, `data-progress={pct}` on the verso aside; `data-folio-recto="true"` on the recto. Within the recto, working-list sections lead with `<ChapterRubric index name>` so the §I/§II/§III numeral progression reads as the chapter's table of contents.

### RpgSprite

`<RpgSprite spriteKey="slug" icon="🐉" size={32} alt="..." className="..." />`

Renders an RPG-domain icon from the runtime sprite catalog. Call sites provide a `spriteKey` (slug string) and an `icon` emoji fallback — slug resolution and URL lookup happen internally via `useSpriteCatalog()` from `SpriteCatalogProvider`. The component has three render modes:

- **Static** (`frames === 1`): renders `<img src={url} style="image-rendering: pixelated">`. Most sprites are static.
- **Animated** (`frames > 1`): renders `<span role="img" aria-label={alt}>` with a CSS `background-position` step animation. The shared `@keyframes sprite-cycle` rule is injected once by `SpriteCatalogProvider`; each instance sets `--sprite-end-x` as an inline custom property so any render size works without separate keyframe declarations.
- **Fallback** (unknown slug or catalog still loading): renders the `icon` emoji. The emoji contract means call sites never show an empty gap.

Props: `spriteKey` (required), `icon` (required emoji fallback), `size` (px, default `32`), `alt` (accessible label, falls back to `spriteKey`), `className`.

A11y: static `<img>` gets `alt`; the animated `<span>` gets `role="img"` + `aria-label`. The fallback emoji is wrapped in `aria-hidden` with a visually-hidden `<span>` carrying the label so screen readers announce the name, not the glyph. Animations respect `prefers-reduced-motion` via a one-line freeze rule in `index.css` — no per-instance logic needed.

Do not call `fetchSpriteCatalog` or access `localStorage` directly in pages; go through `useSpriteCatalog().getSpriteUrl` / `.getSpriteMeta` for consistent cache behavior.
