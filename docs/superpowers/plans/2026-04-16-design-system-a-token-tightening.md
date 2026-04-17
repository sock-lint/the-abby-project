# Design System A: Token Tightening — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four remaining gaps in the token system — add a project font-size scale, tokenize the four modal-overlay rgba values, codemod the 23 hardcoded hex literals in component code, and document the (currently informal) z-index stack.

**Architecture:** All changes land in three places: [frontend/src/index.css](../../../frontend/src/index.css) (`@theme` block), the 25 files containing arbitrary `text-[Npx]` Tailwind values, and a new `frontend/src/components/README.md` for the z-stack convention. No new components or behavior — pure token consolidation.

**Tech Stack:** Tailwind 4 (CSS-first config via `@theme`), Vite 8, Vitest 4 (theme-contrast gate already enforces WCAG AA on every cover).

---

## File Structure

### Modified
- `frontend/src/index.css` — add 5 `--text-*` tokens; tokenize 4 modal rgba values
- `frontend/src/components/README.md` — **new** doc; z-index stack + token authoring conventions
- ~25 component/page files — replace `text-[Npx]` with `text-micro` / `text-tiny` / `text-caption` / `text-body` / `text-lede`
- ~10 component/page files — replace hardcoded hex with token classes (`text-rarity-*`, `bg-ink-page-aged`, etc.)

### Untouched
- `frontend/src/themes.js` — already canonical for the 6 covers
- `frontend/src/constants/colors.js` and `styles.js` — already token-driven; no change needed

---

## Task 1: Add font-size scale to `@theme`

**Files:**
- Modify: `frontend/src/index.css:4-57` (the `@theme` block)

The Tailwind 4 `@theme` block exposes any `--text-*` token as a `text-<name>` utility class automatically. Pick names that match the existing journal vocabulary (micro / tiny / caption / body / lede) so call sites read like editorial copy, not pixel values.

- [ ] **Step 1: Add the type-scale block**

Open [frontend/src/index.css](../../../frontend/src/index.css). Inside the `@theme { }` block, after the `/* Fonts */` group (around line 12) and before `/* Parchment core */` (around line 14), insert:

```css
  /* Type scale — paired with line-height so utilities double as leading.
     Values are calibrated against the cohort of arbitrary text-[Npx] uses
     audited 2026-04-16. text-base remains the Tailwind default (16px). */
  --text-micro: 10px;
  --text-micro--line-height: 14px;
  --text-tiny: 11px;
  --text-tiny--line-height: 15px;
  --text-caption: 12px;
  --text-caption--line-height: 16px;
  --text-body: 14px;
  --text-body--line-height: 20px;
  --text-lede: 18px;
  --text-lede--line-height: 26px;
```

- [ ] **Step 2: Verify the utilities resolve**

Run: `cd frontend && npm run build`
Expected: build succeeds. (Tailwind 4 generates `.text-micro`, `.text-tiny`, etc. on demand once a class is referenced — the build is the verification that the syntax parses.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "Add type-scale tokens (micro/tiny/caption/body/lede)"
```

---

## Task 2: Codemod arbitrary `text-[Npx]` values

**Files:**
- Modify: 25 files identified by `Grep "text-\[\d+px\]"` on 2026-04-16:
  - `frontend/src/pages/Stable.jsx` (8 sites)
  - `frontend/src/pages/manage/CodexSection.jsx` (6)
  - `frontend/src/pages/SettingsPage.jsx` (4)
  - `frontend/src/pages/ChildDashboard.jsx` (3)
  - `frontend/src/pages/Inventory.jsx` (2)
  - `frontend/src/pages/rewards/CoinExchangeModal.jsx`, `RewardShop.jsx`, `RedemptionHistory.jsx`, `ExchangeHistory.jsx`
  - `frontend/src/pages/Character.jsx`
  - `frontend/src/pages/Projects.jsx`
  - `frontend/src/pages/achievements/BadgeCollection.jsx`
  - `frontend/src/pages/project/ProjectPlanItems.jsx`, `PlanTab.jsx`
  - `frontend/src/components/dashboard/VitalPipStrip.jsx`
  - `frontend/src/components/layout/HeaderProgressBand.jsx`, `HeaderStatusPips.jsx`, `ChapterNav.jsx`
  - `frontend/src/components/AvatarMenu.jsx`
  - `frontend/src/components/DropToastStack.jsx`
  - `frontend/src/components/NotificationBell.jsx`
  - `frontend/src/components/journal/RuneBand.jsx`, `RuneBadge.jsx`, `PartyCard.jsx`

**Mapping table (apply to every site):**

| Old | New |
|---|---|
| `text-[10px]` | `text-micro` |
| `text-[11px]` | `text-tiny` |
| `text-[12px]` | `text-caption` |
| `text-[14px]` | `text-body` |
| `text-[18px]` | `text-lede` |

For any other size found (e.g. `text-[9px]` or `text-[15px]`), do **not** invent a new token — round to the nearest scale value and let it ride. If a file resists rounding (e.g. it's mimicking a fixed-pixel system like a numeric badge), leave the arbitrary value in and add a one-line `// retained: pixel-perfect badge` comment.

- [ ] **Step 1: Migrate `frontend/src/pages/Stable.jsx`**

Open the file. Use Edit with `replace_all: true` for each row in the mapping table that appears. Then visually scan for any unmapped sizes — keep them with a comment per the rule above.

- [ ] **Step 2: Repeat for the remaining 24 files**

Same procedure. Process them in alphabetical order so progress is trackable. After each file, run:

```bash
cd frontend && npx eslint src/<the-file> --max-warnings 0
```

- [ ] **Step 3: Run the full lint + test suite**

```bash
cd frontend && npm run lint && npm run test:run
```

Expected: clean lint; all tests pass. (Theme-contrast gate exercises the `--text-*` tokens indirectly via render.)

- [ ] **Step 4: Boot the dev server and eyeball**

```bash
cd frontend && npm run dev
```

Use [preview tools](../../README.md) to visit `/stable`, `/inventory`, `/character`, `/dashboard`, `/manage`. Confirm no visible regression in row densities. Take a screenshot of `/stable` for the PR.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "Codemod arbitrary text-[Npx] to type-scale tokens"
```

---

## Task 3: Tokenize modal-overlay rgba values

**Files:**
- Modify: `frontend/src/index.css:186-216` (the four `.modal-*` rules)

The four overlay rules currently hardcode `rgba(45,31,21,...)` (which is `#2d1f15` = `--color-ink-primary` at varying alpha) and `rgba(77,208,225,...)` (a teal that doesn't quite match `--color-sheikah-teal` `#1d8a80`). On the dark Vigil cover these read wrong because the ink-wash never lightens. Move them to per-cover tokens so [themes.js](../../../frontend/src/themes.js) can override them.

- [ ] **Step 1: Add token slots in `@theme`**

In the `@theme { }` block of [frontend/src/index.css](../../../frontend/src/index.css), add a new group after the rarity tiers (around line 44):

```css
  /* Modal chrome (Hyrule defaults — themes.js overrides per cover) */
  --color-modal-wash: rgba(45, 31, 21, 0.45);
  --color-modal-vignette-mid: rgba(45, 31, 21, 0.25);
  --color-modal-vignette-edge: rgba(45, 31, 21, 0.45);
  --color-modal-seal-glow: rgba(77, 208, 225, 0.18);
  --color-modal-seal-edge: rgba(77, 208, 225, 0.28);
  --color-modal-seal-glow-strong: rgba(77, 208, 225, 0.22);
  --color-modal-seal-edge-strong: rgba(217, 117, 72, 0.40);
  --color-modal-shadow: rgba(45, 31, 21, 0.45);
  --color-modal-shadow-strong: rgba(45, 31, 21, 0.55);
  --color-modal-highlight: rgba(255, 248, 224, 0.4);
```

- [ ] **Step 2: Replace literals in the four `.modal-*` rules**

Edit `frontend/src/index.css` lines 186-216 to reference the new tokens:

```css
.modal-ink-wash {
  background-color: var(--color-modal-wash);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}

.modal-vignette {
  background: radial-gradient(
    ellipse at center,
    transparent 25%,
    var(--color-modal-vignette-mid) 70%,
    var(--color-modal-vignette-edge) 100%
  );
  pointer-events: none;
}

.modal-seal-ring {
  box-shadow:
    0 0 0 1px var(--color-modal-seal-edge),
    0 0 40px var(--color-modal-seal-glow),
    0 24px 60px var(--color-modal-shadow),
    0 2px 0 var(--color-modal-highlight) inset;
}

.modal-seal-ring-strong {
  box-shadow:
    0 0 0 1px var(--color-modal-seal-edge-strong),
    0 0 44px var(--color-modal-seal-glow-strong),
    0 28px 70px var(--color-modal-shadow-strong),
    0 2px 0 var(--color-modal-highlight) inset;
}
```

- [ ] **Step 3: Verify modals still render**

```bash
cd frontend && npm run dev
```

Visit `/manage`, click "New Reward". Visit `/chores`, click any "+ Add chore" affordance. Confirm the wax-seal ring + ink wash look identical to before. Repeat after switching cover (Settings → cover picker → Vigil) and confirm Vigil's modal still has the warm halo (no override yet — should be unchanged since we kept the same default values).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "Tokenize modal overlay rgba values"
```

> **Future work (out of scope for this plan):** themes.js can now override `--color-modal-*` per cover. Vigil could lift `--color-modal-wash` toward a slate hue instead of leaning on a darker ink. Track in a follow-up.

---

## Task 4: Replace hardcoded hex literals in component code

**Files:**
- Modify (~10 files identified by `Grep "#[0-9a-fA-F]{6}"` excluding themes.js / index.css / constants/colors.js / test files):
  - `frontend/src/pages/manage/CodexSection.jsx` — 6 sites (rarity ternary fallbacks)
  - `frontend/src/pages/SettingsPage.jsx` — 4 sites (theme-swatch previews — **leave as-is**, they're preview UI)
  - `frontend/src/components/ConfirmDialog.jsx` — 2
  - `frontend/src/components/modal/SealCloseButton.jsx` — 2
  - `frontend/src/pages/achievements/CategoryFormModal.jsx` — 2
  - `frontend/src/pages/Login.jsx` — 1
  - any others surfaced by the audit

For rarity-tinted fallbacks, the right replacement is a class lookup from [`RARITY_COLORS`](../../../frontend/src/constants/colors.js) / `RARITY_TEXT_COLORS` / `RARITY_PILL_COLORS` rather than a CSS variable.

- [ ] **Step 1: Inspect each violation site and choose the replacement**

Run:

```bash
cd frontend
# Pattern catches both 6-char (#abcdef) and 3-char shorthand (#abc) hex.
grep -rEn "#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b" src/ --include="*.jsx" --include="*.js" \
  | grep -v "src/themes.js" \
  | grep -v "src/index.css" \
  | grep -v "src/constants/colors.js" \
  | grep -v ".test." \
  | grep -v "// intentional\|// preview-only\|// retained:"
```

For each match, decide the replacement using this priority order:

1. **If the hex matches a defined token** (cross-check against `frontend/src/index.css`'s `@theme` block): replace with `var(--color-X)` if used in `style={{}}` or with a Tailwind class if used in `className`.
2. **If the hex is a rarity tint:** replace with the appropriate constant from [constants/colors.js](../../../frontend/src/constants/colors.js).
3. **If the hex is a one-off** (not in any token): leave it alone. Add `// preview-only — intentional literal` if it's a swatch in SettingsPage-style code.

- [ ] **Step 2: Apply the replacements file by file**

For each file, use Edit. Example pattern for a `CodexSection.jsx` rarity fallback:

```jsx
// Before
const color = item.rarity === 'legendary' ? '#856418' : '#456a3a';

// After
import { RARITY_TEXT_COLORS } from '../../constants/colors';
// ... in component
<span className={RARITY_TEXT_COLORS[item.rarity] || RARITY_TEXT_COLORS.common}>
```

- [ ] **Step 3: Run lint + tests + build**

```bash
cd frontend && npm run lint && npm run test:run && npm run build
```

Expected: all clean. The theme-contrast gate must still pass.

- [ ] **Step 4: Visual spot-check**

```bash
cd frontend && npm run dev
```

Visit the affected pages: `/manage` (Codex tab), confirmation dialogs (delete a draft project to trigger ConfirmDialog), `/login`. Confirm rarity colors and modal close-button tinting unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "Replace hardcoded hex literals with token classes"
```

---

## Task 5: Document the z-index stack

**Files:**
- Create: `frontend/src/components/README.md`

Currently `BottomSheet.jsx:34` uses `z-40` for backdrop, `z-50` for the sheet, and `JournalShell` uses `z-30` for the sticky header. There are no other z-index uses, but the convention is undocumented. Write it down before drift starts.

- [ ] **Step 1: Create the README**

Create `frontend/src/components/README.md` with:

```markdown
# Components

Shared primitives and composition components for the Hyrule Field Notes UI. See [CLAUDE.md](../../../CLAUDE.md#frontendsrc) at the repo root for the full architectural overview.

## Conventions

### Token-first styling

- Color, font, and (after 2026-04-16) font-size values come from CSS custom properties declared in [`../index.css`](../index.css)'s `@theme` block.
- Per-cover overrides live in [`../themes.js`](../themes.js).
- Component-level class strings live in [`../constants/styles.js`](../constants/styles.js); status/rarity color maps live in [`../constants/colors.js`](../constants/colors.js).
- Avoid arbitrary Tailwind values (`text-[10px]`, `bg-[#abc123]`). If a value doesn't fit the existing scale, add a token to `@theme` rather than inlining.

### Z-index stack

The app uses three explicit layers. Avoid introducing new z values without updating this table.

| Layer | Token / Class | Used by |
|---|---|---|
| Sticky shell | `z-30` | `JournalShell` header (sticky), `HeaderProgressBand` |
| Modal backdrop | `z-40` | `ModalBackdrop`, `BottomSheet` overlay |
| Modal surface | `z-50` | `BottomSheet` card / sheet, `ConfirmDialog` |

If a new layer is needed (e.g. a toast stack above modals), pick `z-60` and add a row to this table in the same PR.

### File layout

- Root `components/*.jsx` — domain-agnostic primitives (Button, Loader, EmptyState, BottomSheet, etc.)
- `components/journal/` — Hyrule-themed surface compositions (ParchmentCard, RuneBand, StreakFlame)
- `components/layout/` — page chrome (JournalShell, ChapterNav, QuickActionsFab)
- `components/modal/` — modal building blocks (ModalBackdrop, SealCloseButton, SealPulseRing)
- `components/dashboard/` — Today-page composites (HeroPrimaryCard, ApprovalQueueList)
- `components/cards/` — promoted page-card components (added when a `*Card` from `pages/` is reused twice)
- `components/icons/` — custom SVG icon set (lucide-react covers the rest)

A component lives in `pages/` until it's reused twice; promote to `components/` (or a sub-folder) on the second use.
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/README.md
git commit -m "Document component conventions and z-index stack"
```

---

## Verification

Run the full frontend gate:

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected:
- Lint: 0 warnings, 0 errors
- Tests: all green; coverage ≥ existing thresholds (65/55/55/65)
- Build: succeeds; `dist/` produced

Then boot dev and visually check every page audited as a top offender:

```bash
cd frontend && npm run dev
```

Visit (preview tools): `/`, `/dashboard`, `/projects`, `/stable`, `/inventory`, `/character`, `/manage`, `/manage` → Codex tab, `/settings`. Switch covers (Settings → all 6 covers) and confirm:
- Type sizes look right (no oversized or tiny rows)
- Modals render correctly on every cover (open one from `/manage`)
- Rarity badges still show the right tint

Snapshot one screenshot per cover from `/dashboard` for the PR.
