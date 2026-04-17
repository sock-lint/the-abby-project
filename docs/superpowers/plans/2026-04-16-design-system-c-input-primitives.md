# Design System C: Input / Select / Textarea Primitives — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 118 raw `<input>` / `<select>` / `<textarea>` call sites (each manually styled with `className={inputClass}` and a hand-rolled `<label>`) with three shared primitives: `<TextField>`, `<SelectField>`, and `<TextAreaField>`. Same visual output, half the JSX, baked-in label/error/help-text association.

**Architecture:** Three new primitives in `frontend/src/components/form/`. Each wraps the existing `inputClass` style string from [`constants/styles.js`](../../../frontend/src/constants/styles.js), generates a stable `useId()` for label/control association, exposes `label`, `error`, `helpText` props, and forwards every other prop to the native control via `forwardRef`. Migration is a one-page-per-task sweep over the 30 files that import `inputClass`. The plan ends with a small follow-up: migrating the 6 hand-rolled empty states the audit found to `<EmptyState>`.

**Tech Stack:** React 19 (`useId`, `forwardRef`), Vitest 4, MSW 2 (no API surface change — pure UI refactor).

---

## File Structure

### New
- `frontend/src/components/form/TextField.jsx`
- `frontend/src/components/form/TextField.test.jsx`
- `frontend/src/components/form/SelectField.jsx`
- `frontend/src/components/form/SelectField.test.jsx`
- `frontend/src/components/form/TextAreaField.jsx`
- `frontend/src/components/form/TextAreaField.test.jsx`
- `frontend/src/components/form/index.js` — barrel export

### Modified (30 files importing `inputClass`)
Identified by `grep "from '.*constants/styles'" frontend/src` filtering for `inputClass`:
- `frontend/src/pages/achievements/{BadgeFormModal,SkillFormModal,SubjectFormModal,CategoryFormModal}.jsx`
- `frontend/src/pages/rewards/{RewardFormModal,CoinExchangeModal,CoinAdjustModal}.jsx`
- `frontend/src/pages/project/modals/{AddResourceModal,AddMaterialModal,AddMilestoneModal,AddStepModal,EditProjectModal}.jsx`
- `frontend/src/pages/ingest/{SourceStep,MilestonesEditor,StepsEditor,ResourcesEditor,ProjectOverridesCard}.jsx`
- `frontend/src/pages/{Chores,Habits,Homework,Manage,Login,Payments,Portfolio,Stable,ClockPage,ProjectNew,__design}.jsx`
- `frontend/src/components/HomeworkSubmitSheet.jsx`
- `frontend/src/components/layout/QuickActionsSheet.jsx`

### Modified (EmptyState stragglers — surfaced by `Grep "No (chores|homework|projects|approvals)" --not -- "<EmptyState"`)
- `frontend/src/components/dashboard/ApprovalQueueList.jsx:114`
- `frontend/src/pages/Stable.jsx`
- `frontend/src/pages/Timecards.jsx`
- (3 more to discover via grep — see Task 6)

---

## Task 1: Build `<TextField>` primitive

**Files:**
- Create: `frontend/src/components/form/TextField.jsx`
- Create: `frontend/src/components/form/TextField.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/form/TextField.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import TextField from './TextField.jsx';

describe('TextField', () => {
  it('associates the label with the input via htmlFor/id', () => {
    render(<TextField label="Name" />);
    const input = screen.getByLabelText('Name');
    expect(input.tagName).toBe('INPUT');
  });

  it('forwards arbitrary props to the underlying input', () => {
    render(<TextField label="Name" type="email" placeholder="you@x.com" />);
    const input = screen.getByLabelText('Name');
    expect(input).toHaveAttribute('type', 'email');
    expect(input).toHaveAttribute('placeholder', 'you@x.com');
  });

  it('renders helpText when provided', () => {
    render(<TextField label="Name" helpText="Use your full legal name" />);
    expect(screen.getByText('Use your full legal name')).toBeInTheDocument();
  });

  it('renders error text and sets aria-invalid when error is provided', () => {
    render(<TextField label="Name" error="Required" />);
    const input = screen.getByLabelText('Name');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('is fully controlled — value updates on each keystroke', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('');
      return <TextField label="Name" value={v} onChange={(e) => setV(e.target.value)} />;
    }
    render(<Harness />);
    await user.type(screen.getByLabelText('Name'), 'Abby');
    expect(screen.getByLabelText('Name')).toHaveValue('Abby');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/form/TextField.test.jsx`
Expected: 5 fail (component doesn't exist).

- [ ] **Step 3: Implement TextField**

Create `frontend/src/components/form/TextField.jsx`:

```jsx
import { forwardRef, useId } from 'react';
import { inputClass } from '../../constants/styles';

const labelClass = 'font-script text-sm text-ink-secondary mb-1 block';
const helpClass = 'text-xs text-ink-whisper mt-1';
const errorClass = 'text-xs text-ember-deep mt-1';

const TextField = forwardRef(function TextField(
  { label, error, helpText, id: idProp, className = '', ...rest },
  ref,
) {
  const generatedId = useId();
  const id = idProp || generatedId;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelClass}>{label}</label>}
      <input
        ref={ref}
        id={id}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={helpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={errorClass}>{error}</p>}
    </div>
  );
});

export default TextField;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/form/TextField.test.jsx`
Expected: 5 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/form/TextField.jsx frontend/src/components/form/TextField.test.jsx
git commit -m "Add TextField form primitive"
```

---

## Task 2: Build `<SelectField>` primitive

**Files:**
- Create: `frontend/src/components/form/SelectField.jsx`
- Create: `frontend/src/components/form/SelectField.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/form/SelectField.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import SelectField from './SelectField.jsx';

describe('SelectField', () => {
  it('associates label and renders option children', () => {
    render(
      <SelectField label="Type">
        <option value="a">A</option>
        <option value="b">B</option>
      </SelectField>,
    );
    const select = screen.getByLabelText('Type');
    expect(select.tagName).toBe('SELECT');
    expect(select.querySelectorAll('option')).toHaveLength(2);
  });

  it('forwards value/onChange', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('a');
      return (
        <SelectField label="Type" value={v} onChange={(e) => setV(e.target.value)}>
          <option value="a">A</option>
          <option value="b">B</option>
        </SelectField>
      );
    }
    render(<Harness />);
    await user.selectOptions(screen.getByLabelText('Type'), 'b');
    expect(screen.getByLabelText('Type')).toHaveValue('b');
  });

  it('renders error and sets aria-invalid', () => {
    render(<SelectField label="Type" error="Pick one"><option value="">--</option></SelectField>);
    expect(screen.getByLabelText('Type')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Pick one')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/form/SelectField.test.jsx`
Expected: 3 fail.

- [ ] **Step 3: Implement SelectField**

Create `frontend/src/components/form/SelectField.jsx`:

```jsx
import { forwardRef, useId } from 'react';
import { inputClass } from '../../constants/styles';

const labelClass = 'font-script text-sm text-ink-secondary mb-1 block';
const helpClass = 'text-xs text-ink-whisper mt-1';
const errorClass = 'text-xs text-ember-deep mt-1';

const SelectField = forwardRef(function SelectField(
  { label, error, helpText, id: idProp, className = '', children, ...rest },
  ref,
) {
  const generatedId = useId();
  const id = idProp || generatedId;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelClass}>{label}</label>}
      <select
        ref={ref}
        id={id}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      >
        {children}
      </select>
      {helpText && !error && <p id={helpId} className={helpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={errorClass}>{error}</p>}
    </div>
  );
});

export default SelectField;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/form/SelectField.test.jsx`
Expected: 3 pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/form/SelectField.jsx frontend/src/components/form/SelectField.test.jsx
git commit -m "Add SelectField form primitive"
```

---

## Task 3: Build `<TextAreaField>` primitive

**Files:**
- Create: `frontend/src/components/form/TextAreaField.jsx`
- Create: `frontend/src/components/form/TextAreaField.test.jsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/components/form/TextAreaField.test.jsx`:

```jsx
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import TextAreaField from './TextAreaField.jsx';

describe('TextAreaField', () => {
  it('associates the label with the textarea', () => {
    render(<TextAreaField label="Notes" rows={5} />);
    const ta = screen.getByLabelText('Notes');
    expect(ta.tagName).toBe('TEXTAREA');
    expect(ta).toHaveAttribute('rows', '5');
  });

  it('updates value via controlled change', async () => {
    const user = userEvent.setup();
    function Harness() {
      const [v, setV] = useState('');
      return <TextAreaField label="Notes" value={v} onChange={(e) => setV(e.target.value)} />;
    }
    render(<Harness />);
    await user.type(screen.getByLabelText('Notes'), 'Hello');
    expect(screen.getByLabelText('Notes')).toHaveValue('Hello');
  });

  it('renders error and sets aria-invalid', () => {
    render(<TextAreaField label="Notes" error="Too short" />);
    expect(screen.getByLabelText('Notes')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Too short')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/form/TextAreaField.test.jsx`
Expected: 3 fail.

- [ ] **Step 3: Implement TextAreaField**

Create `frontend/src/components/form/TextAreaField.jsx`:

```jsx
import { forwardRef, useId } from 'react';
import { inputClass } from '../../constants/styles';

const labelClass = 'font-script text-sm text-ink-secondary mb-1 block';
const helpClass = 'text-xs text-ink-whisper mt-1';
const errorClass = 'text-xs text-ember-deep mt-1';

const TextAreaField = forwardRef(function TextAreaField(
  { label, error, helpText, id: idProp, className = '', rows = 3, ...rest },
  ref,
) {
  const generatedId = useId();
  const id = idProp || generatedId;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelClass}>{label}</label>}
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={helpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={errorClass}>{error}</p>}
    </div>
  );
});

export default TextAreaField;
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/form/TextAreaField.test.jsx`
Expected: 3 pass.

- [ ] **Step 5: Add the barrel export**

Create `frontend/src/components/form/index.js`:

```js
export { default as TextField } from './TextField.jsx';
export { default as SelectField } from './SelectField.jsx';
export { default as TextAreaField } from './TextAreaField.jsx';
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/form
git commit -m "Add TextAreaField primitive and form barrel"
```

---

## Task 4: Pilot migration — `pages/Habits.jsx` HabitFormModal

**Files:**
- Modify: `frontend/src/pages/Habits.jsx:31-124`

This is the smallest representative form — five fields covering input/select with conditional rendering. Migrate it first to validate the primitive ergonomics, then use the diff as a template for the other 29 files.

- [ ] **Step 1: Replace the imports**

Open `frontend/src/pages/Habits.jsx`. Remove:

```js
import { buttonPrimary, inputClass } from '../constants/styles';
```

Replace with:

```js
import { buttonPrimary } from '../constants/styles';
import { TextField, SelectField } from '../components/form';
```

- [ ] **Step 2: Replace each field block in `HabitFormModal`**

The current pattern (lines 75-112) is:

```jsx
<div>
  <label className={labelClass}>Name</label>
  <input className={inputClass} value={form.name} onChange={onField('name')} required />
</div>
```

Becomes:

```jsx
<TextField label="Name" value={form.name} onChange={onField('name')} required />
```

For the select blocks, replace with `<SelectField>`:

```jsx
<SelectField label="Type" value={form.habit_type} onChange={onField('habit_type')}>
  <option value="positive">Virtue (+)</option>
  <option value="negative">Vice (−)</option>
  <option value="both">Both</option>
</SelectField>
```

Delete the local `const labelClass = ...` declaration at line 43 — it's no longer used.

- [ ] **Step 3: Run the Habits page test**

Run: `cd frontend && npx vitest run src/pages/Habits.test.jsx`
Expected: all existing tests still pass (the new primitives produce equivalent DOM that `getByLabelText` queries see correctly).

- [ ] **Step 4: Smoke test in dev server**

```bash
cd frontend && npm run dev
```

Visit `/quests?tab=rituals` (the Habits route). Click "+ New ritual". Confirm:
- All fields render with their labels
- Filling in values still saves correctly
- Layout matches the previous version (compare before/after screenshots)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Habits.jsx
git commit -m "Migrate HabitFormModal to TextField/SelectField primitives"
```

---

## Task 5: Migrate the remaining 29 files

**Files:** every file from the "Modified" list above except `Habits.jsx`.

The pattern is mechanical: same import swap, same field replacements. Process one file per commit so reviewers can step through. After each file:

```bash
cd frontend && npm run lint -- --max-warnings 0 && npx vitest run <related-test-file>
```

- [ ] **Step 1: Migrate `frontend/src/pages/Chores.jsx`**

Same import swap. Each `<input>`/`<select>` with `inputClass` becomes the corresponding primitive. Run page tests, commit.

- [ ] **Step 2: Migrate the four `pages/achievements/*FormModal.jsx`**

Process one at a time: BadgeFormModal → SkillFormModal → SubjectFormModal → CategoryFormModal. Each has its own `*.test.jsx` — run after migration.

- [ ] **Step 3: Migrate the three `pages/rewards/*Modal.jsx`**

RewardFormModal → CoinExchangeModal → CoinAdjustModal. RewardFormModal has a test file; the other two should still smoke-test cleanly.

- [ ] **Step 4: Migrate the five `pages/project/modals/*.jsx`**

AddResourceModal → AddMaterialModal → AddMilestoneModal → AddStepModal → EditProjectModal.

- [ ] **Step 5: Migrate the five `pages/ingest/*.jsx`**

SourceStep → MilestonesEditor → StepsEditor → ResourcesEditor → ProjectOverridesCard.

- [ ] **Step 6: Migrate the remaining pages**

Homework.jsx, Manage.jsx, Login.jsx, Payments.jsx, Portfolio.jsx, Stable.jsx, ClockPage.jsx, ProjectNew.jsx, __design.jsx (one per commit). Plus the two component files: HomeworkSubmitSheet.jsx and layout/QuickActionsSheet.jsx.

- [ ] **Step 7: Verify nothing imports `inputClass` for an `<input>` anymore**

Run:

```bash
cd frontend
grep -rn "className={inputClass}" src/
```

Expected: 0 hits. If any remain, those are call sites where the primitive doesn't fit (e.g. an `<input type="file">` styled with inputClass — leave those, but justify in a code comment).

- [ ] **Step 8: Run the full gate**

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected: all green; coverage thresholds met; build succeeds.

---

## Task 6: Migrate hand-rolled empty states

**Files:**
- Modify: `frontend/src/components/dashboard/ApprovalQueueList.jsx:114` (known)
- Modify: `frontend/src/pages/Stable.jsx`, `frontend/src/pages/Timecards.jsx` (known)
- Modify: 3 more discovered via grep

- [ ] **Step 1: Find every hand-rolled empty state**

Run:

```bash
cd frontend
grep -rn "No \(chores\|homework\|projects\|approvals\|entries\|items\|rewards\|quests\|habits\|materials\)" src/ --include="*.jsx" \
  | grep -v "EmptyState"
```

This catches divs that say "No X yet" without using `<EmptyState>`. Manually scan the 6+ hits and confirm they're empty-state UI (not e.g. error toasts or stub text).

- [ ] **Step 2: Migrate each one**

Pattern — replace:

```jsx
<div className="text-center py-8 text-ink-secondary italic">
  No pending approvals.
</div>
```

with:

```jsx
import EmptyState from '../EmptyState';   // adjust path
// ...
<EmptyState>No pending approvals.</EmptyState>
```

If the original includes an icon, pass it via the `icon` prop:

```jsx
<EmptyState icon={<Inbox size={32} />}>No pending approvals.</EmptyState>
```

Commit one file per migration.

- [ ] **Step 3: Verify the count is zero**

Re-run the grep from Step 1. Expected: 0 hits.

- [ ] **Step 4: Run the gate one more time**

```bash
cd frontend && npm run lint && npm run test:run && npm run build
```

Expected: clean.

---

## Verification

End-to-end smoke:

```bash
cd frontend && npm run dev
```

Visit and exercise every form-bearing modal:

| Page | Trigger | What to verify |
|---|---|---|
| `/quests?tab=rituals` | + New ritual | every field labeled and saves |
| `/quests?tab=duties` | + New chore | as above |
| `/homework` | + Add homework | as above |
| `/manage` → Children | edit hourly rate | as above |
| `/manage` → Categories | + New category | as above |
| `/manage` → Subjects, Skills, Badges | each form | as above |
| `/rewards` | + New reward (parent) | as above (multipart upload still works) |
| `/rewards` | Exchange (child) | as above |
| `/projects/<id>` | edit project, add material/milestone/step/resource | as above |
| `/login` | login flow | username + password fields render correctly |

Then visit pages that previously showed hand-rolled empty states (`/manage` with no subjects, `/timecards` with none, `/stable` with no pets, `/dashboard` with no approvals) and confirm the new `<EmptyState>` looks right.

Run the test gate:

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Coverage should rise (3 new tested primitives). Field-level a11y now includes `aria-invalid` and `aria-describedby` wherever the consumer passes `error` / `helpText` — DevTools accessibility tree will show the bound text on focus.
