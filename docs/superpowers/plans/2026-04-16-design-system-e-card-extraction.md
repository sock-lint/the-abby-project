# Design System E: Inline Card Extraction + Promotion Convention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the four `*Card` components currently defined inline within long page files into sibling files inside their existing page subfolder. Document the promotion rule ("co-located until reused twice; then promote to `components/cards/`") so future drift has a reference. **Not** promoting any card to `components/` yet — none of the four current candidates is reused outside its parent page.

**Architecture:** Pure refactor. Each extraction moves a `function FooCard(...)` definition out of its 400+ line parent file into `pages/<area>/FooCard.jsx`, plus its colocated `FooCard.test.jsx` if behavior is non-trivial. The parent file imports it back. No prop changes, no behavior changes.

**Tech Stack:** React 19, Vitest 4. No new dependencies.

---

## File Structure

### New (4 files, 4 colocated tests)
- `frontend/src/pages/Homework/AssignmentCard.jsx` *(new subfolder)*
- `frontend/src/pages/Homework/AssignmentCard.test.jsx`
- `frontend/src/pages/manage/CatalogCard.jsx`
- `frontend/src/pages/manage/CatalogCard.test.jsx`
- `frontend/src/pages/achievements/SkillCard.jsx`
- `frontend/src/pages/achievements/SkillCard.test.jsx`
- `frontend/src/pages/rewards/RewardCard.jsx`
- `frontend/src/pages/rewards/RewardCard.test.jsx`

### Modified
- `frontend/src/pages/Homework.jsx` — remove `function AssignmentCard` (line ~389); import from sibling
- `frontend/src/pages/manage/CodexSection.jsx` — remove `function CatalogCard` (line ~54); import from sibling
- `frontend/src/pages/achievements/SkillTreeView.jsx` — remove `function SkillCard` (line ~14); import from sibling
- `frontend/src/pages/rewards/RewardShop.jsx` — remove `function RewardCard` (line ~6); import from sibling
- `frontend/src/components/README.md` — add the promotion convention (Plan A creates this file; if Plan A hasn't shipped, create the README here with just the convention)

### Deferred (not extracted)
- `pages/rewards/CoinBalanceCard.jsx` — already in its own file; one importer (`pages/Rewards.jsx`). Stay.
- `pages/ingest/ProjectOverridesCard.jsx` — already in its own file; one importer (`pages/ingest/ReviewStep.jsx`). Stay.
- `pages/project/ProjectPlanItems.jsx` `StepCard` — already exported; one importer (`pages/project/PlanTab.jsx`). Stay (the export sits alongside `ResourcePill` in a tightly coupled file).

---

## Task 1: Extract `AssignmentCard` from `pages/Homework.jsx`

**Files:**
- Modify: `frontend/src/pages/Homework.jsx`
- Create: `frontend/src/pages/Homework/AssignmentCard.jsx`
- Create: `frontend/src/pages/Homework/AssignmentCard.test.jsx`

**Note on the new subfolder:** `Homework.jsx` currently sits directly under `pages/`. Creating `pages/Homework/AssignmentCard.jsx` requires moving `Homework.jsx` to `pages/Homework/index.jsx` to keep the existing route working. **Confirm with the user** whether to do that route-shape change in this task or extract to a flat sibling like `pages/HomeworkAssignmentCard.jsx`. The plan below assumes the cleaner subfolder layout.

- [ ] **Step 1: Read the current AssignmentCard definition**

Read `frontend/src/pages/Homework.jsx` lines 389–end (or wherever `function AssignmentCard` ends). Note its props, what it imports from the parent file (constants, helpers, formatters), and whether anything inside it references the parent's local state.

- [ ] **Step 2: Write a failing test for the extracted component**

Create `frontend/src/pages/Homework/AssignmentCard.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AssignmentCard from './AssignmentCard.jsx';
import { buildHomework } from '../../test/factories.js';   // add a builder if missing

describe('AssignmentCard', () => {
  it('renders the assignment title and subject', () => {
    const a = buildHomework({ title: 'Read Chapter 3', subject_label: 'English' });
    render(<AssignmentCard assignment={a} onSubmit={() => {}} onPlan={() => {}} planning={false} canPlan={false} />);
    expect(screen.getByText('Read Chapter 3')).toBeInTheDocument();
    expect(screen.getByText(/English/i)).toBeInTheDocument();
  });

  it('calls onSubmit when the submit affordance is clicked', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const a = buildHomework({ status: 'open' });
    render(<AssignmentCard assignment={a} onSubmit={onSubmit} onPlan={() => {}} planning={false} canPlan={false} />);
    await user.click(screen.getByRole('button', { name: /submit/i }));
    expect(onSubmit).toHaveBeenCalledWith(a);
  });
});
```

If `buildHomework` doesn't exist in [`frontend/src/test/factories.js`](../../../frontend/src/test/factories.js), add it now (look at how `buildChore` is structured and mirror).

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/Homework/AssignmentCard.test.jsx`
Expected: fail (file doesn't exist).

- [ ] **Step 4: Move `Homework.jsx` to `Homework/index.jsx`**

```bash
mkdir frontend/src/pages/Homework
git mv frontend/src/pages/Homework.jsx frontend/src/pages/Homework/index.jsx
```

(If a `Homework.test.jsx` exists, also rename to `pages/Homework/index.test.jsx`.) Verify the existing route still resolves — open `frontend/src/App.jsx` and confirm the import for the page still works (it should, since `import Homework from './pages/Homework'` resolves to `index.jsx` automatically).

- [ ] **Step 5: Create `AssignmentCard.jsx` from the extracted definition**

Cut the entire `function AssignmentCard(...)` block from `pages/Homework/index.jsx`. Paste it into `frontend/src/pages/Homework/AssignmentCard.jsx`. At the top of the new file, add:

- All `import` statements the function needs (icons from `lucide-react`, helpers from `../../utils/format`, constants, etc. — copy each from the original parent file).
- `export default function AssignmentCard(...)` (turn the local `function` into the default export).

Back in `pages/Homework/index.jsx`, replace the deleted block with:

```jsx
import AssignmentCard from './AssignmentCard.jsx';
```

- [ ] **Step 6: Verify the rendered Homework page is unchanged**

Run: `cd frontend && npx vitest run src/pages/Homework/`
Expected: existing Homework tests pass; new AssignmentCard test passes.

```bash
cd frontend && npm run dev
```

Visit `/homework` in both child and parent contexts. Confirm assignments render exactly as before.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Homework
git commit -m "Extract AssignmentCard from Homework.jsx"
```

---

## Task 2: Extract `CatalogCard` from `pages/manage/CodexSection.jsx`

**Files:**
- Modify: `frontend/src/pages/manage/CodexSection.jsx`
- Create: `frontend/src/pages/manage/CatalogCard.jsx`
- Create: `frontend/src/pages/manage/CatalogCard.test.jsx`

`pages/manage/` already exists — no folder reshuffle needed.

- [ ] **Step 1: Write a failing test**

Create `frontend/src/pages/manage/CatalogCard.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CatalogCard from './CatalogCard.jsx';

describe('CatalogCard', () => {
  it('renders the name, subtitle, and rarity-tinted ring', () => {
    render(
      <CatalogCard rarity="legendary" icon="🐉" spriteKey={null} name="Wyvern" subtitle="Mount" onClick={() => {}} />,
    );
    expect(screen.getByText('Wyvern')).toBeInTheDocument();
    expect(screen.getByText('Mount')).toBeInTheDocument();
  });

  it('fires onClick when clicked', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<CatalogCard rarity="common" icon="🐾" name="Pup" subtitle="Pet" onClick={onClick} />);
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/manage/CatalogCard.test.jsx`
Expected: fail.

- [ ] **Step 3: Extract the function**

Cut `function CatalogCard(...)` (line ~54) from `pages/manage/CodexSection.jsx`. Paste into `frontend/src/pages/manage/CatalogCard.jsx`. Add the imports it needs (rarity colors from `../../constants/colors`, RpgSprite if used, etc.). Use `export default`.

In `CodexSection.jsx`, replace the deleted block with:

```jsx
import CatalogCard from './CatalogCard.jsx';
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run src/pages/manage/`
Expected: all pass.

- [ ] **Step 5: Smoke test**

```bash
cd frontend && npm run dev
```

Visit `/manage` → Codex tab. Confirm catalog cards still render and click into the right detail.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/manage/
git commit -m "Extract CatalogCard from CodexSection.jsx"
```

---

## Task 3: Extract `SkillCard` from `pages/achievements/SkillTreeView.jsx`

**Files:**
- Modify: `frontend/src/pages/achievements/SkillTreeView.jsx`
- Create: `frontend/src/pages/achievements/SkillCard.jsx`
- Create: `frontend/src/pages/achievements/SkillCard.test.jsx`

- [ ] **Step 1: Write a failing test**

Create `frontend/src/pages/achievements/SkillCard.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillCard from './SkillCard.jsx';

describe('SkillCard', () => {
  it('renders the skill name and level', () => {
    const skill = { id: 1, name: 'Soldering', level: 3, max_level: 10, xp_current: 40, xp_to_next: 100 };
    render(<SkillCard skill={skill} index={0} onSelect={() => {}} />);
    expect(screen.getByText('Soldering')).toBeInTheDocument();
    expect(screen.getByText(/Level 3/i)).toBeInTheDocument();
  });

  it('calls onSelect when activated', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const skill = { id: 1, name: 'x', level: 1, max_level: 10, xp_current: 0, xp_to_next: 100 };
    render(<SkillCard skill={skill} index={0} onSelect={onSelect} />);
    await user.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledWith(skill);
  });
});
```

(Adjust the skill shape to match what the actual function reads — refer to the original definition.)

- [ ] **Step 2: Run the test to verify it fails**

- [ ] **Step 3: Extract the function**

Cut `function SkillCard(...)` (line ~14) from `pages/achievements/SkillTreeView.jsx`. Paste into `frontend/src/pages/achievements/SkillCard.jsx` with required imports and `export default`.

In `SkillTreeView.jsx`, replace with:

```jsx
import SkillCard from './SkillCard.jsx';
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/achievements/
```

- [ ] **Step 5: Smoke test**

Visit `/achievements`. Confirm skill cards render and click into skill detail.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/achievements/
git commit -m "Extract SkillCard from SkillTreeView.jsx"
```

---

## Task 4: Extract `RewardCard` from `pages/rewards/RewardShop.jsx`

**Files:**
- Modify: `frontend/src/pages/rewards/RewardShop.jsx`
- Create: `frontend/src/pages/rewards/RewardCard.jsx`
- Create: `frontend/src/pages/rewards/RewardCard.test.jsx`

- [ ] **Step 1: Write a failing test**

Create `frontend/src/pages/rewards/RewardCard.test.jsx`:

```jsx
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardCard from './RewardCard.jsx';

describe('RewardCard', () => {
  const reward = { id: 1, name: 'Ice cream', cost_coins: 50, rarity: 'common', stock: 5, is_active: true };

  it('shows the name and cost', () => {
    render(<RewardCard reward={reward} isParent={false} coinBalance={100} onRedeem={() => {}} />);
    expect(screen.getByText('Ice cream')).toBeInTheDocument();
    expect(screen.getByText(/50/)).toBeInTheDocument();
  });

  it('calls onRedeem when child can afford it', async () => {
    const user = userEvent.setup();
    const onRedeem = vi.fn();
    render(<RewardCard reward={reward} isParent={false} coinBalance={100} onRedeem={onRedeem} />);
    await user.click(screen.getByRole('button', { name: /redeem|claim/i }));
    expect(onRedeem).toHaveBeenCalledWith(reward);
  });

  it('shows edit + delete affordances when isParent', async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(<RewardCard reward={reward} isParent={true} coinBalance={0} onRedeem={() => {}} onEdit={onEdit} onDelete={onDelete} />);
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

- [ ] **Step 3: Extract the function**

Cut `function RewardCard(...)` (line ~6) from `pages/rewards/RewardShop.jsx`. Paste into `frontend/src/pages/rewards/RewardCard.jsx` with imports and `export default`.

In `RewardShop.jsx`:

```jsx
import RewardCard from './RewardCard.jsx';
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/rewards/
```

- [ ] **Step 5: Smoke test**

Visit `/rewards` as a child (redeem affordance) and as a parent (edit + delete affordances). Confirm both renders match the prior version.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/rewards/
git commit -m "Extract RewardCard from RewardShop.jsx"
```

---

## Task 5: Document the promotion convention

**Files:**
- Modify (or create): `frontend/src/components/README.md`

If Plan A has shipped, the README already exists and has a "File layout" section — append the convention there. If Plan A has not shipped, create the file with just this section.

- [ ] **Step 1: Add the convention**

Open `frontend/src/components/README.md`. In the "File layout" section, ensure the following passage is present:

```markdown
### Card placement rule

A page-specific card component (`*Card`) starts as a sibling file inside its
owning page directory:

- `pages/Homework/AssignmentCard.jsx` — used only by `pages/Homework/index.jsx`
- `pages/manage/CatalogCard.jsx` — used only by `pages/manage/CodexSection.jsx`

It gets promoted to `components/cards/` only when a **second** page imports it.
Until then, co-location wins: the card lives next to its only consumer, the
parent file stays under ~400 lines, and the import line documents ownership.

Do not pre-emptively promote a card that has only one importer. The cost of
moving is small; the cost of premature abstraction is real.
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/README.md
git commit -m "Document card promotion convention"
```

---

## Verification

Run the full gate:

```bash
cd frontend && npm run lint && npm run test:coverage && npm run build
```

Expected:
- 4 new test files passing
- Coverage thresholds met
- Build succeeds

Confirm the parent files shrunk:

```bash
cd frontend
wc -l src/pages/Homework/index.jsx src/pages/manage/CodexSection.jsx \
      src/pages/achievements/SkillTreeView.jsx src/pages/rewards/RewardShop.jsx
```

Each should be measurably shorter than before (delta ≈ size of the extracted card body, typically 30–80 lines).

Smoke test the affected pages:

```bash
cd frontend && npm run dev
```

- `/homework` (child + parent views) — assignment cards render and submit/plan affordances work
- `/manage` → Codex tab — catalog cards render and click through
- `/achievements` — skill cards render with progress bars
- `/rewards` (child + parent views) — reward cards render with the right affordances

Take one screenshot per page for the PR.

Run a final inventory check — confirm the four cards are now the *only* extracted files in their folders:

```bash
ls frontend/src/pages/Homework
ls frontend/src/pages/manage
ls frontend/src/pages/achievements
ls frontend/src/pages/rewards
```

Future cards should follow the same pattern.
