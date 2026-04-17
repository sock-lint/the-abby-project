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
| Modal surface / toast | `z-50` | `BottomSheet` card / sheet, `ConfirmDialog`, `DropToastStack` |

`DropToastStack` shares `z-50` with modal surfaces — a toast emitted while a modal is open can be hidden behind it. If that proves wrong (toasts should always be visible), promote toasts to a new `z-60` row and update this table in the same PR. Do not introduce ad-hoc z-values without updating this table.

### File layout

- Root `components/*.jsx` — domain-agnostic primitives (Button, Loader, EmptyState, BottomSheet, etc.)
- `components/journal/` — Hyrule-themed surface compositions (ParchmentCard, RuneBand, StreakFlame)
- `components/layout/` — page chrome (JournalShell, ChapterNav, QuickActionsFab)
- `components/modal/` — modal building blocks (ModalBackdrop, SealCloseButton, SealPulseRing)
- `components/dashboard/` — Today-page composites (HeroPrimaryCard, ApprovalQueueList)
- `components/cards/` — promoted page-card components (added when a `*Card` from `pages/` is reused twice)
- `components/icons/` — custom SVG icon set (lucide-react covers the rest)

A component lives in `pages/` until it's reused twice; promote to `components/` (or a sub-folder) on the second use.

### Modal overlay tokens

The four `.modal-*` classes in `index.css` (`modal-ink-wash`, `modal-vignette`, `modal-seal-ring`, `modal-seal-ring-strong`) reference per-cover-overridable `--color-modal-*` tokens. `themes.js` may diverge these per cover — e.g. Vigil's dark surface needs a lighter wash. Three Hyrule defaults (`--color-modal-wash`, `--color-modal-vignette-edge`, `--color-modal-shadow`) happen to share `rgba(45,31,21,0.45)` but represent three distinct semantic roles; do not dedupe.
