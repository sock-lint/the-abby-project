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
