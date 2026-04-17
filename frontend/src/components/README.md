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
| Modal surface / popover / toast / lightbox | `z-50` | `BottomSheet`, `ConfirmDialog`, `DropToastStack`, `AvatarMenu` (dropdown), `NotificationBell` (dropdown), `ProofGallery` (lightbox) |

Everything that floats above page chrome lives at `z-50`. That means a toast emitted while a modal is open can be hidden behind it, and an open modal will block the notification dropdown until dismissed. If that proves wrong for a specific element (e.g. toasts should always be visible), promote it to a new `z-60` row and update this table in the same PR. Do not introduce ad-hoc z-values without updating this table.

### File layout

- Root `components/*.jsx` — domain-agnostic primitives (Button, Loader, EmptyState, BottomSheet, etc.)
- `components/journal/` — Hyrule-themed surface compositions (ParchmentCard, RuneBand, StreakFlame)
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
- `pages/achievements/SkillCard.jsx` — used only by `pages/achievements/SkillTreeView.jsx`
- `pages/rewards/RewardCard.jsx` — used only by `pages/rewards/RewardShop.jsx`
- `pages/rewards/CoinBalanceCard.jsx` — used only by `pages/rewards/Rewards.jsx`
- `pages/ingest/ProjectOverridesCard.jsx` — used only by `pages/ingest/ReviewStep.jsx`
- `pages/project/ProjectPlanItems.jsx` (`StepCard` export) — used only by `pages/project/PlanTab.jsx`

Promote to `components/cards/` only when a **second** page imports it. Until then, co-location wins: the card lives next to its only consumer, the parent file stays under ~400 lines, and the import line documents ownership.

Do not pre-emptively promote a card that has only one importer. The cost of moving is small; the cost of premature abstraction is real.

#### Per-area shared constants

When a page-area has constants used by both a parent and an extracted card (e.g. XP thresholds, type orderings), house them in a sibling `.constants.js` file rather than exporting from the parent component file. ESLint's `react-refresh/only-export-components` rule forbids non-component exports from a `.jsx` component file; using a separate `.constants.js` keeps both the lint rule happy and the constant in lockstep across consumers.

Example: [`pages/achievements/skillTree.constants.js`](../pages/achievements/skillTree.constants.js) holds `XP_THRESHOLDS` so both `SkillTreeView.jsx` and `SkillCard.jsx` can import it.

### Accessibility roles

Shared primitives carry consistent ARIA roles. Match these when building new ones:

| Primitive | Role | Why |
|---|---|---|
| `Loader` | `status` + `aria-busy="true"` | Non-urgent transient state |
| `EmptyState` | `status` | Non-urgent informational region |
| `ErrorAlert` | `alert` | Errors interrupt — assertive politeness |
| `ProgressBar` | `progressbar` + `aria-valuenow/min/max` | Widget with measurable state |
| `BottomSheet` | `dialog` + `aria-modal="true"` + `aria-labelledby` | Modal surface |
| `ConfirmDialog` | `alertdialog` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby` | Destructive-action modal |

Use React's `useId()` to generate per-instance IDs for `aria-labelledby` / `aria-describedby` so multiple stacked instances don't collide.

For icon-only interactive elements, an `aria-label` is mandatory — the upcoming `<IconButton>` primitive enforces this; raw `<button>` tags wrapping a single Lucide icon need it added by hand.

When a `ProgressBar` accepts an `aria-label`, prefer a context-rich one (e.g. `"${skill.name} XP progress"`) over the default `"Progress"` if the page renders multiple bars.

### Modal overlay tokens

The four `.modal-*` classes in `index.css` (`modal-ink-wash`, `modal-vignette`, `modal-seal-ring`, `modal-seal-ring-strong`) reference per-cover-overridable `--color-modal-*` tokens. `themes.js` may diverge these per cover — e.g. Vigil's dark surface needs a lighter wash. Three Hyrule defaults (`--color-modal-wash`, `--color-modal-vignette-edge`, `--color-modal-shadow`) happen to share `rgba(45,31,21,0.45)` but represent three distinct semantic roles; do not dedupe.
