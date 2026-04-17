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
