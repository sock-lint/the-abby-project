# Design System D: Button Primitive + Icon-Button A11y + Card Alias Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 125 `className={buttonPrimary | buttonSecondary | buttonDanger | buttonGhost | buttonSuccess}` call sites across 37 files with a single `<Button>` primitive that exposes the variant via prop, plus an `<IconButton>` variant that requires `aria-label`. Sweep up the 19 unlabeled icon-only buttons in the same pass, then delete the `Card.jsx` alias once nothing in the migrated code refers to it.

**Architecture:** Two new components in `frontend/src/components/`. `<Button>` is a thin functional component that maps `variant` + `size` to existing class strings from [`constants/styles.js`](../../../frontend/src/constants/styles.js); `<IconButton>` shares the styling but enforces `aria-label` at the type level (and at runtime via a dev-only assertion). Migration is one-file-per-commit. The legacy `Card.jsx` alias is deleted after a final sweep confirms zero callers.

**Tech Stack:** React 19 (`forwardRef`), Vitest 4, no API surface change.

---

## File Structure

### New
- `frontend/src/components/Button.jsx`
- `frontend/src/components/Button.test.jsx`
- `frontend/src/components/IconButton.jsx`
- `frontend/src/components/IconButton.test.jsx`

### Modified
- 37 files importing button class strings (full list below) — swap to `<Button>`
- ~19 icon-only `<button>` sites — convert to `<IconButton>` with aria-label
- `frontend/src/constants/styles.js` — keep the class strings (Button uses them internally), but mark as "internal" with a code comment

### Deleted (final task)
- `frontend/src/components/Card.jsx`
- `frontend/src/components/Card.test.jsx` — verify it tests the alias, not ParchmentCard, before removing

### Reference
- 18 files currently import `Card` from `'../components/Card'`. Migrate them to `ParchmentCard` before deletion (Task 7).

---

## Task 1: Build `<Button>` primitive

**Files:**
- Create: `frontend/src/components/Button.jsx`
- Create: `frontend/src/components/Button.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/Button.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Button from './Button.jsx';

describe('Button', () => {
  it('renders children inside a <button>', () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole('button', { name: 'Click me' });
    expect(btn.tagName).toBe('BUTTON');
  });

  it('defaults to variant=primary, type=button', () => {
    render(<Button>x</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('type', 'button');
    expect(btn.className).toContain('sheikah-teal-deep');
  });

  it('applies the requested variant', () => {
    const { rerender } = render(<Button variant="danger">x</Button>);
    expect(screen.getByRole('button').className).toContain('ember');
    rerender(<Button variant="success">x</Button>);
    expect(screen.getByRole('button').className).toContain('moss');
    rerender(<Button variant="secondary">x</Button>);
    expect(screen.getByRole('button').className).toContain('ink-page-aged');
    rerender(<Button variant="ghost">x</Button>);
    expect(screen.getByRole('button').className).toContain('ink-secondary');
  });

  it('applies size padding', () => {
    const { rerender } = render(<Button size="sm">x</Button>);
    expect(screen.getByRole('button').className).toMatch(/px-3 py-1/);
    rerender(<Button size="lg">x</Button>);
    expect(screen.getByRole('button').className).toMatch(/px-5 py-3/);
  });

  it('forwards onClick', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>x</Button>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('respects type=submit when explicitly set', () => {
    render(<Button type="submit">x</Button>);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit');
  });

  it('passes through disabled', () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>x</Button>);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('appends caller className without overriding variant classes', () => {
    render(<Button className="w-full mt-4">x</Button>);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('w-full');
    expect(btn.className).toContain('mt-4');
    expect(btn.className).toContain('sheikah-teal-deep');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/Button.test.jsx`
Expected: 8 fail (component doesn't exist).

- [ ] **Step 3: Implement Button**

Create `frontend/src/components/Button.jsx`:

```jsx
import { forwardRef } from 'react';
import {
  buttonPrimary,
  buttonSecondary,
  buttonDanger,
  buttonGhost,
  buttonSuccess,
} from '../constants/styles';

const VARIANT_CLASSES = {
  primary: buttonPrimary,
  secondary: buttonSecondary,
  danger: buttonDanger,
  ghost: buttonGhost,
  success: buttonSuccess,
};

const SIZE_CLASSES = {
  sm: 'px-3 py-1 text-sm',
  md: 'px-4 py-2',
  lg: 'px-5 py-3 text-lg',
};

/**
 * Button — the single source of truth for tappable parchment buttons.
 * Wraps the class strings from constants/styles.js so call sites read
 * the variant as a prop instead of remembering to import the right name.
 *
 * For icon-only buttons (where there is no visible text label), use
 * <IconButton> instead — it enforces an aria-label.
 */
const Button = forwardRef(function Button(
  { variant = 'primary', size = 'md', type = 'button', className = '', children, ...rest },
  ref,
) {
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.primary;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      ref={ref}
      type={type}
      className={`${variantClass} ${sizeClass} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});

export default Button;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/Button.test.jsx`
Expected: 8 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Button.jsx frontend/src/components/Button.test.jsx
git commit -m "Add Button primitive with variant/size props"
```

---

## Task 2: Build `<IconButton>` primitive

**Files:**
- Create: `frontend/src/components/IconButton.jsx`
- Create: `frontend/src/components/IconButton.test.jsx`

Icon-only buttons need a smaller square footprint and **must** have an `aria-label` since there's no visible text. Make the prop required and assert in development.

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/IconButton.test.jsx`:

```jsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IconButton from './IconButton.jsx';

describe('IconButton', () => {
  let warnSpy;
  beforeEach(() => { warnSpy = vi.spyOn(console, 'error').mockImplementation(() => {}); });
  afterEach(() => { warnSpy.mockRestore(); });

  it('renders the icon child inside a labeled button', () => {
    render(
      <IconButton aria-label="Close">
        <span data-testid="x-icon">x</span>
      </IconButton>,
    );
    const btn = screen.getByRole('button', { name: 'Close' });
    expect(btn).toContainElement(screen.getByTestId('x-icon'));
  });

  it('warns in dev when aria-label is missing', () => {
    render(<IconButton><span>x</span></IconButton>);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('IconButton requires aria-label'),
    );
  });

  it('uses a square padding sized for tap targets', () => {
    render(<IconButton aria-label="Close"><span>x</span></IconButton>);
    expect(screen.getByRole('button').className).toMatch(/p-2/);
  });

  it('forwards onClick', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton aria-label="x" onClick={onClick}><span>i</span></IconButton>);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('supports the same variants as Button', () => {
    render(<IconButton aria-label="x" variant="danger"><span>i</span></IconButton>);
    expect(screen.getByRole('button').className).toContain('ember');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/IconButton.test.jsx`
Expected: 5 fail.

- [ ] **Step 3: Implement IconButton**

Create `frontend/src/components/IconButton.jsx`:

```jsx
import { forwardRef } from 'react';
import {
  buttonPrimary,
  buttonSecondary,
  buttonDanger,
  buttonGhost,
  buttonSuccess,
} from '../constants/styles';

const VARIANT_CLASSES = {
  primary: buttonPrimary,
  secondary: buttonSecondary,
  danger: buttonDanger,
  ghost: buttonGhost,
  success: buttonSuccess,
};

const SIZE_CLASSES = {
  sm: 'p-1.5',
  md: 'p-2',
  lg: 'p-2.5',
};

/**
 * IconButton — square-footprint button for icon-only affordances. Requires
 * aria-label since there is no visible text. In development, missing
 * aria-label triggers a console.error so the gap is visible during work.
 */
const IconButton = forwardRef(function IconButton(
  {
    variant = 'ghost',
    size = 'md',
    type = 'button',
    'aria-label': ariaLabel,
    className = '',
    children,
    ...rest
  },
  ref,
) {
  if (process.env.NODE_ENV !== 'production' && !ariaLabel) {
    // eslint-disable-next-line no-console
    console.error(
      'IconButton requires aria-label so screen-reader users can identify the action.',
    );
  }
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.ghost;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      ref={ref}
      type={type}
      aria-label={ariaLabel}
      className={`${variantClass} ${sizeClass} inline-flex items-center justify-center rounded-lg ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});

export default IconButton;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/IconButton.test.jsx`
Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/IconButton.jsx frontend/src/components/IconButton.test.jsx
git commit -m "Add IconButton primitive with required aria-label"
```

---

## Task 3: Pilot migration — `pages/Habits.jsx`

**Files:**
- Modify: `frontend/src/pages/Habits.jsx`

Habits has 6 button references — a manageable pilot.

- [ ] **Step 1: Replace the import**

Open `frontend/src/pages/Habits.jsx`. Remove `buttonPrimary` from the styles import (it's no longer used after this task):

```js
// Before
import { buttonPrimary } from '../constants/styles';

// After
import Button from '../components/Button';
```

(If Plan C has not yet shipped, this file may also import `inputClass` — leave that alone.)

- [ ] **Step 2: Replace each button**

Pattern — replace:

```jsx
<button
  type="submit"
  disabled={saving}
  className={`${buttonPrimary} w-full py-2.5`}
>
  {saving ? 'Saving…' : 'Create ritual'}
</button>
```

with:

```jsx
<Button
  type="submit"
  variant="primary"
  disabled={saving}
  className="w-full"
>
  {saving ? 'Saving…' : 'Create ritual'}
</Button>
```

(Drop the manual `py-2.5` since `size="md"` handles vertical padding.)

For ghost-variant icon-only buttons in Habits.jsx (delete-confirmation buttons, etc.), use `<IconButton>` with an `aria-label` pulled from the surrounding context (e.g. `aria-label="Delete ritual"`).

- [ ] **Step 3: Run the page test**

Run: `cd frontend && npx vitest run src/pages/Habits.test.jsx`
Expected: pass (the test queries by `getByRole('button', ...)` so the migration is transparent).

- [ ] **Step 4: Smoke test**

```bash
cd frontend && npm run dev
```

Visit `/quests?tab=rituals`. Confirm: virtue/vice tap buttons still work, "+ New ritual" opens the form, the form's submit button has the same look.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Habits.jsx
git commit -m "Migrate Habits buttons to <Button>"
```

---

## Task 4: Wave 1 migration — top 6 files by call-site count

**Files:**
- `frontend/src/pages/Manage.jsx` (10 button-class uses)
- `frontend/src/pages/project/ProjectHeader.jsx` (7)
- `frontend/src/pages/__design.jsx` (6)
- `frontend/src/components/dashboard/HeroPrimaryCard.jsx` (5)
- `frontend/src/components/layout/QuickActionsSheet.jsx` (5)
- `frontend/src/pages/Chores.jsx` (5)

These are the heaviest — biggest payoff per touch.

- [ ] **Step 1: Migrate `Manage.jsx`**

Same pattern as Task 3. After the swap, run:

```bash
cd frontend && npx vitest run src/pages/Manage.test.jsx
```

Commit: `git commit -m "Migrate Manage buttons to <Button>/<IconButton>"`

- [ ] **Step 2: Migrate `project/ProjectHeader.jsx`**

Buttons here are likely a mix of primary + ghost (back nav). Convert any pure-icon back/menu affordances to `<IconButton>` with explicit aria-labels.

```bash
cd frontend && npx vitest run src/pages/project/ProjectHeader.test.jsx 2>/dev/null || true
```

Commit.

- [ ] **Step 3: Migrate `__design.jsx`**

This is the design-system showcase page. Migrating it serves double duty as living documentation of the new primitive. Add a section that demos every variant and size if one isn't already present.

- [ ] **Step 4: Migrate `dashboard/HeroPrimaryCard.jsx`, `layout/QuickActionsSheet.jsx`, `Chores.jsx`**

One commit per file. Run colocated tests after each.

- [ ] **Step 5: Run the full suite**

```bash
cd frontend && npm run lint && npm run test:run
```

Expected: green.

---

## Task 5: Wave 2 migration — remaining 30 files

**Files:** (count in parens — see `Grep buttonPrimary|...` output for full list)

Process in alphabetical order:
- `pages/achievements/{BadgeFormModal,SkillFormModal,SubjectFormModal,CategoryFormModal,ManagePanel}.jsx` (~10)
- `pages/Homework.jsx` (4)
- `pages/Login.jsx` (2)
- `pages/Payments.jsx` (3)
- `pages/Portfolio.jsx` (3)
- `pages/ProjectNew.jsx` (2)
- `pages/Projects.jsx` (2)
- `pages/Quests.jsx` (2)
- `pages/Rewards.jsx` (2)
- `pages/SettingsPage.jsx` (2)
- `pages/Stable.jsx` (3)
- `pages/Timecards.jsx` (4)
- `pages/ingest/{ReviewStep,SourceStep}.jsx` (~4)
- `pages/project/modals/{AddMaterialModal,AddMilestoneModal,AddResourceModal,AddStepModal,EditProjectModal,RequestChangesModal}.jsx` (~18)
- `pages/rewards/{CoinAdjustModal,CoinExchangeModal,RewardFormModal}.jsx` (~6)
- `components/HomeworkSubmitSheet.jsx` (2)

- [ ] **Step 1: Process the achievements/ modals**

One commit each. Run colocated tests after.

- [ ] **Step 2: Process the project/modals/ folder**

These six modals share a similar shape (header + form fields + save/cancel). Establish a consistent pattern: Save = `variant="primary"`, Cancel = `variant="secondary"`.

- [ ] **Step 3: Process the rewards/ modals**

Same cancel/save pattern.

- [ ] **Step 4: Process the remaining standalone pages**

Alphabetical sweep.

- [ ] **Step 5: Verify the migration is complete**

```bash
cd frontend
grep -rn "buttonPrimary\|buttonSecondary\|buttonDanger\|buttonGhost\|buttonSuccess" src/ --include="*.jsx" \
  | grep -v "test.js\|test.jsx\|constants/styles.js\|Button.jsx\|IconButton.jsx"
```

Expected: 0 hits.

- [ ] **Step 6: Mark the class strings as internal**

Add a comment to [`frontend/src/constants/styles.js`](../../../frontend/src/constants/styles.js) above the button block:

```js
// INTERNAL: these class strings are now consumed only by <Button> and
// <IconButton> (frontend/src/components/Button.jsx). New call sites should
// use the components, not these strings directly.
```

- [ ] **Step 7: Run the full gate**

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected: green; coverage ≥ thresholds.

---

## Task 6: Sweep up unlabeled icon-only buttons

**Files:**
- ~19 sites identified by the audit (icon-only `<button>` with no `aria-label`).

After Tasks 4–5, most icon-only buttons in those files were already converted to `<IconButton>` (which forced aria-label). The remainder are buttons that were styled with `buttonGhost` but still use raw `<button>` syntax with an embedded icon and no label.

- [ ] **Step 1: Find the remaining offenders**

Run:

```bash
cd frontend
# Match raw <button…> tags whose immediate child is a self-closing or
# JSX-element icon (capitalized component) with no aria-label on the button.
grep -rEn "<button[^>]*>" src/ --include="*.jsx" \
  | grep -v "aria-label" \
  | grep -E "<(Plus|Pencil|Trash2|Edit|X|ChevronDown|ChevronRight|Settings|MoreVertical|Check|ArrowLeft|ArrowRight|Filter|Search|Bell)"
```

Expected: ~19 hits (give or take).

- [ ] **Step 2: For each hit, migrate to `<IconButton>` with the right label**

Pull the label from surrounding context — the action verb plus the noun makes the best label:

| Icon | Typical label |
|---|---|
| `<Plus />` | `aria-label="Add <thing>"` |
| `<Pencil />` | `aria-label="Edit <thing>"` |
| `<Trash2 />` | `aria-label="Delete <thing>"` |
| `<X />` | `aria-label="Close"` or `"Remove <thing>"` |
| `<ChevronDown />` | `aria-label="Expand"` / `"Collapse"` |
| `<MoreVertical />` | `aria-label="More options"` |
| `<Bell />` | `aria-label="Notifications"` |

Pattern — replace:

```jsx
<button onClick={...} className="text-ink-secondary hover:text-ink-primary">
  <Trash2 size={16} />
</button>
```

with:

```jsx
<IconButton onClick={...} variant="ghost" size="sm" aria-label="Delete chore">
  <Trash2 size={16} />
</IconButton>
```

Commit one file per change.

- [ ] **Step 3: Verify zero unlabeled icon buttons remain**

Re-run the grep from Step 1. Expected: 0 hits (or only those with text content alongside the icon, which don't need a label).

- [ ] **Step 4: Run the gate**

```bash
cd frontend && npm run lint && npm run test:run
```

---

## Task 7: Migrate `Card` → `ParchmentCard` and delete the alias

**Files:**
- Modify: 18 files importing `Card` (see grep output)
- Delete: `frontend/src/components/Card.jsx`
- Delete (or repurpose): `frontend/src/components/Card.test.jsx`

[`Card.jsx`](../../../frontend/src/components/Card.jsx) is a 14-line back-compat shim that just re-exports `ParchmentCard`. Migrate the 18 import sites and delete it.

- [ ] **Step 1: Find every importer**

Run:

```bash
cd frontend && grep -rln "from '../components/Card'\|from '../../components/Card'\|from '../../../components/Card'\|from '\\./Card'" src/
```

(Adjust glob depths as needed.) Expected: 18 files (plus `Card.test.jsx`).

- [ ] **Step 2: Codemod each importer**

For each file, replace the import:

```js
// Before
import Card from '../components/Card';

// After
import ParchmentCard from '../components/journal/ParchmentCard';
```

Then `replace_all`: `<Card` → `<ParchmentCard` and `</Card>` → `</ParchmentCard>`.

Commit one file per change.

- [ ] **Step 3: Verify no live import sites remain**

```bash
cd frontend
grep -rn "from.*\\bCard'" src/ --include="*.jsx" --include="*.js" | grep -v "ParchmentCard\|RewardCard\|StatusCard\|HeroPrimaryCard\|.test."
```

Expected: 0 hits.

- [ ] **Step 4: Inspect `Card.test.jsx` and decide its fate**

Open `frontend/src/components/Card.test.jsx`. If it asserts the alias delegates to ParchmentCard (and nothing else), delete it — `ParchmentCard.test.jsx` already covers the underlying behavior. If it has unique assertions, port them.

- [ ] **Step 5: Delete `Card.jsx`**

```bash
rm frontend/src/components/Card.jsx
rm frontend/src/components/Card.test.jsx   # only if Step 4 confirmed it's redundant
```

- [ ] **Step 6: Run the full gate**

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected: green; no test references the deleted file.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/components/Card.jsx frontend/src/components/Card.test.jsx
git commit -m "Delete Card alias; migrate callers to ParchmentCard"
```

---

## Verification

End-to-end smoke:

```bash
cd frontend && npm run dev
```

Visit every route the app exposes (the chapter nav covers them). For each page:
- All buttons should look identical to before — no regression.
- Hover any icon-only button. The browser should show the new aria-label as a tooltip-equivalent in the accessibility tree.
- Open DevTools → Elements → Accessibility on `/manage` and any page with icon affordances. Every button should have a name.

Run the test gate:

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected:
- 2 new test files (Button + IconButton)
- Coverage rises (function/branch coverage on the variant maps)
- Lint clean
- Build succeeds

Search for stragglers one more time:

```bash
cd frontend
grep -rn "className=\\(\"\\|'\\|{\\)\\(buttonPrimary\\|buttonSecondary\\|buttonDanger\\|buttonGhost\\|buttonSuccess\\)" src/
grep -rn "from.*\\bCard'" src/ | grep -v "ParchmentCard\\|.test."
```

Both should return 0 hits (excluding the internal usage inside `Button.jsx` and `IconButton.jsx`).

---

## Plan-vs-Reality (post-execution addendum)

**Audit gap #4 (no shared Button) and #13 (Card alias deletion) — fully closed.**
- 35 files / 54 button-class call sites migrated to `<Button>`
- 17 importers migrated to `<ParchmentCard>`; `Card.jsx` + `Card.test.jsx` deleted

**Audit gap #10 (icon-only buttons lack aria-label) — closed at the a11y level, partially at the cohort-consistency level.**
- The audit predicted ~19 unlabeled icon-only buttons. Reality: only **8** sites lacked an aria-label by the time Task 6 ran — the wave migration in Tasks 3-5 added many aria-labels in passing, and prior PRs (Plan B's [`SkillTreeView`](frontend/src/pages/achievements/SkillTreeView.jsx) follow-up, the standalone aria-label sweep on `ApprovalQueueList`) had already covered others.
- Those 8 sites were converted to `<IconButton>` in commit `cf18127`.
- **An additional ~12 icon-only `<button>` sites already have a valid `aria-label` and were left as raw markup** — they're functionally accessible but not visually using the `<IconButton>` primitive. Examples: `Habits.jsx:238-253` (Edit/Delete ritual), `Chores.jsx:342,350` (Edit/Delete duty), `RewardShop.jsx:19,27` (Edit/Delete reward), `HomeworkSubmitSheet.jsx:83-90` (Remove photo), the X buttons across the `pages/ingest/*Editor.jsx` cohort. Plan D's stated scope was *closing the a11y gap*, not *enforcing primitive consistency on already-accessible markup* — converting these is a polish PR, not a bugfix.

**One asymmetry caught and fixed in `35deb5f`-style polish:** [`Manage.jsx`](frontend/src/pages/Manage.jsx) had Edit as `<Button>` and Delete as `<IconButton>` *in the same row*. The Edit was converted to `<IconButton>` so the matched pair is consistent.

**One pre-existing typo cleaned in passing:** [`NotificationBell.jsx`](frontend/src/components/NotificationBell.jsx) had `hover:bg-ink-page-shadow/60/50` (double `/60/50` modifier — invalid Tailwind, no-ops at runtime). Carried verbatim by the IconButton conversion; cleaned up to `hover:bg-ink-page-shadow/60`.

**Out of scope (documented for follow-up):**
1. Convert the ~12 already-labeled icon-only `<button>` sites to `<IconButton>` for cohort consistency.
2. Add an ESLint rule (or `@deprecated` JSDoc on `buttonPrimary`/etc.) to deflect future PRs from re-introducing the raw-button-class pattern.
