# Design System B: Primitive A11y + Test Backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring six shared primitive components up to a consistent baseline — add the WCAG-required ARIA roles/attributes that are currently missing, and backfill colocated tests for the five primitives that have none.

**Architecture:** No new components, no API changes, no migrations. Each task is one component: tighten the JSX (1–4 lines of ARIA), add a colocated `*.test.jsx` that proves the new attributes render and that existing behavior still works.

**Tech Stack:** React 19, Vitest 4 + React Testing Library, jest-dom matchers (already globally registered via [`frontend/src/test/setup.js`](../../../frontend/src/test/setup.js)).

---

## File Structure

### Modified
- `frontend/src/components/Loader.jsx` — add `role="status"`, `aria-busy`, `aria-label`
- `frontend/src/components/ProgressBar.jsx` — add `role="progressbar"`, `aria-valuenow/min/max`, `aria-label`
- `frontend/src/components/ErrorAlert.jsx` — add `role="alert"`
- `frontend/src/components/EmptyState.jsx` — add `role="status"`
- `frontend/src/components/BottomSheet.jsx` — add `role="dialog"`, `aria-modal`, `aria-labelledby`
- `frontend/src/components/StatusBadge.jsx` — fix unstyled fallback className (`bg-gray-500/20 text-gray-400` is not a token)

### New
- `frontend/src/components/Loader.test.jsx`
- `frontend/src/components/ProgressBar.test.jsx`
- `frontend/src/components/ErrorAlert.test.jsx`
- `frontend/src/components/EmptyState.test.jsx`
- `frontend/src/components/StatusBadge.test.jsx`
- (BottomSheet already has `BottomSheet.test.jsx` — extend it.)

### Reference (do not modify)
- `frontend/src/components/journal/ParchmentCard.test.jsx` — exemplar test pattern
- `frontend/src/test/render.jsx` — `renderWithProviders` (only needed for components that use auth/router; primitives use plain `render`)

---

## Task 1: Loader — `role="status"` + `aria-busy` + tests

**Files:**
- Modify: `frontend/src/components/Loader.jsx:24-39`
- Create: `frontend/src/components/Loader.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/Loader.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import Loader from './Loader.jsx';

describe('Loader', () => {
  it('renders nothing before delayMs elapses', () => {
    vi.useFakeTimers();
    const { container } = render(<Loader delayMs={200} />);
    expect(container.firstChild).toBeNull();
    vi.useRealTimers();
  });

  it('renders the spinner after the delay', () => {
    vi.useFakeTimers();
    render(<Loader delayMs={50} />);
    act(() => { vi.advanceTimersByTime(60); });
    expect(screen.getByRole('status')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('renders immediately when delayMs is 0', () => {
    render(<Loader delayMs={0} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('exposes aria-busy and an accessible name to screen readers', () => {
    render(<Loader delayMs={0} />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAccessibleName(/loading/i);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/Loader.test.jsx`
Expected: 4 tests, 2 pass (the render-timing tests), 2 fail (missing `role="status"` and `aria-busy`).

- [ ] **Step 3: Add ARIA attributes to Loader**

Edit `frontend/src/components/Loader.jsx`. Replace the wrapper `<div className="flex items-center justify-center py-12">` (line 24) with:

```jsx
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className="flex items-center justify-center py-12"
    >
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/Loader.test.jsx`
Expected: 4 tests, 4 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Loader.jsx frontend/src/components/Loader.test.jsx
git commit -m "Loader: role=status + aria-busy + tests"
```

---

## Task 2: ProgressBar — `role="progressbar"` + `aria-valuenow/min/max` + tests

**Files:**
- Modify: `frontend/src/components/ProgressBar.jsx`
- Create: `frontend/src/components/ProgressBar.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/ProgressBar.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProgressBar from './ProgressBar.jsx';

describe('ProgressBar', () => {
  it('renders a progressbar with the value and bounds', () => {
    render(<ProgressBar value={30} max={100} aria-label="Quest progress" />);
    const bar = screen.getByRole('progressbar', { name: 'Quest progress' });
    expect(bar).toHaveAttribute('aria-valuenow', '30');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
  });

  it('clamps values above max to 100% width and reports max as aria-valuenow', () => {
    render(<ProgressBar value={150} max={100} aria-label="x" />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '100');
  });

  it('reports 0 when max is 0 (avoid divide-by-zero)', () => {
    render(<ProgressBar value={5} max={0} aria-label="x" />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuenow', '0');
  });

  it('falls back to a generic label when caller omits aria-label', () => {
    render(<ProgressBar value={50} max={100} />);
    expect(screen.getByRole('progressbar')).toHaveAccessibleName(/progress/i);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/ProgressBar.test.jsx`
Expected: 4 tests, 4 fail (no `role="progressbar"` yet).

- [ ] **Step 3: Add ARIA to ProgressBar**

Replace `frontend/src/components/ProgressBar.jsx` with:

```jsx
import { motion } from 'framer-motion';

/**
 * ProgressBar — parchment track with a sheikah-teal fill by default.
 * Callers can override `color` with any Tailwind bg-* class.
 */
export default function ProgressBar({
  value,
  max = 100,
  color = 'bg-sheikah-teal-deep',
  className = '',
  'aria-label': ariaLabel = 'Progress',
}) {
  const safeValue = max > 0 ? Math.min(max, Math.max(0, value)) : 0;
  const pct = max > 0 ? (safeValue / max) * 100 : 0;
  return (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuenow={Math.round(safeValue)}
      aria-valuemin={0}
      aria-valuemax={max}
      className={`h-2 bg-ink-page-shadow/60 rounded-full overflow-hidden ${className}`}
    >
      <motion.div
        className={`h-full ${color} rounded-full`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/ProgressBar.test.jsx`
Expected: 4 pass.

- [ ] **Step 5: Run the full suite to catch regressions**

Run: `cd frontend && npm run test:run`
Expected: all green. Existing call sites that didn't pass `aria-label` now show "Progress" as the accessible name — that's intentional. If any test snapshots break on the new aria attributes, update them.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ProgressBar.jsx frontend/src/components/ProgressBar.test.jsx
git commit -m "ProgressBar: role=progressbar + aria-value attrs + tests"
```

---

## Task 3: ErrorAlert — `role="alert"` + tests

**Files:**
- Modify: `frontend/src/components/ErrorAlert.jsx`
- Create: `frontend/src/components/ErrorAlert.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/ErrorAlert.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorAlert from './ErrorAlert.jsx';

describe('ErrorAlert', () => {
  it('renders nothing when message is falsy', () => {
    const { container } = render(<ErrorAlert message="" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when message is undefined', () => {
    const { container } = render(<ErrorAlert />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the message inside an alert role when provided', () => {
    render(<ErrorAlert message="Something broke" />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Something broke');
  });

  it('passes through custom className', () => {
    render(<ErrorAlert message="x" className="mt-4" />);
    expect(screen.getByRole('alert').className).toContain('mt-4');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/ErrorAlert.test.jsx`
Expected: 2 pass (the falsy-message ones), 2 fail.

- [ ] **Step 3: Add `role="alert"` to ErrorAlert**

Edit `frontend/src/components/ErrorAlert.jsx`. Replace the `<div>` opener with:

```jsx
    <div
      role="alert"
      className={`text-ember-deep text-sm bg-ember/10 px-3 py-2 rounded-lg border border-ember/40 font-body ${className}`}
    >
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/ErrorAlert.test.jsx`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ErrorAlert.jsx frontend/src/components/ErrorAlert.test.jsx
git commit -m "ErrorAlert: role=alert + tests"
```

---

## Task 4: EmptyState — `role="status"` + tests

**Files:**
- Modify: `frontend/src/components/EmptyState.jsx`
- Create: `frontend/src/components/EmptyState.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/EmptyState.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import EmptyState from './EmptyState.jsx';

describe('EmptyState', () => {
  it('renders children inside a status region', () => {
    render(<EmptyState>No quests yet</EmptyState>);
    expect(screen.getByRole('status')).toHaveTextContent('No quests yet');
  });

  it('renders the icon slot when provided', () => {
    render(<EmptyState icon={<svg data-testid="ico" />}>Nothing</EmptyState>);
    expect(screen.getByTestId('ico')).toBeInTheDocument();
  });

  it('omits the icon slot when no icon prop', () => {
    render(<EmptyState>x</EmptyState>);
    expect(screen.queryByTestId('ico')).not.toBeInTheDocument();
  });

  it('passes through className', () => {
    render(<EmptyState className="my-custom">x</EmptyState>);
    expect(screen.getByRole('status').className).toContain('my-custom');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/EmptyState.test.jsx`
Expected: 4 fail (no `role="status"` yet).

- [ ] **Step 3: Add `role="status"` via ParchmentCard's `as` prop**

Replace `frontend/src/components/EmptyState.jsx` with:

```jsx
import ParchmentCard from './journal/ParchmentCard';

/**
 * EmptyState — a blank journal page with an ink flourish. Used whenever a
 * list or collection has no items yet.
 */
export default function EmptyState({ children, icon, className = '' }) {
  return (
    <ParchmentCard
      flourish
      role="status"
      className={`text-center py-10 text-ink-secondary font-body italic ${className}`}
    >
      {icon && <div className="flex justify-center mb-2 text-ink-whisper">{icon}</div>}
      {children}
    </ParchmentCard>
  );
}
```

ParchmentCard already spreads `...props` onto its root element ([ParchmentCard.jsx:50](../../../frontend/src/components/journal/ParchmentCard.jsx#L50)), so `role="status"` lands on the rendered `<div>`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/EmptyState.test.jsx`
Expected: 4 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EmptyState.jsx frontend/src/components/EmptyState.test.jsx
git commit -m "EmptyState: role=status + tests"
```

---

## Task 5: BottomSheet — `role="dialog"` + `aria-modal` + `aria-labelledby` + extend tests

**Files:**
- Modify: `frontend/src/components/BottomSheet.jsx`
- Modify: `frontend/src/components/BottomSheet.test.jsx`

The component renders a modal — both the desktop and mobile branches need `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` pointing at the title `<h2>`. Use a per-instance ID to support multiple sheets in tests.

- [ ] **Step 1: Read existing BottomSheet tests**

Read `frontend/src/components/BottomSheet.test.jsx` to understand the existing render pattern (matchMedia is polyfilled in [`test/setup.js`](../../../frontend/src/test/setup.js)).

- [ ] **Step 2: Add a failing test**

Append to `frontend/src/components/BottomSheet.test.jsx`:

```jsx
  it('exposes a labeled dialog role on the sheet surface', () => {
    render(<BottomSheet title="Edit reward" onClose={() => {}}>body</BottomSheet>);
    const dialog = screen.getByRole('dialog', { name: 'Edit reward' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/BottomSheet.test.jsx`
Expected: existing tests pass; the new one fails (no `role="dialog"`).

- [ ] **Step 4: Add ARIA to both branches**

In `frontend/src/components/BottomSheet.jsx`, change the function signature to generate a stable ID and add it to both `motion.div`s and the title `<h2>`s. Replace the entire function body with:

```jsx
import { useEffect, useId, useState } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import ModalBackdrop from './modal/ModalBackdrop';
import SealCloseButton from './modal/SealCloseButton';
import SealPulseRing from './modal/SealPulseRing';

function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined') return true;
    return window.matchMedia('(min-width: 768px)').matches;
  });
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = (e) => setIsDesktop(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isDesktop;
}

export default function BottomSheet({ title, onClose, disabled, children }) {
  const isDesktop = useIsDesktop();
  const titleId = useId();

  return createPortal(
    <AnimatePresence>
      <ModalBackdrop onClick={onClose} disabled={disabled} zIndex="z-40" />
      {isDesktop ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
          <motion.div
            key="sheet-desktop"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ scale: 0.88, opacity: 0, rotate: -1.5 }}
            animate={{ scale: 1, opacity: 1, rotate: 0 }}
            exit={{ scale: 0.94, opacity: 0 }}
            transition={{ type: 'spring', damping: 22, stiffness: 260 }}
            className="pointer-events-auto relative w-full max-w-lg parchment-bg-aged border border-ink-page-shadow rounded-2xl modal-seal-ring max-h-[85vh] overflow-y-auto overflow-x-hidden scrollbar-hide"
          >
            <SealPulseRing rounded="rounded-2xl" />
            <div className="relative flex items-center justify-between px-5 pt-4 pb-2">
              <h2 id={titleId} className="font-display text-lg font-bold text-ink-primary">{title}</h2>
              <SealCloseButton onClick={onClose} disabled={disabled} />
            </div>
            <div className="relative px-5 pb-5 space-y-3">
              {children}
            </div>
          </motion.div>
        </div>
      ) : (
        <motion.div
          key="sheet-mobile"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          initial={{ y: '100%' }}
          animate={{ y: 0 }}
          exit={{ y: '100%' }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          className="fixed bottom-0 left-0 right-0 parchment-bg-aged border-t border-ink-page-shadow rounded-t-2xl z-50 pb-[env(safe-area-inset-bottom)] max-h-[90vh] overflow-y-auto overflow-x-hidden scrollbar-hide modal-seal-ring"
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute left-0 right-0 -top-1 h-2 animate-halo-rise"
            style={{
              background:
                'linear-gradient(to right, transparent 0%, rgba(77, 208, 225, 0.65) 50%, transparent 100%)',
              filter: 'blur(3px)',
            }}
          />
          <div className="flex justify-center pt-2">
            <div
              className="w-12 h-1.5 rounded-full animate-rune-pulse"
              style={{
                background:
                  'linear-gradient(to right, transparent, var(--color-sheikah-teal) 50%, transparent)',
              }}
            />
          </div>
          <div className="flex items-center justify-between px-4 pt-3 pb-2">
            <h2 id={titleId} className="font-display text-lg font-bold text-ink-primary">{title}</h2>
            <SealCloseButton onClick={onClose} disabled={disabled} />
          </div>
          <div className="px-4 pb-4 space-y-3">
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
```

Key changes:
- Added `useId` import on line 1
- Added `const titleId = useId();` after `const isDesktop = useIsDesktop();`
- Added `role="dialog" aria-modal="true" aria-labelledby={titleId}` to both `motion.div`s
- Added `id={titleId}` to both `<h2>` elements

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/BottomSheet.test.jsx`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BottomSheet.jsx frontend/src/components/BottomSheet.test.jsx
git commit -m "BottomSheet: role=dialog + aria-modal + aria-labelledby"
```

---

## Task 6: StatusBadge — fix unstyled fallback + tests

**Files:**
- Modify: `frontend/src/components/StatusBadge.jsx`
- Create: `frontend/src/components/StatusBadge.test.jsx`

The component is small but has one bug: the fallback `'bg-gray-500/20 text-gray-400'` (line 4) breaks the journal aesthetic when an unknown status arrives — Tailwind 4 may not even ship `bg-gray-500` since the `@theme` block doesn't declare it. Replace with a token-driven fallback.

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/StatusBadge.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StatusBadge from './StatusBadge.jsx';

describe('StatusBadge', () => {
  it('renders the friendly label for in_progress', () => {
    render(<StatusBadge status="in_progress" />);
    expect(screen.getByText('In Progress')).toBeInTheDocument();
  });

  it('renders the friendly label for in_review', () => {
    render(<StatusBadge status="in_review" />);
    expect(screen.getByText('In Review')).toBeInTheDocument();
  });

  it('title-cases an unknown status as a fallback label', () => {
    render(<StatusBadge status="something_new" />);
    expect(screen.getByText(/Something_new/i)).toBeInTheDocument();
  });

  it('uses a token-driven className for unknown statuses (no bg-gray)', () => {
    const { container } = render(<StatusBadge status="something_new" />);
    expect(container.firstChild.className).not.toContain('bg-gray');
    expect(container.firstChild.className).toContain('ink-whisper');
  });

  it('uses the STATUS_COLORS class for known statuses', () => {
    const { container } = render(<StatusBadge status="completed" />);
    expect(container.firstChild.className).toContain('moss');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/StatusBadge.test.jsx`
Expected: 3 pass, the unknown-status className test fails.

- [ ] **Step 3: Replace the fallback with a token class**

Edit `frontend/src/components/StatusBadge.jsx` line 4:

```jsx
// Before
const color = STATUS_COLORS[status] || 'bg-gray-500/20 text-gray-400';

// After
const color = STATUS_COLORS[status] || 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30';
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/StatusBadge.test.jsx`
Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatusBadge.jsx frontend/src/components/StatusBadge.test.jsx
git commit -m "StatusBadge: token fallback className + tests"
```

---

## Verification

Run the full gate:

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected:
- 5 new test files (StatusBadge / Loader / EmptyState / ProgressBar / ErrorAlert)
- BottomSheet test count up by 1
- Coverage thresholds (65/55/55/65) still met — these primitives now have `function` coverage they previously lacked, so the metric should rise

Smoke test in the browser:

```bash
cd frontend && npm run dev
```

- Visit any page with a `<Loader>` showing (refresh `/dashboard` and watch the brief spinner) — DevTools → Accessibility tab should show `role: status, aria-busy: true`.
- Visit `/quests` — the active-quest progress bar should expose `role: progressbar` with sensible `aria-value*` attributes.
- Trigger any error path (e.g. submit an invalid form on `/manage`) — the `<ErrorAlert>` should now announce in screen readers (`role: alert`).
- Open any `*FormModal` — DevTools should show `role: dialog, aria-modal: true, aria-labelledby` on the sheet surface.
- Visit a page with an empty list (e.g. `/manage` → Subjects with none) — the `<EmptyState>` should be a `role: status` region.

No visual regression should be detectable. The work is purely accessibility metadata.
