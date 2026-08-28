"""Single-heartbeat payload for the SPA's background pollers.

The shell used to run eight independent timers — six toast stacks, the
notification bell, and the first-encounter check — each hitting its own
endpoint on its own interval. For a logged-in child that was roughly 21
requests a minute, a radio wake-up every ~7 seconds, and the worst offender
re-fetched the *entire* dashboard payload (next-action scoring, since-last-
visit computation, plus a ``last_seen_at`` write) every 20 seconds just to
check for newly unlocked Lorebook entries.

``build_pulse`` gathers the same signals in one query pass so the frontend
can poll one endpoint on one timer. Every block mirrors the shape its
dedicated endpoint already returned, so the consuming hooks keep their
existing diffing/dedupe logic and only swap transport.

Deliberately NOT here: anything with a write side effect or real cost.
``build_dashboard`` stamps ``last_seen_at`` and scores next-actions; the
pulse must stay cheap enough to run every 30 seconds forever.
"""
from __future__ import annotations

from typing import Any

NOTIFICATION_SLICE = 20
"""Recent notifications carried per beat — the approval-toast hook only ever
looks at the newest handful, and the bell renders at most 20."""


def build_pulse(user) -> dict[str, Any]:
    """Return every background signal the shell polls for, in one payload."""
    from apps.notifications.models import Notification
    from apps.notifications.serializers import NotificationSerializer
    from apps.pets.expeditions import ExpeditionService
    from apps.pets.serializers import MountExpeditionSerializer
    from apps.rpg.models import CharacterProfile
    from apps.projects.models import SavingsGoal
    from apps.projects.savings_service import SavingsGoalService
    from apps.projects.serializers import SavingsGoalSerializer
    from apps.quests.serializers import QuestSerializer
    from apps.quests.services import QuestService
    from apps.rewards.services import CoinService
    from apps.rpg.models import DropLog
    from apps.rpg.serializers import DropLogSerializer
    from apps.timecards.services import ClockService, TimeEntryService

    is_child = user.role == "child"

    notifications = list(
        user.notifications.all()[:NOTIFICATION_SLICE],
    )
    unread_count = user.notifications.filter(is_read=False).count()

    drops = DropLog.objects.filter(user=user).select_related("item")[:10]

    active_quest = QuestService.get_active_quest(user) if is_child else None

    # Mirrors SavingsGoalViewSet.list — completion detection runs on read so
    # a goal whose target was edited below the current balance completes
    # without waiting for another ledger write. This is the one intentional
    # write in the payload and it is idempotent.
    SavingsGoalService.check_and_complete(user)
    savings_goals = SavingsGoal.objects.filter(user=user)

    expeditions_ready = ExpeditionService.list_for_user(user, ready_only=True)

    return {
        "unread_count": unread_count,
        "notifications": NotificationSerializer(notifications, many=True).data,
        "recent_drops": DropLogSerializer(drops, many=True).data,
        "active_quest": QuestSerializer(active_quest).data if active_quest else None,
        "companion_growth": {"events": _companion_growth(CharacterProfile, user)},
        "expeditions_ready": MountExpeditionSerializer(expeditions_ready, many=True).data,
        "savings_goals": SavingsGoalSerializer(savings_goals, many=True).data,
        "newly_unlocked_lorebook": _newly_unlocked(user) if is_child else [],
        # Cheap header-pip refresh. The pips used to read the full dashboard
        # once at shell mount and then go stale for the whole session — a kid
        # could finish three chores and watch the coin count sit still.
        "header": _header(user, ClockService, CoinService, TimeEntryService),
    }


def _companion_growth(character_profile_model, user) -> list[dict[str, Any]]:
    """The queue CompanionGrowthRecentView serves — passive growth ticks the
    user hasn't seen yet. Read-only here; the toast hook still POSTs to
    ``/pets/companion-growth/seen/`` once it has rendered them."""
    profile = character_profile_model.objects.filter(user=user).first()
    return list(profile.pending_companion_growth or []) if profile else []


def _newly_unlocked(user) -> list[str]:
    from apps.lorebook.services import newly_unlocked_entries

    return newly_unlocked_entries(user)


def _header(user, clock_service, coin_service, time_entry_service) -> dict[str, Any]:
    """The handful of numbers the sticky header shows, without the dashboard."""
    from django.utils import timezone

    active_entry = clock_service.get_active_entry(user)
    active_timer = None
    if active_entry:
        elapsed = (timezone.now() - active_entry.clock_in).total_seconds() / 60
        active_timer = {
            "project_id": active_entry.project_id,
            "project_title": active_entry.project.title,
            "clock_in": active_entry.clock_in.isoformat(),
            "elapsed_minutes": round(elapsed),
        }

    return {
        "active_timer": active_timer,
        "coin_balance": coin_service.get_balance(user),
        "streak_days": time_entry_service.current_streak(user),
    }
