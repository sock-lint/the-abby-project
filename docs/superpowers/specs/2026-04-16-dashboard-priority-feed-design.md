# Dashboard Priority Feed — Design Spec

**Date:** 2026-04-16
**Status:** Approved
**Topic:** Unified "next actions" feed for the child dashboard hero card and quest log

## Context

Today the child dashboard's `HeroPrimaryCard` picks what to show using a simple priority chain: `clocked → streak-risk → next-chore → quest-progress → idle`. The `next-chore` step takes the first `!is_done` entry from `chores_today`, but `ChoreService.get_available_chores` returns every available chore — including **weekly** chores, which stay "available" every single day Mon→Sun until completed that week. Result: a weekly "Clean Room" chore becomes the hero's "NEXT UP" on a Thursday, beating out two homework assignments due tomorrow. The hero doesn't even consider homework.

Beneath the hero, the quest log groups items by kind (Study / Duty / Ritual) but each section uses its own ad-hoc ordering (homework: overdue→today→upcoming; chores: first available). Cross-section ordering by urgency doesn't exist.

**Goal:** compute a single ranked list of actionable items on the backend, and drive both the hero card and the quest log from it. Scoring lives in one module so "why is X above Y" is testable instead of emergent.

## Architecture

New backend module `apps/projects/priority.py` — a pure-Python scorer with no new Django app. Lives alongside `apps/projects/views.py` where `DashboardView` already returns the dashboard payload.

```
apps/projects/
  priority.py                          NEW — scoring + aggregation
  tests/
    test_priority_unit.py              NEW — scoring math + filter rules (mocks DB helpers)
    test_priority_integration.py       NEW — end-to-end against real DB fixtures
  views.py                             MODIFIED — DashboardView calls priority.build_next_actions(user)
```

Public surface:

```python
def build_next_actions(user, *, target_date=None, hour=None, limit=20) -> list[NextAction]:
    """Return scored, ranked actionable items for the given user."""
```

Internals are private contributor functions (`_chore_actions`, `_homework_actions`, `_habit_actions`) — each ~20 lines, each only used here. `build_next_actions` is a thin orchestrator: gather → score → sort → trim. Parents always get `[]` — the parent hero (approval-queue count) is orthogonal and stays as-is.

---

## Section 1: Scope & Data Model

### Scope — which sources contribute

Only deadline-driven or time-locked items compete for the feed:

- **Chores** — daily, weekly, one-time
- **Homework** — scored by due-date distance
- **Streak-protecting habits** — one habit, only after 6pm, only when a streak is in play

Explicitly **out of scope** for v1:
- Active timer (`clocked`) stays as its own hero variant above the feed
- Active quest stays as its own hero variant below the feed
- Untapped habits without streak risk, quest progress nudges, savings-goal prompts

Rationale: open-ended items (habits without streak, quests) have no deadline, so giving them a competing score always feels arbitrary. The hero's job is "the most important deadline-locked thing." Keeping `clocked` and `quest-progress` as dedicated variants preserves their special visual treatment without forcing them through scoring.

### `NextAction` shape

```python
@dataclass
class NextAction:
    kind: str              # "homework" | "chore" | "habit"
    id: int                # source-row PK
    title: str             # "Math workbook" / "Clean room" / "Brush teeth"
    subtitle: str          # "due tomorrow" / "duty · $1" / "keep your 12-day streak"
    score: int             # final urgency score
    due_at: date | None    # for client-side relative formatting
    reward: dict | None    # {"money": "1.00", "coins": 2} or None
    icon: str              # lucide-react icon name
    tone: str              # "royal" | "moss" | "ember" — drives accent color
    action_url: str        # "/homework" | "/chores" — fallback nav target
```

Each contributor chooses `icon` and `tone` appropriate to its kind so the frontend has no per-kind visual branching — one generic renderer consumes `{icon, tone, title, subtitle}`.

---

## Section 2: Scoring Formula

All weights live in a single `SCORING_WEIGHTS` dict at module top — tunable in one place without surgery.

| Signal | Score | Notes |
|---|---|---|
| Overdue homework | `100 + 10·days_late` | Hard cap at 200 |
| Homework due today | `90` | |
| Daily chore not done | `70` | Resets at midnight |
| Streak-protecting habit | `65` | Only when hour ≥ 18 AND streak ≥ 1 AND untapped today |
| Homework due tomorrow | `60` | |
| One-time chore | `50 + 2·days_since_assigned` | Climbs slowly |
| Homework due this week (not tomorrow) | `30` | |
| Weekly chore | `10 + 8·days_since_monday` | Mon=10, Thu=34, Sat=50, Sun=58 |

```python
SCORING_WEIGHTS = {
    "homework_overdue_base": 100,
    "homework_overdue_per_day": 10,
    "homework_overdue_cap": 200,
    "homework_due_today": 90,
    "homework_due_tomorrow": 60,
    "homework_due_this_week": 30,
    "chore_daily": 70,
    "chore_one_time_base": 50,
    "chore_one_time_per_day": 2,
    "chore_weekly_base": 10,
    "chore_weekly_per_day": 8,
    "habit_streak_protection": 65,
}
```

### Filtering rules

- **Submitted-but-not-yet-approved homework** is excluded — there's nothing for the kid to *do*.
- **Done daily chores** excluded for the rest of the day; **done weekly chores** excluded for the rest of the week.
- **Already-tapped habits** excluded.
- Streak-protecting habit only appears when `character.login_streak ≥ 1 AND hour ≥ 18 AND user has ≥1 untapped positive habit today`. In v1 we surface at most one habit — if multiple qualify, pick the one with the highest per-habit `strength` (breaks ties by alphabetical title). Multiple would clutter the feed.
- The `hour` threshold is interpreted in `America/Phoenix` local time (matches Django's `TIME_ZONE` setting). Passed explicitly into `build_next_actions` so tests can pin it.
- "Homework due this week (not tomorrow)" means due date falls within the next 7 days (exclusive of today, exclusive of tomorrow, inclusive of day+2 through day+7). Past the 7-day horizon, homework is not scored at all.
- "One-time chore days_since_assigned" uses `chore.created_at.date()` as the reference point.

### Tie-breaking

When scores match, deterministic order: higher reward → newer due date → alphabetical title. Deterministic so tests can pin exact ordering.

### Walkthrough (sanity check)

With the screenshot from 2026-04-16 (Thursday):

- Overdue "wb-2" reading — already submitted, filtered out
- Two "workbook" math due tomorrow — score `60` each
- Dishes (daily) — already done, filtered out
- Clean Room (weekly) — Thursday is day 3, score `10 + 3·8 = 34`

Top item: one of the workbook assignments at score 60, Clean Room drops to third. Matches the intuition ("homework due tomorrow is more pressing than a weekly chore that can be done any day").

---

## Section 3: API & Frontend Integration

### API shape (additive)

`GET /api/dashboard/` gains one new top-level field. All existing fields stay — per-source arrays (`chores_today`, `homework.dashboard`, `rpg.habits_today`, `active_timer`) continue to power `HeaderStatusPips`, `HomeworkSubmitSheet`, `QuickActionsFab`, etc. Cleanup of duplicated fields is deferred to a follow-up PR.

```json
{
  "role": "child",
  "active_timer": { ... },
  "chores_today": [ ... ],
  "homework": { "dashboard": ... },
  "rpg": { ... },
  "next_actions": [
    {"kind": "homework", "id": 42, "title": "Math workbook",
     "subtitle": "due tomorrow", "score": 60, "due_at": "2026-04-17",
     "reward": null, "icon": "BookOpen", "tone": "royal",
     "action_url": "/homework"},
    {"kind": "chore", "id": 7, "title": "Clean Room",
     "subtitle": "duty · $1.00", "score": 34, "due_at": null,
     "reward": {"money": "1.00", "coins": 2}, "icon": "Sparkles",
     "tone": "moss", "action_url": "/chores"}
  ]
}
```

For parents `next_actions` is always `[]` — the existing parent hero code path (approval-queue count) is untouched.

### `HeroPrimaryCard.jsx` — 5 variants become 4

| Variant | Condition | Notes |
|---|---|---|
| `clocked` | `active_timer` present | unchanged |
| `next-action` | `next_actions[0]` present | NEW — replaces both `streak-risk` and `next-chore` |
| `quest-progress` | active quest present | unchanged |
| `idle` | nothing | unchanged |

The `next-action` variant is one generic renderer consuming `{title, subtitle, icon, tone, action_url}` — no per-kind visual branching. The "Complete" button action is kind-dependent via a small switch:

- `kind=homework` → opens `HomeworkSubmitSheet(id)`
- `kind=chore` → calls `onCompleteChore(id)`
- `kind=habit` → calls `onTapHabit(id)`

### `ChildDashboard.jsx` quest log

Current behavior: builds rows from `homework.dashboard.{overdue,today,upcoming}` + `chores_today` + `rpg.habits_today` with hand-rolled ordering per section.

New behavior:
1. Group items from `next_actions` by `kind` into Study / Duty / Ritual buckets.
2. Render each bucket in `next_actions` order (which is already score-sorted).
3. Sections with zero items hide their header entirely.

The existing `nextDueTarget()` logic in `_dashboardShared.js` (computing "next school day" client-side) is **removed** — the backend scorer now handles "due today vs. tomorrow vs. this week" with server timezone (`America/Phoenix`). One source of truth for date math.

### Unchanged components

`HeaderStatusPips`, `QuickActionsFab`, `HomeworkSubmitSheet` continue to read the existing per-source arrays. No migration of those consumers in this PR.

---

## Section 4: Testing

### Backend

**`apps/projects/tests/test_priority_unit.py`** — unit tests via `unittest.TestCase` + `unittest.mock.patch`:

Scoring-math tests using lightweight stand-in objects (no DB queries — DB-touching helpers are patched out). Examples:

- Homework 3 days overdue → `130`
- Homework 20 days overdue → `200` (cap holds)
- Weekly chore Monday → `10`; Thursday → `34`; Sunday → `58`
- Streak-protecting habit at 5pm → not included (hour < 18)
- Streak-protecting habit at 7pm, streak=0 → not included (streak < 1)
- Streak-protecting habit at 7pm, streak=1, untapped → score `65`
- Submitted-but-unapproved homework → not included
- Done daily chore → not included
- Tie-breaking: two chores at score 34, one with reward → reward wins
- Parent user → returns `[]`

**`apps/projects/tests/test_priority_integration.py`** — integration test, real DB via Django's `TestCase`:

One end-to-end scenario:
- Seed: 1 child, 2 homework (1 overdue, 1 due tomorrow), 2 chores (daily already done, weekly not done), 1 habit (untapped, streak=5), 1 submitted-but-pending homework submission.
- Call `build_next_actions(child, target_date=..., hour=19)`.
- Assert returned list is exactly `[overdue_homework, due_tomorrow_homework, weekly_chore_thursday, streak_habit]` with exact scores.
- Assert submitted homework + done daily chore absent from result.

**Endpoint test** — added to existing `DashboardView` test file:

- `GET /api/dashboard/` for a child returns `next_actions` field
- Shape of each item matches the `NextAction` serialization contract
- Parent receives `next_actions: []`

### Frontend

- **`HeroPrimaryCard.test.jsx`** — tests for the new `next-action` variant: renders title/subtitle/icon, clicking the button fires the right callback per kind. Use `spyHandler` pattern from `frontend/src/test/spy.js`.
- **`ChildDashboard.test.jsx`** — update fixtures to include `next_actions`, verify quest log groups + re-orders match. The existing "homework row opens submit sheet" test is re-worked to use the new data path.
- **`Dashboard.test.jsx`** — smoke test that `next_actions` is threaded through the role-router into `ChildDashboard`.
- **`frontend/src/test/handlers.js`** — default `/api/dashboard/` mock returns `next_actions: []` so existing tests don't break.

Coverage gate stays at 65/55/55/65 — new code is small enough that incidental misses won't breach the threshold.

---

## Out of Scope

- Removing duplicated per-source fields from the dashboard payload (`chores_today`, `homework.dashboard`, etc.) — follow-up PR once we're confident nothing else reads them.
- Expanding the feed to include habits without streak risk, quest progress, savings-goal prompts, badges close to earning — explicitly deferred.
- User-configurable scoring weights — weights are constants; tuning happens by code change + deploy.
- Push notifications driven by `next_actions[0]` — possible future consumer, but not in this spec.
- Replacing the parent hero variant (approval queue) with a scored feed — parent flow is different and stays as-is.

## Open Questions

None at spec time. All Q1–Q4 settled in brainstorming.
