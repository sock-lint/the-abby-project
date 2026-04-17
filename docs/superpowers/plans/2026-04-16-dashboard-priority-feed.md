# Dashboard Priority Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the child dashboard's ad-hoc priority chain with a unified, scored "next actions" feed that drives the hero card and the quest log, so the most urgent deadline-locked thing surfaces first.

**Architecture:** New Python module `apps/projects/priority.py` exposes `build_next_actions(user, *, target_date, hour, limit)` which gathers chore + homework + streak-protecting-habit candidates, scores them via a central `SCORING_WEIGHTS` dict, sorts descending with deterministic tie-breaking, and returns a list of `NextAction` dataclass instances. `DashboardView` adds a new top-level `next_actions` field to its JSON response. Existing per-source arrays (`chores_today`, `homework.dashboard`, `rpg.habits_today`) stay on the wire for other consumers. Frontend collapses `HeroPrimaryCard`'s 5 variants to 4 (one generic `next-action` renderer replaces `streak-risk` + `next-chore`), and `ChildDashboard`'s quest log builds from `next_actions` grouped by kind while keeping Study / Duty / Ritual section headers.

**Tech Stack:** Python 3.12, Django 5.1, DRF 3.15, dataclasses, `unittest.TestCase` + `unittest.mock.patch` via `python manage.py test` (this project does NOT use pytest). Frontend: React 19, Vitest 4, React Testing Library, MSW 2.

**Reference spec:** [docs/superpowers/specs/2026-04-16-dashboard-priority-feed-design.md](../specs/2026-04-16-dashboard-priority-feed-design.md)

---

## File Structure

### Create

- `apps/projects/priority.py` — `NextAction` dataclass, `SCORING_WEIGHTS` dict, per-source contributor functions, `build_next_actions` orchestrator
- `apps/projects/tests/test_priority_unit.py` — scoring math + filter rules using `unittest.TestCase` + `unittest.mock.patch` (DB helpers patched out)
- `apps/projects/tests/test_priority_integration.py` — end-to-end using Django's `TestCase` against real DB fixtures
- `apps/projects/tests/test_dashboard_view.py` — endpoint test for `GET /api/dashboard/` including `next_actions` shape
- `frontend/src/components/dashboard/HeroPrimaryCard.test.jsx` — colocated tests for the new `next-action` variant

### Modify

- `apps/projects/views.py` — `DashboardView.get` calls `priority.build_next_actions(user)` and includes serialized result in response payload
- `frontend/src/components/dashboard/HeroPrimaryCard.jsx` — replace `streak-risk` and `next-chore` branches with a single `next-action` branch that reads `ctx.nextAction`
- `frontend/src/pages/ChildDashboard.jsx` — replace `buildHomeworkEntries` + `buildTodayQuests` internals with one `buildQuestLogFromActions(next_actions)` helper; pass `next_actions[0]` to hero via new `nextAction` context field
- `frontend/src/pages/ChildDashboard.test.jsx` — update fixtures to include `next_actions`; update hero-variant assertions
- `frontend/src/pages/Dashboard.test.jsx` — add smoke test that `next_actions` is threaded through the role router
- `frontend/src/pages/_dashboardShared.js` — remove `nextDueTarget` (date math moves server-side)
- `frontend/src/pages/_dashboardShared.test.js` — remove `nextDueTarget` test cases
- `frontend/src/test/handlers.js` — default `/api/dashboard/` mock returns `next_actions: []`

### Test runner conventions

- All backend tests use `unittest.TestCase` (or Django's `django.test.TestCase` when DB queries are needed) and run via `docker compose exec django python manage.py test <dotted.path>`.
- This project does NOT use pytest. Do NOT use `monkeypatch`, pytest fixtures, or bare-function tests. Use `unittest.mock.patch` (decorator or context manager) for stubbing.
- Test discovery is automatic for files matching `tests/test_*.py` — that's why all tests live under `apps/projects/tests/`.

### Responsibility per file

- `priority.py` — all urgency-scoring logic. Single source of truth for "what should the child do next." Any new source (e.g., savings-goal reminders) adds one contributor function here, not scattered UI changes.
- `tests/test_priority_unit.py` — pure scoring/filter logic with the three contributor I/O boundaries (`_available_chores`, `_eligible_homework`, `_untapped_positive_habits`, `_login_streak`) patched out. Fast, focused, no DB writes.
- `tests/test_priority_integration.py` — confirms the wiring works against real Django models. One end-to-end scenario.
- `HeroPrimaryCard.jsx` — presentation only. No kind-specific rendering logic — the backend already emits `icon` / `tone` / `subtitle` appropriate to each item's kind.
- `ChildDashboard.jsx` — orchestration. Pulls `next_actions` from dashboard payload, feeds to hero + quest log.

---

## Task 1: Priority module scaffold

**Files:**
- Create: `apps/projects/priority.py`
- Create: `apps/projects/tests/test_priority_unit.py`

This task establishes the module skeleton with the dataclass, the weights dict, and an empty orchestrator that returns `[]` for parents. No scoring yet — scoring lands in Tasks 2–4. This exists so every subsequent task has a stable module to import and a TDD target to grow.

- [ ] **Step 1: Write the failing test**

Create `apps/projects/tests/test_priority_unit.py`:

```python
"""Unit tests for apps.projects.priority — pure scoring math + filter rules.

DB-touching helpers (`_available_chores`, `_eligible_homework`,
`_untapped_positive_habits`, `_login_streak`) are patched out so these tests
don't require a populated DB. End-to-end DB coverage lives in
test_priority_integration.py.
"""
import datetime
from types import SimpleNamespace
from unittest import TestCase

from apps.projects.priority import (
    NextAction,
    SCORING_WEIGHTS,
    build_next_actions,
)


def _parent():
    return SimpleNamespace(role="parent", pk=1)


def _child():
    return SimpleNamespace(role="child", pk=2)


class ScaffoldTests(TestCase):
    def test_parent_returns_empty_list(self):
        self.assertEqual(build_next_actions(_parent()), [])

    def test_scoring_weights_dict_has_expected_keys(self):
        required = {
            "homework_overdue_base", "homework_overdue_per_day",
            "homework_overdue_cap", "homework_due_today",
            "homework_due_tomorrow", "homework_due_this_week",
            "chore_daily", "chore_one_time_base",
            "chore_one_time_per_day", "chore_weekly_base",
            "chore_weekly_per_day", "habit_streak_protection",
        }
        self.assertTrue(required <= set(SCORING_WEIGHTS.keys()))

    def test_nextaction_serializes_to_dict_with_iso_date(self):
        action = NextAction(
            kind="homework", id=42, title="Math workbook",
            subtitle="due tomorrow", score=60,
            due_at=datetime.date(2026, 4, 17),
            reward=None, icon="BookOpen", tone="royal",
            action_url="/homework",
        )
        d = action.as_dict()
        self.assertEqual(d["kind"], "homework")
        self.assertEqual(d["id"], 42)
        self.assertEqual(d["due_at"], "2026-04-17")
        self.assertEqual(d["score"], 60)

    def test_nextaction_serializes_none_due_at(self):
        action = NextAction(
            kind="chore", id=7, title="Clean Room", subtitle="duty · $1",
            score=34, due_at=None, reward={"money": "1.00", "coins": 2},
            icon="Sparkles", tone="moss", action_url="/chores",
        )
        self.assertIsNone(action.as_dict()["due_at"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 4 tests FAIL with `ModuleNotFoundError: No module named 'apps.projects.priority'`.

- [ ] **Step 3: Write minimal implementation**

Create `apps/projects/priority.py`:

```python
"""Urgency scoring and next-action aggregation for the child dashboard.

Exports one public function — `build_next_actions(user, *, target_date=None,
hour=None, limit=20)` — which returns a ranked list of `NextAction`
dataclass instances covering chores, homework, and (optionally) a single
streak-protecting habit. Parents always receive `[]` — the parent hero is
driven by the approval queue, not a priority feed.

Scoring weights live in `SCORING_WEIGHTS` at module top so they can be
tuned in one place. See
docs/superpowers/specs/2026-04-16-dashboard-priority-feed-design.md
for the full formula and rationale.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional


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


@dataclass
class NextAction:
    kind: str                              # "homework" | "chore" | "habit"
    id: int                                # source-row PK
    title: str
    subtitle: str
    score: int
    due_at: Optional[datetime.date]
    reward: Optional[dict]                 # {"money": "1.00", "coins": 2} or None
    icon: str                              # lucide-react name
    tone: str                              # "royal" | "moss" | "ember" | etc.
    action_url: str

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "score": self.score,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "reward": self.reward,
            "icon": self.icon,
            "tone": self.tone,
            "action_url": self.action_url,
        }


def build_next_actions(user, *, target_date=None, hour=None, limit=20):
    """Return a ranked list of NextAction instances for the user.

    Args:
        user: Django user instance (must have `.role` attribute).
        target_date: `date` to treat as "today". Defaults to
            `timezone.localdate()` — passed explicitly by tests.
        hour: `int` 0-23 to treat as current hour (for streak-protection
            gating). Defaults to current server-local hour.
        limit: Trim result to at most this many items.

    Returns:
        list[NextAction] sorted by score descending with deterministic
        tie-breaking. Parents always receive `[]`.
    """
    if user.role != "child":
        return []
    return []  # contributors land in Tasks 2–4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/priority.py apps/projects/tests/test_priority_unit.py
git commit -m "feat(priority): add NextAction dataclass + scoring-weights scaffold"
```

---

## Task 2: Chore contributor

**Files:**
- Modify: `apps/projects/priority.py`
- Modify: `apps/projects/tests/test_priority_unit.py`

The chore contributor reuses `ChoreService.get_available_chores(user, target_date)` — which already handles active-flag + alternating-week filtering + the `is_done_today` annotation — and assigns scores based on the `Recurrence` enum. To keep tests fast and DB-free, we expose a thin `_available_chores(user, target_date)` wrapper that tests can patch.

- [ ] **Step 1: Write the failing tests**

Append to `apps/projects/tests/test_priority_unit.py`:

```python
from decimal import Decimal
from unittest.mock import patch

from apps.projects.priority import _chore_actions


def _make_chore(*, pk, title, recurrence, is_done=False, icon="",
                reward=Decimal("0.00"), coins=0, created_at=None):
    """Build a chore-shaped stand-in. The real Chore model has many more
    fields but `_chore_actions` only reads a handful."""
    return SimpleNamespace(
        pk=pk, title=title, icon=icon,
        reward_amount=reward, coin_reward=coins,
        recurrence=recurrence, is_done_today=is_done,
        # `created_at` is normally a datetime — expose `.date()` like Django does.
        created_at=SimpleNamespace(date=lambda cd=created_at: cd),
    )


class ChoreScoringTests(TestCase):
    @patch("apps.projects.priority._available_chores")
    def test_weekly_scores_by_weekday(self, mock_available):
        # Thursday = weekday 3 → 10 + 3·8 = 34
        thursday = datetime.date(2026, 4, 16)
        chore = _make_chore(pk=1, title="Clean Room", recurrence="weekly",
                            reward=Decimal("1.00"), coins=2)
        mock_available.return_value = [chore]
        actions = _chore_actions(_child(), thursday)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].score, 34)
        self.assertEqual(actions[0].kind, "chore")
        self.assertEqual(actions[0].title, "Clean Room")
        self.assertEqual(actions[0].reward, {"money": "1.00", "coins": 2})

    @patch("apps.projects.priority._available_chores")
    def test_weekly_monday_scores_10(self, mock_available):
        monday = datetime.date(2026, 4, 13)
        mock_available.return_value = [
            _make_chore(pk=1, title="X", recurrence="weekly")
        ]
        self.assertEqual(_chore_actions(_child(), monday)[0].score, 10)

    @patch("apps.projects.priority._available_chores")
    def test_weekly_sunday_scores_58(self, mock_available):
        sunday = datetime.date(2026, 4, 19)
        mock_available.return_value = [
            _make_chore(pk=1, title="X", recurrence="weekly")
        ]
        self.assertEqual(_chore_actions(_child(), sunday)[0].score, 58)

    @patch("apps.projects.priority._available_chores")
    def test_daily_scores_70(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Dishes", recurrence="daily")
        ]
        self.assertEqual(_chore_actions(_child(), today)[0].score, 70)

    @patch("apps.projects.priority._available_chores")
    def test_one_time_climbs_over_days(self, mock_available):
        today = datetime.date(2026, 4, 16)
        assigned = datetime.date(2026, 4, 11)  # 5 days ago
        mock_available.return_value = [
            _make_chore(pk=1, title="Organize garage",
                        recurrence="one_time", created_at=assigned)
        ]
        # 50 + 2·5 = 60
        self.assertEqual(_chore_actions(_child(), today)[0].score, 60)

    @patch("apps.projects.priority._available_chores")
    def test_done_today_filtered_out(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Dishes", recurrence="daily", is_done=True)
        ]
        self.assertEqual(_chore_actions(_child(), today), [])

    @patch("apps.projects.priority._available_chores")
    def test_reward_omitted_when_both_zero(self, mock_available):
        today = datetime.date(2026, 4, 16)
        mock_available.return_value = [
            _make_chore(pk=1, title="Free chore", recurrence="daily")
        ]
        self.assertIsNone(_chore_actions(_child(), today)[0].reward)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: the 7 new tests FAIL with `ImportError: cannot import name '_chore_actions'`.

- [ ] **Step 3: Implement the chore contributor**

Append to `apps/projects/priority.py`:

```python
def _available_chores(user, target_date):
    """Thin wrapper around ChoreService.get_available_chores — extracted so
    tests can patch it without pulling in a full DB fixture."""
    from apps.chores.services import ChoreService
    return list(ChoreService.get_available_chores(user, target_date))


def _chore_reward(chore):
    if not chore.reward_amount and not chore.coin_reward:
        return None
    return {
        "money": str(chore.reward_amount),
        "coins": int(chore.coin_reward),
    }


def _chore_subtitle(chore):
    if chore.reward_amount and chore.coin_reward:
        return f"duty · ${chore.reward_amount} · {chore.coin_reward} coins"
    if chore.reward_amount:
        return f"duty · ${chore.reward_amount}"
    if chore.coin_reward:
        return f"duty · {chore.coin_reward} coins"
    return "duty"


def _chore_score(chore, target_date):
    w = SCORING_WEIGHTS
    if chore.recurrence == "daily":
        return w["chore_daily"]
    if chore.recurrence == "weekly":
        days_since_monday = target_date.weekday()
        return w["chore_weekly_base"] + days_since_monday * w["chore_weekly_per_day"]
    if chore.recurrence == "one_time":
        created = chore.created_at.date() if hasattr(chore.created_at, "date") else chore.created_at
        days_since = max(0, (target_date - created).days)
        return w["chore_one_time_base"] + days_since * w["chore_one_time_per_day"]
    return 0


def _chore_actions(user, target_date):
    actions = []
    for chore in _available_chores(user, target_date):
        if chore.is_done_today:
            continue
        actions.append(NextAction(
            kind="chore",
            id=chore.pk,
            title=chore.title,
            subtitle=_chore_subtitle(chore),
            score=_chore_score(chore, target_date),
            due_at=None,
            reward=_chore_reward(chore),
            icon=chore.icon or "Sparkles",
            tone="moss",
            action_url="/chores",
        ))
    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/priority.py apps/projects/tests/test_priority_unit.py
git commit -m "feat(priority): add chore contributor with weekly/daily/one-time scoring"
```

---

## Task 3: Homework contributor

**Files:**
- Modify: `apps/projects/priority.py`
- Modify: `apps/projects/tests/test_priority_unit.py`

The homework contributor queries `HomeworkAssignment` directly. Filter rule: exclude assignments that have any submission with status `pending` or `approved` (rejected submissions still leave the assignment eligible for resubmit). The DB query is wrapped in `_eligible_homework(user)` for test patchability.

- [ ] **Step 1: Write the failing tests**

Append to `apps/projects/tests/test_priority_unit.py`:

```python
from apps.projects.priority import _homework_actions


def _make_homework(*, pk, title, due_date, subject="math"):
    return SimpleNamespace(
        pk=pk, title=title, due_date=due_date, subject=subject,
        get_subject_display=lambda: subject.title(),
    )


class HomeworkScoringTests(TestCase):
    @patch("apps.projects.priority._eligible_homework")
    def test_overdue_scales_with_days(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Reading",
                           due_date=datetime.date(2026, 4, 13))
        ]
        # 3 days overdue → 100 + 3·10 = 130
        actions = _homework_actions(_child(), today)
        self.assertEqual(actions[0].score, 130)
        self.assertEqual(actions[0].kind, "homework")

    @patch("apps.projects.priority._eligible_homework")
    def test_overdue_caps_at_200(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="R",
                           due_date=datetime.date(2026, 3, 1))
        ]
        # Way more than 10 days late → capped at 200
        self.assertEqual(_homework_actions(_child(), today)[0].score, 200)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_today_scores_90(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [_make_homework(pk=1, title="Math", due_date=today)]
        self.assertEqual(_homework_actions(_child(), today)[0].score, 90)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_tomorrow_scores_60(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 17))
        ]
        self.assertEqual(_homework_actions(_child(), today)[0].score, 60)

    @patch("apps.projects.priority._eligible_homework")
    def test_due_this_week_scores_30(self, mock_hw):
        today = datetime.date(2026, 4, 16)  # Thursday
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 20))
        ]
        # 4 days out, within 7-day horizon, not tomorrow → 30
        self.assertEqual(_homework_actions(_child(), today)[0].score, 30)

    @patch("apps.projects.priority._eligible_homework")
    def test_beyond_7_days_not_scored(self, mock_hw):
        today = datetime.date(2026, 4, 16)
        mock_hw.return_value = [
            _make_homework(pk=1, title="Math",
                           due_date=datetime.date(2026, 4, 30))
        ]
        self.assertEqual(_homework_actions(_child(), today), [])

    @patch("apps.projects.priority._eligible_homework")
    def test_subtitle_formats_due_date_phrase(self, mock_hw):
        today = datetime.date(2026, 4, 16)

        mock_hw.return_value = [
            _make_homework(pk=1, title="A", due_date=datetime.date(2026, 4, 14))
        ]
        self.assertIn("overdue", _homework_actions(_child(), today)[0].subtitle)

        mock_hw.return_value = [_make_homework(pk=2, title="B", due_date=today)]
        self.assertIn("today", _homework_actions(_child(), today)[0].subtitle)

        mock_hw.return_value = [
            _make_homework(pk=3, title="C", due_date=datetime.date(2026, 4, 17))
        ]
        self.assertIn("tomorrow", _homework_actions(_child(), today)[0].subtitle)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: 7 new tests FAIL with `ImportError: cannot import name '_homework_actions'`.

- [ ] **Step 3: Implement the homework contributor**

Append to `apps/projects/priority.py`:

```python
def _eligible_homework(user):
    """Homework assignments the child can still act on.

    Excludes:
    - inactive assignments
    - assignments with any submission in ('pending', 'approved') —
      rejected-only submissions still leave the assignment eligible.
    """
    from apps.homework.models import HomeworkAssignment, HomeworkSubmission
    from django.db.models import Exists, OuterRef

    blocking_submission = HomeworkSubmission.objects.filter(
        assignment=OuterRef("pk"),
        user=user,
    ).exclude(status=HomeworkSubmission.Status.REJECTED)

    return list(
        HomeworkAssignment.objects
        .filter(assigned_to=user, is_active=True)
        .annotate(_has_blocking=Exists(blocking_submission))
        .filter(_has_blocking=False)
    )


def _homework_score(hw, target_date):
    w = SCORING_WEIGHTS
    days_delta = (hw.due_date - target_date).days
    if days_delta < 0:
        score = w["homework_overdue_base"] + (-days_delta) * w["homework_overdue_per_day"]
        return min(score, w["homework_overdue_cap"])
    if days_delta == 0:
        return w["homework_due_today"]
    if days_delta == 1:
        return w["homework_due_tomorrow"]
    if days_delta <= 7:
        return w["homework_due_this_week"]
    return 0  # signal: skip


def _homework_subtitle(hw, target_date):
    days_delta = (hw.due_date - target_date).days
    subject = hw.get_subject_display()
    if days_delta < 0:
        n = -days_delta
        return f"{subject} · {n} day{'s' if n != 1 else ''} overdue"
    if days_delta == 0:
        return f"{subject} · due today"
    if days_delta == 1:
        return f"{subject} · due tomorrow"
    return f"{subject} · due in {days_delta} days"


def _homework_actions(user, target_date):
    actions = []
    for hw in _eligible_homework(user):
        score = _homework_score(hw, target_date)
        if score == 0:
            continue
        actions.append(NextAction(
            kind="homework",
            id=hw.pk,
            title=hw.title,
            subtitle=_homework_subtitle(hw, target_date),
            score=score,
            due_at=hw.due_date,
            reward=None,
            icon="BookOpen",
            tone="royal",
            action_url="/homework",
        ))
    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 18 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/priority.py apps/projects/tests/test_priority_unit.py
git commit -m "feat(priority): add homework contributor with overdue/today/week scoring"
```

---

## Task 4: Streak-protecting habit contributor

**Files:**
- Modify: `apps/projects/priority.py`
- Modify: `apps/projects/tests/test_priority_unit.py`

The habit contributor fires at most once — it surfaces a *single* untapped positive habit only when:
- `character.login_streak >= 1`
- `hour >= 18` (6pm server-local)
- user has at least one untapped positive habit today

Ties between multiple qualifying habits break by `strength` DESC, then `name` ASC.

- [ ] **Step 1: Write the failing tests**

Append to `apps/projects/tests/test_priority_unit.py`:

```python
from apps.projects.priority import _habit_actions


def _make_habit(*, pk, name, strength=0, icon="", max_taps=1, taps_today=0,
                habit_type="positive"):
    return SimpleNamespace(
        pk=pk, name=name, strength=strength, icon=icon,
        habit_type=habit_type, max_taps_per_day=max_taps,
        _taps_today=taps_today,
    )


class HabitStreakProtectionTests(TestCase):
    def _patch(self, habits, streak):
        """Stack two patches as context managers and return their mocks
        for tests that don't need to assert on call args."""
        habits_patch = patch(
            "apps.projects.priority._untapped_positive_habits",
            return_value=list(habits),
        )
        streak_patch = patch(
            "apps.projects.priority._login_streak",
            return_value=streak,
        )
        habits_patch.start()
        streak_patch.start()
        self.addCleanup(habits_patch.stop)
        self.addCleanup(streak_patch.stop)

    def test_no_streak_returns_empty(self):
        self._patch([_make_habit(pk=1, name="Brush", strength=5)], streak=0)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19),
            [],
        )

    def test_early_hour_returns_empty(self):
        self._patch([_make_habit(pk=1, name="Brush", strength=5)], streak=3)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=17),
            [],
        )

    def test_streak_protection_scores_65(self):
        self._patch(
            [_make_habit(pk=1, name="Brush teeth", strength=5, icon="🪥")],
            streak=3,
        )
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].score, 65)
        self.assertEqual(actions[0].kind, "habit")
        self.assertEqual(actions[0].title, "Brush teeth")
        self.assertEqual(actions[0].tone, "ember")

    def test_picks_highest_strength(self):
        self._patch([
            _make_habit(pk=1, name="Aaa", strength=1),
            _make_habit(pk=2, name="Zzz", strength=10),
        ], streak=3)
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].id, 2)  # the high-strength one

    def test_ties_break_alphabetically(self):
        self._patch([
            _make_habit(pk=1, name="Zebra", strength=5),
            _make_habit(pk=2, name="Apple", strength=5),
        ], streak=3)
        actions = _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19)
        self.assertEqual(actions[0].title, "Apple")

    def test_empty_list_returns_empty(self):
        self._patch([], streak=3)
        self.assertEqual(
            _habit_actions(_child(), datetime.date(2026, 4, 16), hour=19),
            [],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: 6 new tests FAIL with `ImportError: cannot import name '_habit_actions'`.

- [ ] **Step 3: Implement the habit contributor**

Append to `apps/projects/priority.py`:

```python
def _login_streak(user):
    from apps.rpg.models import CharacterProfile
    try:
        return CharacterProfile.objects.get(user=user).login_streak
    except CharacterProfile.DoesNotExist:
        return 0


def _untapped_positive_habits(user, target_date):
    """Positive (or both) habits with taps_today < max_taps_per_day."""
    from apps.habits.models import Habit, HabitLog
    from django.db.models import Q

    habits = list(
        Habit.objects
        .filter(user=user, is_active=True)
        .filter(Q(habit_type="positive") | Q(habit_type="both"))
    )
    for h in habits:
        h._taps_today = HabitLog.objects.filter(
            habit=h, user=user, direction=1,
            created_at__date=target_date,
        ).count()
    return [h for h in habits if h._taps_today < h.max_taps_per_day]


def _habit_actions(user, target_date, *, hour):
    if hour < 18:
        return []
    streak = _login_streak(user)
    if streak < 1:
        return []
    habits = _untapped_positive_habits(user, target_date)
    if not habits:
        return []
    # Pick the habit with highest strength, ties broken by name.
    habits.sort(key=lambda h: (-h.strength, h.name))
    top = habits[0]
    icon = top.icon or "Flame"
    return [NextAction(
        kind="habit",
        id=top.pk,
        title=top.name,
        subtitle=f"keep your {streak}-day streak",
        score=SCORING_WEIGHTS["habit_streak_protection"],
        due_at=None,
        reward=None,
        icon=icon,
        tone="ember",
        action_url="/habits",
    )]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 24 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/projects/priority.py apps/projects/tests/test_priority_unit.py
git commit -m "feat(priority): add streak-protecting habit contributor"
```

---

## Task 5: Orchestrator — combine, sort, tie-break, limit

**Files:**
- Modify: `apps/projects/priority.py`
- Modify: `apps/projects/tests/test_priority_unit.py`
- Create: `apps/projects/tests/test_priority_integration.py`

The orchestrator calls all three contributors, concatenates, sorts by `(score DESC, reward-has-money DESC, due-at ASC, title ASC)`, and trims to `limit`. The reward tie-break key: `bool(reward and reward.get("money") not in (None, "0.00"))` — presence of real money beats absence.

- [ ] **Step 1: Write the failing orchestrator unit tests**

Append to `apps/projects/tests/test_priority_unit.py`:

```python
class OrchestratorTests(TestCase):
    def _patch_all(self, *, chores=(), homework=(), habits=(), streak=0):
        for target, value in [
            ("apps.projects.priority._available_chores", list(chores)),
            ("apps.projects.priority._eligible_homework", list(homework)),
            ("apps.projects.priority._untapped_positive_habits", list(habits)),
            ("apps.projects.priority._login_streak", streak),
        ]:
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_sorts_descending_by_score(self):
        today = datetime.date(2026, 4, 16)
        hw_overdue = _make_homework(pk=1, title="Overdue",
                                    due_date=datetime.date(2026, 4, 14))
        chore_weekly = _make_chore(pk=2, title="Clean Room", recurrence="weekly")
        self._patch_all(chores=[chore_weekly], homework=[hw_overdue])
        actions = build_next_actions(_child(), target_date=today, hour=12)
        # Overdue homework (120) > weekly chore Thursday (34)
        self.assertEqual(
            [(a.kind, a.id) for a in actions],
            [("homework", 1), ("chore", 2)],
        )

    def test_tie_break_reward_wins(self):
        today = datetime.date(2026, 4, 16)
        a = _make_chore(pk=1, title="Apple", recurrence="daily")
        b = _make_chore(pk=2, title="Banana", recurrence="daily",
                        reward=Decimal("1.00"))
        self._patch_all(chores=[a, b])
        actions = build_next_actions(_child(), target_date=today, hour=12)
        # Both score 70 → reward wins, so Banana first
        self.assertEqual(actions[0].id, 2)

    def test_trims_to_limit(self):
        today = datetime.date(2026, 4, 16)
        chores = [
            _make_chore(pk=i, title=f"Chore {i}", recurrence="daily")
            for i in range(30)
        ]
        self._patch_all(chores=chores)
        actions = build_next_actions(
            _child(), target_date=today, hour=12, limit=5,
        )
        self.assertEqual(len(actions), 5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: 3 new tests FAIL — `build_next_actions` still returns `[]`.

- [ ] **Step 3: Replace the orchestrator stub with the real implementation**

Edit `apps/projects/priority.py` — replace the `build_next_actions` function body:

```python
def build_next_actions(user, *, target_date=None, hour=None, limit=20):
    """Return a ranked list of NextAction instances for the user.

    See module docstring for full semantics.
    """
    if user.role != "child":
        return []

    from django.utils import timezone
    if target_date is None:
        target_date = timezone.localdate()
    if hour is None:
        hour = timezone.localtime().hour

    actions = []
    actions.extend(_chore_actions(user, target_date))
    actions.extend(_homework_actions(user, target_date))
    actions.extend(_habit_actions(user, target_date, hour=hour))

    def sort_key(a):
        has_money = bool(a.reward and a.reward.get("money") not in (None, "0.00"))
        due = a.due_at or datetime.date.max
        return (-a.score, 0 if has_money else 1, due, a.title)

    actions.sort(key=sort_key)
    return actions[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_unit -v 2`

Expected: all 27 tests PASS.

- [ ] **Step 5: Write the DB integration test**

Create `apps/projects/tests/test_priority_integration.py`:

```python
"""End-to-end integration test for build_next_actions against real DB fixtures.

Unit coverage for individual scoring rules lives in
test_priority_unit.py — this file confirms the wiring works against real
Django models (queries, signals, etc.)."""
import datetime
from decimal import Decimal

from django.test import TestCase

from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.habits.models import Habit
from apps.projects.models import User
from apps.projects.priority import build_next_actions
from apps.rpg.models import CharacterProfile


class BuildNextActionsIntegrationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        # CharacterProfile auto-created via signal — set streak for test.
        cp = CharacterProfile.objects.get(user=self.child)
        cp.login_streak = 5
        cp.save(update_fields=["login_streak"])

    def test_parent_receives_empty_list(self):
        self.assertEqual(build_next_actions(self.parent), [])

    def test_end_to_end_ordering(self):
        today = datetime.date(2026, 4, 16)  # Thursday

        # Overdue homework (2 days): score 120
        HomeworkAssignment.objects.create(
            title="Reading log", subject="reading", effort_level=3,
            due_date=datetime.date(2026, 4, 14),
            assigned_to=self.child, created_by=self.parent,
        )
        # Due tomorrow: score 60
        HomeworkAssignment.objects.create(
            title="Math workbook", subject="math", effort_level=3,
            due_date=datetime.date(2026, 4, 17),
            assigned_to=self.child, created_by=self.parent,
        )
        # Submitted-but-pending homework: should be filtered out
        submitted = HomeworkAssignment.objects.create(
            title="History essay", subject="social_studies", effort_level=3,
            due_date=datetime.date(2026, 4, 17),
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkSubmission.objects.create(
            assignment=submitted, user=self.child,
            timeliness=HomeworkSubmission.Timeliness.ON_TIME,
        )

        # Daily chore already done: filtered
        done_daily = Chore.objects.create(
            title="Dishes", recurrence="daily",
            reward_amount=Decimal("0.00"), coin_reward=0,
            assigned_to=self.child, created_by=self.parent,
        )
        ChoreCompletion.objects.create(
            chore=done_daily, user=self.child,
            completed_date=today,
            status=ChoreCompletion.Status.APPROVED,
            reward_amount_snapshot=Decimal("0.00"),
        )

        # Weekly chore not done: Thursday → score 34
        Chore.objects.create(
            title="Clean Room", recurrence="weekly",
            reward_amount=Decimal("1.00"), coin_reward=2,
            assigned_to=self.child, created_by=self.parent,
        )

        # Untapped habit, streak=5, hour=19 → score 65
        Habit.objects.create(
            user=self.child, created_by=self.parent,
            name="Brush teeth", habit_type="positive",
            strength=3, max_taps_per_day=1, is_active=True,
        )

        actions = build_next_actions(self.child, target_date=today, hour=19)
        result = [(a.kind, a.title, a.score) for a in actions]

        self.assertEqual(result, [
            ("homework", "Reading log", 120),
            ("habit", "Brush teeth", 65),
            ("homework", "Math workbook", 60),
            ("chore", "Clean Room", 34),
        ])

    def test_rejected_homework_still_eligible(self):
        today = datetime.date(2026, 4, 16)
        hw = HomeworkAssignment.objects.create(
            title="Resubmit this", subject="math", effort_level=3,
            due_date=today,
            assigned_to=self.child, created_by=self.parent,
        )
        HomeworkSubmission.objects.create(
            assignment=hw, user=self.child,
            status=HomeworkSubmission.Status.REJECTED,
            timeliness=HomeworkSubmission.Timeliness.ON_TIME,
        )
        actions = build_next_actions(self.child, target_date=today, hour=12)
        titles = [a.title for a in actions]
        self.assertIn("Resubmit this", titles)
```

- [ ] **Step 6: Run the integration test**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_priority_integration -v 2`

Expected: all 3 tests PASS. (If `CharacterProfile.DoesNotExist` errors out on `setUp`, verify `apps/rpg/signals.py` is registered via `apps/rpg/apps.py`'s `ready()` hook — it should be.)

- [ ] **Step 7: Commit**

```bash
git add apps/projects/priority.py apps/projects/tests/test_priority_unit.py apps/projects/tests/test_priority_integration.py
git commit -m "feat(priority): orchestrator with score/tie-break/limit + DB integration test"
```

---

## Task 6: Wire into DashboardView + endpoint test

**Files:**
- Modify: `apps/projects/views.py`
- Create: `apps/projects/tests/test_dashboard_view.py`

Add one import and six lines to `DashboardView.get`. Create the endpoint test file (none exists yet — verified via glob during plan-writing).

- [ ] **Step 1: Write the failing endpoint test**

Create `apps/projects/tests/test_dashboard_view.py`:

```python
"""Endpoint tests for GET /api/dashboard/.

Currently covers only the `next_actions` field added for the priority feed.
Other dashboard fields are covered implicitly by the pages that consume them."""
import datetime
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.chores.models import Chore
from apps.homework.models import HomeworkAssignment
from apps.projects.models import User


class DashboardNextActionsTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent")
        self.child = User.objects.create_user(
            username="c", password="pw", role="child")
        self.client = APIClient()

    def test_parent_receives_empty_next_actions(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["next_actions"], [])

    def test_child_receives_scored_next_actions(self):
        HomeworkAssignment.objects.create(
            title="Math workbook", subject="math", effort_level=3,
            due_date=datetime.date.today() + datetime.timedelta(days=1),
            assigned_to=self.child, created_by=self.parent,
        )
        Chore.objects.create(
            title="Clean Room", recurrence="weekly",
            reward_amount=Decimal("1.00"), coin_reward=2,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("next_actions", data)
        self.assertGreaterEqual(len(data["next_actions"]), 2)
        first = data["next_actions"][0]
        required_keys = {
            "kind", "id", "title", "subtitle", "score",
            "due_at", "reward", "icon", "tone", "action_url",
        }
        self.assertTrue(required_keys <= set(first.keys()))
        # Homework due tomorrow (60) outranks weekly chore on any weekday (≤58)
        self.assertEqual(first["kind"], "homework")

    def test_child_item_shape_for_chore(self):
        Chore.objects.create(
            title="Dishes", icon="🍽", recurrence="daily",
            reward_amount=Decimal("0.50"), coin_reward=1,
            assigned_to=self.child, created_by=self.parent,
        )
        self.client.force_authenticate(self.child)
        data = self.client.get("/api/dashboard/").json()
        chore_item = next(
            (a for a in data["next_actions"] if a["kind"] == "chore"), None,
        )
        self.assertIsNotNone(chore_item)
        self.assertEqual(chore_item["reward"], {"money": "0.50", "coins": 1})
        self.assertEqual(chore_item["tone"], "moss")
        self.assertEqual(chore_item["action_url"], "/chores")
        self.assertIsNone(chore_item["due_at"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_dashboard_view -v 2`

Expected: all 3 tests FAIL — the response has no `next_actions` key.

- [ ] **Step 3: Wire the priority feed into DashboardView**

Edit `apps/projects/views.py`. Find the response-dict construction in `DashboardView.get` (starts around line 197 with `return Response({`) and add the priority feed import + call.

Immediately before the `return Response({` line, insert:

```python
        from apps.projects import priority as priority_module
        next_actions = [
            a.as_dict() for a in priority_module.build_next_actions(user)
        ]
```

Then inside the response dict (after `"chores_today": chores_today,` and before `"pending_chore_approvals": pending_chore_approvals,`), add one line:

```python
            "next_actions": next_actions,
```

- [ ] **Step 4: Run the endpoint test to verify it passes**

Run: `docker compose exec django python manage.py test apps.projects.tests.test_dashboard_view -v 2`

Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full projects test suite to catch regressions**

Run: `docker compose exec django python manage.py test apps.projects -v 2`

Expected: all tests PASS (new + existing).

- [ ] **Step 6: Commit**

```bash
git add apps/projects/views.py apps/projects/tests/test_dashboard_view.py
git commit -m "feat(dashboard): expose next_actions from /api/dashboard/ endpoint"
```

---

## Task 7: Frontend MSW handler update

**Files:**
- Modify: `frontend/src/test/handlers.js`

Before touching any React component, update the default `/api/dashboard/` mock response to include `next_actions: []`. This is a standalone commit so test failures in subsequent tasks are easy to attribute to the real change.

- [ ] **Step 1: Update the default dashboard handler**

Edit `frontend/src/test/handlers.js`. Find this exact line (around line 29):

```js
  http.get('*/api/dashboard/', () => HttpResponse.json({})),
```

Replace it with:

```js
  http.get('*/api/dashboard/', () => HttpResponse.json({ next_actions: [] })),
```

Rationale: the default handler returns `{}` today. Most consumers of dashboard data tolerate missing fields via destructure defaults, but having the default include the new contract field keeps tests honest — any test that *doesn't* override the handler still receives the realistic shape.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm run test:run`

Expected: all tests PASS (no changes should break — we're just adding a field).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/test/handlers.js
git commit -m "test(frontend): add next_actions to default dashboard MSW handler"
```

---

## Task 8: HeroPrimaryCard — new `next-action` variant

**Files:**
- Modify: `frontend/src/components/dashboard/HeroPrimaryCard.jsx`
- Create: `frontend/src/components/dashboard/HeroPrimaryCard.test.jsx`

Replace the `streak-risk` and `next-chore` variants with a single `next-action` variant that consumes `ctx.nextAction` (the top item from `next_actions`). The `clocked`, `quest-progress`, and `idle` variants stay untouched. The "Complete" button's callback depends on `nextAction.kind`.

### Icon resolution

The new variant needs to render the `icon` name returned by the backend as a real lucide component. Use a small mapping at the top of the file:

```jsx
import { Play, Square, Flame, Sparkles, ClipboardCheck, BookOpen } from 'lucide-react';

const ICON_MAP = {
  BookOpen, Sparkles, Flame, Play, Square, ClipboardCheck,
};
```

Unknown icon names fall back to `Sparkles`.

- [ ] **Step 1: Create the failing test file**

Create `frontend/src/components/dashboard/HeroPrimaryCard.test.jsx`:

```jsx
import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import HeroPrimaryCard from './HeroPrimaryCard';
import { renderWithProviders } from '../../test/render';

describe('HeroPrimaryCard — next-action variant', () => {
  it('renders homework next-action with subtitle and icon', () => {
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday',
          dateStr: 'April 16',
          nextAction: {
            kind: 'homework', id: 42, title: 'Math workbook',
            subtitle: 'Math · due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
        }}
      />,
    );
    expect(screen.getByText('Math workbook')).toBeInTheDocument();
    expect(screen.getByText(/due tomorrow/i)).toBeInTheDocument();
  });

  it('calls onOpenHomework when homework "Submit" clicked', async () => {
    const onOpenHomework = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'homework', id: 42, title: 'Math workbook',
            subtitle: 'Math · due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
          onOpenHomework,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /submit/i }));
    expect(onOpenHomework).toHaveBeenCalledWith(42);
  });

  it('calls onCompleteChore when chore "Complete" clicked', async () => {
    const onCompleteChore = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'chore', id: 7, title: 'Clean Room',
            subtitle: 'duty · $1.00', score: 34,
            icon: 'Sparkles', tone: 'moss', action_url: '/chores',
            due_at: null, reward: { money: '1.00', coins: 2 },
          },
          onCompleteChore,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /complete/i }));
    expect(onCompleteChore).toHaveBeenCalledWith(7);
  });

  it('calls onTapHabit when habit "Tap" clicked', async () => {
    const onTapHabit = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'Thursday', dateStr: 'April 16',
          nextAction: {
            kind: 'habit', id: 9, title: 'Brush teeth',
            subtitle: 'keep your 5-day streak', score: 65,
            icon: 'Flame', tone: 'ember', action_url: '/habits',
            due_at: null, reward: null,
          },
          onTapHabit,
        }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /tap/i }));
    expect(onTapHabit).toHaveBeenCalledWith(9);
  });

  it('falls back to idle variant when no nextAction and nothing else', () => {
    renderWithProviders(
      <HeroPrimaryCard role="child" ctx={{ weekday: 'T', dateStr: 'Apr 16' }} />,
    );
    expect(screen.getByText(/pick something/i)).toBeInTheDocument();
  });

  it('clocked variant still wins over nextAction', () => {
    renderWithProviders(
      <HeroPrimaryCard
        role="child"
        ctx={{
          weekday: 'T', dateStr: 'Apr 16',
          activeTimer: { project_title: 'Birdhouse', elapsed_minutes: 42 },
          nextAction: {
            kind: 'homework', id: 42, title: 'Math',
            subtitle: 'due tomorrow', score: 60,
            icon: 'BookOpen', tone: 'royal', action_url: '/homework',
            due_at: '2026-04-17', reward: null,
          },
        }}
      />,
    );
    expect(screen.getByText('Birdhouse')).toBeInTheDocument();
    expect(screen.queryByText('Math')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm run test:run -- HeroPrimaryCard`

Expected: 4 of the 6 tests FAIL (only the "clocked wins" and "idle fallback" tests should pass since those variants still exist).

- [ ] **Step 3: Rewrite HeroPrimaryCard to add the new variant**

Replace the contents of `frontend/src/components/dashboard/HeroPrimaryCard.jsx` with:

```jsx
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Play, Square, Flame, Sparkles, ClipboardCheck, BookOpen } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
import { formatDuration } from '../../utils/format';
import { inkBleed } from '../../motion/variants';
import { buttonPrimary } from '../../constants/styles';

const ICON_MAP = { BookOpen, Sparkles, Flame, Play, Square, ClipboardCheck };

const TONE_TO_ACCENT_CLASS = {
  royal: 'text-royal',
  moss: 'text-moss',
  ember: 'text-ember-deep',
};

/**
 * HeroPrimaryCard — the single-fold primary card on the Today page.
 *
 * Child roles resolve a context in this order:
 *   clocked → next-action → quest-progress → idle
 * Parent role: queue(count) → all-clear.
 *
 * Props:
 *   role     : 'child' | 'parent'
 *   ctx      : { activeTimer, rpg, nextAction, activeQuest,
 *                weekday, dateStr, pendingCount,
 *                onCompleteChore, onTapHabit, onOpenHomework }
 *
 * `nextAction` is the top item from the backend's `next_actions` feed
 * (see apps/projects/priority.py). Its shape is the NextAction.as_dict()
 * serialization — {kind, id, title, subtitle, score, due_at, reward,
 * icon, tone, action_url}.
 */
export default function HeroPrimaryCard({ role = 'child', ctx = {} }) {
  const navigate = useNavigate();
  const { weekday, dateStr } = ctx;

  if (role === 'parent') {
    const count = Number(ctx.pendingCount) || 0;
    return (
      <motion.div variants={inkBleed} initial="initial" animate="animate">
        <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
          <div className="font-script text-sheikah-teal-deep text-sm mb-0.5">
            {weekday ? `${weekday} · ${dateStr}` : 'Today'}
          </div>
          {count > 0 ? (
            <>
              <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
                {count} {count === 1 ? 'thing needs' : 'things need'} your seal today
              </h1>
              <div className="font-body text-sm text-ink-secondary mt-1">
                Review duties, homework, and redemptions below.
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const el = document.getElementById('approval-queue');
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                  className={`${buttonPrimary} inline-flex items-center gap-2 px-4 py-2 text-sm`}
                >
                  <ClipboardCheck size={16} /> Review queue
                </button>
                <RuneBadge tone="ember">pending</RuneBadge>
              </div>
            </>
          ) : (
            <>
              <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
                Nothing needs your seal.
              </h1>
              <div className="font-body text-sm text-ink-secondary mt-1">
                A quiet page. The kids are on their own today.
              </div>
            </>
          )}
        </ParchmentCard>
      </motion.div>
    );
  }

  // Child contexts.
  const activeTimer = ctx.activeTimer;
  const nextAction = ctx.nextAction;
  const quest = ctx.activeQuest && ctx.activeQuest.status === 'active' ? ctx.activeQuest : null;

  let variant = 'idle';
  if (activeTimer) variant = 'clocked';
  else if (nextAction) variant = 'next-action';
  else if (quest) variant = 'quest-progress';

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate">
      <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
        <div className="font-script text-sheikah-teal-deep text-sm mb-0.5">
          {weekday ? `${weekday} · ${dateStr}` : 'Today'}
        </div>

        {variant === 'clocked' && (
          <>
            <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
              Still inking
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
              {activeTimer.project_title}
            </h1>
            <div className="font-rune text-3xl md:text-4xl font-bold text-ember-deep tabular-nums mt-2">
              {formatDuration(activeTimer.elapsed_minutes)}
            </div>
            <button
              type="button"
              onClick={() => navigate('/clock')}
              className={`${buttonPrimary} mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm`}
            >
              <Square size={16} /> Stop and log
            </button>
          </>
        )}

        {variant === 'next-action' && (
          <NextActionBody
            action={nextAction}
            onOpenHomework={ctx.onOpenHomework}
            onCompleteChore={ctx.onCompleteChore}
            onTapHabit={ctx.onTapHabit}
            onNavigate={navigate}
          />
        )}

        {variant === 'quest-progress' && (
          <>
            <div className="font-script text-xs text-royal uppercase tracking-wider">
              Active trial
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
              {quest.definition?.name}
            </h1>
            <div className="font-body text-sm text-ink-secondary mt-1">
              {quest.current_progress}/{quest.effective_target} · {quest.progress_percent}%
            </div>
            <div className="h-2 mt-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                style={{ width: `${Math.min(100, quest.progress_percent)}%` }}
              />
            </div>
            <button
              type="button"
              onClick={() => navigate('/quests')}
              className="mt-3 font-script text-sm text-sheikah-teal-deep hover:underline"
            >
              View quest →
            </button>
          </>
        )}

        {variant === 'idle' && (
          <>
            <div className="flex items-center gap-1.5 font-script text-xs text-ink-whisper uppercase tracking-wider">
              <Sparkles size={14} /> A quiet page
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5">
              Nothing pressing — pick something.
            </h1>
            <button
              type="button"
              onClick={() => navigate('/quests')}
              className="mt-3 font-script text-sm text-sheikah-teal-deep hover:underline"
            >
              Open the quests hub →
            </button>
          </>
        )}
      </ParchmentCard>
    </motion.div>
  );
}

function NextActionBody({ action, onOpenHomework, onCompleteChore, onTapHabit, onNavigate }) {
  const Icon = ICON_MAP[action.icon] || Sparkles;
  const accentClass = TONE_TO_ACCENT_CLASS[action.tone] || 'text-moss';
  const buttonLabel = action.kind === 'homework' ? 'Submit'
    : action.kind === 'habit' ? 'Tap'
    : 'Complete';
  const handleClick = () => {
    if (action.kind === 'homework' && onOpenHomework) return onOpenHomework(action.id);
    if (action.kind === 'chore' && onCompleteChore) return onCompleteChore(action.id);
    if (action.kind === 'habit' && onTapHabit) return onTapHabit(action.id);
    if (action.action_url) onNavigate(action.action_url);
  };

  return (
    <>
      <div className={`flex items-center gap-1.5 font-script text-xs ${accentClass} uppercase tracking-wider`}>
        <Icon size={14} /> Next up
      </div>
      <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
        {action.title}
      </h1>
      <div className="font-body text-sm text-ink-secondary mt-1">
        {action.subtitle}
      </div>
      <button
        type="button"
        aria-label={`${buttonLabel} ${action.title}`}
        onClick={handleClick}
        className={`${buttonPrimary} mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm`}
      >
        <Play size={16} /> {buttonLabel}
      </button>
    </>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test:run -- HeroPrimaryCard`

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the full frontend test suite to catch regressions**

Run: `cd frontend && npm run test:run`

Expected: all tests PASS (may see failures in `ChildDashboard.test.jsx` or `Dashboard.test.jsx` that reference the old `streak-risk` variant — if so, those get cleaned up in Task 9).

If any unrelated tests fail, fix them before committing. Specifically, any test that passed `ctx.onTapHabit` expecting `streak-risk` variant will need the fixture updated to use `nextAction`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/HeroPrimaryCard.jsx frontend/src/components/dashboard/HeroPrimaryCard.test.jsx
git commit -m "feat(hero): replace streak-risk/next-chore with unified next-action variant"
```

---

## Task 9: ChildDashboard — consume `next_actions` for hero + quest log

**Files:**
- Modify: `frontend/src/pages/ChildDashboard.jsx`
- Modify: `frontend/src/pages/ChildDashboard.test.jsx`

The quest log continues to group by kind (Study / Duty / Ritual) but the *ordering within each group* now comes from `next_actions`. The hero receives `next_actions[0]` via the new `nextAction` context field.

### Grouping convention

- `kind === 'homework'` → Study section
- `kind === 'chore'` → Duty section
- `kind === 'habit'` → Ritual section

### Migration shape

Current `buildTodayQuests` + `buildHomeworkEntries` are replaced by one helper. Approved/pending homework that currently renders as `awaiting seal` rows is NOT in `next_actions` (filtered server-side). For now, the "pending submission" UI rows are dropped — they'll come back if user feedback demands, but per the spec they're excluded because "there's nothing for the kid to *do*."

The handler functions (`handleCompleteChore`, `handleTapHabit`, `handleOpenHomework`) likely already exist in `ChildDashboard.jsx` — they're passed to the existing hero today. Reuse them; do not redefine.

- [ ] **Step 1: Read the current ChildDashboard to understand what needs to change**

Run: `cat frontend/src/pages/ChildDashboard.jsx | head -200`

Note the imports, the `buildHomeworkEntries` helper, the `buildTodayQuests` helper, and where they're called. The goal is to replace both with a single `buildQuestLogFromActions`.

- [ ] **Step 2: Write the failing ChildDashboard tests**

Edit `frontend/src/pages/ChildDashboard.test.jsx`. Find the current test-scaffold fixture (something like `const dashboardData = {...}`), and add `next_actions` to it. Add a new test:

```jsx
it('renders hero using next_actions[0] and groups quest log by kind', async () => {
  const { spyHandler } = await import('../test/spy');
  spyHandler('get', /\/api\/dashboard\/$/, {
    role: 'child',
    active_timer: null,
    chores_today: [], // deprecated — still on wire
    homework: { dashboard: { overdue: [], today: [], upcoming: [] } },
    rpg: {
      level: 0, login_streak: 0, longest_login_streak: 0,
      perfect_days_count: 0, last_active_date: null, habits_today: [],
    },
    next_actions: [
      { kind: 'homework', id: 42, title: 'Math workbook',
        subtitle: 'Math · due tomorrow', score: 60, due_at: '2026-04-17',
        reward: null, icon: 'BookOpen', tone: 'royal', action_url: '/homework' },
      { kind: 'chore', id: 7, title: 'Clean Room',
        subtitle: 'duty · $1.00', score: 34, due_at: null,
        reward: { money: '1.00', coins: 2 },
        icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
    ],
  });

  renderWithProviders(<ChildDashboard />, { withAuth: true });
  await screen.findByText('Math workbook');
  // Hero shows top item
  expect(screen.getByText('Math workbook')).toBeInTheDocument();
  // Quest log shows both items grouped by section
  expect(screen.getByText(/study/i)).toBeInTheDocument();
  expect(screen.getByText(/duty/i)).toBeInTheDocument();
  expect(screen.getByText('Clean Room')).toBeInTheDocument();
});
```

Replace any existing test in this file that references `streak-risk` hero variant or passes only `chores_today` as the source of Duty items. Update those fixtures to include `next_actions`.

- [ ] **Step 3: Run the failing tests**

Run: `cd frontend && npm run test:run -- ChildDashboard`

Expected: the new test FAILS (ChildDashboard doesn't pass `nextAction` to the hero yet and doesn't group from `next_actions`).

- [ ] **Step 4: Update ChildDashboard to consume next_actions**

Edit `frontend/src/pages/ChildDashboard.jsx`:

Replace the imports / helpers block near the top with (keeping other existing imports):

```jsx
// Remove: import { nextDueTarget, ... } from './_dashboardShared';
// Keep: formatWeekdayDate, mapProjectTone, streakMultiplier imports from _dashboardShared

function buildQuestLogFromActions(next_actions = []) {
  const study = [];
  const duty = [];
  const ritual = [];
  for (const a of next_actions) {
    if (a.kind === 'homework') study.push(a);
    else if (a.kind === 'chore') duty.push(a);
    else if (a.kind === 'habit') ritual.push(a);
  }
  // Already sorted by score DESC in the backend; sections preserve that order.
  return { study, duty, ritual };
}
```

Delete the `buildHomeworkEntries` and `buildTodayQuests` function bodies entirely.

Find the ChildDashboard component's render section. Where it currently destructures dashboard data, add `next_actions = []`:

```jsx
const {
  role, active_timer, current_balance, coin_balance, this_week,
  active_projects, pending_timecards, recent_badges, savings_goals,
  chores_today, rpg, homework, next_actions = [],
} = data;
```

Where the hero is rendered, pass `nextAction={next_actions[0]}` into the `ctx` prop. Example:

```jsx
<HeroPrimaryCard
  role="child"
  ctx={{
    weekday, dateStr, activeTimer: active_timer,
    rpg, nextAction: next_actions[0] || null,
    activeQuest,
    onCompleteChore: handleCompleteChore,
    onTapHabit: handleTapHabit,
    onOpenHomework: handleOpenHomework,
  }}
/>
```

Where the quest log is rendered, build from the grouped object:

```jsx
const { study, duty, ritual } = buildQuestLogFromActions(next_actions);
```

Render each section only if its array is non-empty. Each `<QuestLogEntry>` now consumes a `NextAction` shape — pass `a.title`, `a.subtitle`, `a.kind`, `a.icon`, `a.tone` into the existing `QuestLogEntry` props as appropriate. The click handler on an entry mirrors the hero's switch: homework → `onOpenHomework(a.id)`, chore → `onCompleteChore(a.id)`, habit → `onTapHabit(a.id)`.

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm run test:run -- ChildDashboard`

Expected: the new test PASSES and any pre-existing tests that still have valid fixtures PASS.

- [ ] **Step 6: Add a smoke test in Dashboard.test.jsx**

Edit `frontend/src/pages/Dashboard.test.jsx` — add one test:

```jsx
it('threads next_actions through to ChildDashboard', async () => {
  const { spyHandler } = await import('../test/spy');
  spyHandler('get', /\/api\/dashboard\/$/, {
    role: 'child',
    active_timer: null,
    chores_today: [],
    homework: { dashboard: { overdue: [], today: [], upcoming: [] } },
    rpg: {
      level: 0, login_streak: 0, longest_login_streak: 0,
      perfect_days_count: 0, last_active_date: null, habits_today: [],
    },
    next_actions: [
      { kind: 'chore', id: 1, title: 'Threaded Chore',
        subtitle: 'duty', score: 70, due_at: null, reward: null,
        icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
    ],
  });
  renderWithProviders(<Dashboard />, { withAuth: true });
  await screen.findByText('Threaded Chore');
  expect(screen.getByText('Threaded Chore')).toBeInTheDocument();
});
```

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npm run test:run`

Expected: all tests PASS.

- [ ] **Step 8: Run the dev server and eyeball the dashboard**

Per CLAUDE.md, UI changes need browser verification. Start the stack if not already running:

```bash
docker compose up -d django celery_worker celery_beat db redis
cd frontend && npm run dev
```

Open `http://localhost:3000/`, log in as a child, verify:
- Hero card shows the top-scored item (not necessarily a weekly chore)
- Quest log groups by Study / Duty / Ritual
- Within each group, items are ordered by urgency (overdue homework before due-tomorrow homework; Thursday weekly chores stay lower than daily chores)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/ChildDashboard.jsx frontend/src/pages/ChildDashboard.test.jsx frontend/src/pages/Dashboard.test.jsx
git commit -m "feat(dashboard): drive child hero + quest log from next_actions feed"
```

---

## Task 10: Remove `nextDueTarget` from `_dashboardShared.js`

**Files:**
- Modify: `frontend/src/pages/_dashboardShared.js`
- Modify: `frontend/src/pages/_dashboardShared.test.js`

Final cleanup: the server now owns date math ("due today vs. tomorrow vs. this week"). The old `nextDueTarget` helper and its tests are dead code.

- [ ] **Step 1: Confirm there are no remaining consumers**

Run: `cd frontend && grep -rn nextDueTarget src/`

Expected: the only references should be in `_dashboardShared.js` and `_dashboardShared.test.js` themselves (ChildDashboard's import was removed in Task 9). If anything else references it, stop and migrate it first.

- [ ] **Step 2: Remove the function from the source file**

Edit `frontend/src/pages/_dashboardShared.js` — delete the `nextDueTarget` export and its docstring (lines 27–49 in the current file). Keep `formatWeekdayDate`, `mapProjectTone`, and `streakMultiplier`.

- [ ] **Step 3: Remove the tests for it**

Edit `frontend/src/pages/_dashboardShared.test.js` — delete any `describe('nextDueTarget', ...)` block or individual `it(...)` tests that exercise it.

- [ ] **Step 4: Run the frontend test suite**

Run: `cd frontend && npm run test:run`

Expected: all tests PASS.

- [ ] **Step 5: Update CLAUDE.md if it mentions nextDueTarget**

Run: `grep -n nextDueTarget CLAUDE.md`

If there are matches, edit the affected paragraphs to remove or update the references. For example, the paragraph about "next-school-day horizon is `nextDueTarget()` in `_dashboardShared.js`" should be updated to note that the server now computes it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/_dashboardShared.js frontend/src/pages/_dashboardShared.test.js CLAUDE.md
git commit -m "refactor(dashboard): drop nextDueTarget — server owns due-date math"
```

---

## Verification — full suite

After all 10 tasks land:

- [ ] **Backend:** `docker compose exec django python manage.py test apps.projects -v 2` — all green
- [ ] **Frontend:** `cd frontend && npm run test:run` — all green
- [ ] **Frontend coverage gate:** `cd frontend && npm run test:coverage` — thresholds hold (65/55/55/65)
- [ ] **Smoke test the child dashboard** in a browser as described in Task 9 Step 8
- [ ] **Smoke test the parent dashboard** — `next_actions` should be `[]` and the approval-queue hero variant should render unchanged

## Follow-up (not in this plan)

The spec called out a follow-up cleanup PR to remove the duplicated per-source arrays (`chores_today`, `homework.dashboard`, `rpg.habits_today`) from the dashboard payload once no frontend code reads them. That's intentionally deferred — some (`HeaderStatusPips`, `HomeworkSubmitSheet`, `QuickActionsFab`) legitimately still need those fields for non-priority-feed purposes. After this lands, audit consumer sites with `grep -rn chores_today frontend/src` and decide case-by-case.
