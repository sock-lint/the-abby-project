"""Cheap, body-free invalidation signal for the shared parent review inbox."""
import hashlib
import json

from django.db.models import Count, Max, Q


def parent_attention(user):
    if user.role != "parent" or not user.family_id:
        return None
    from apps.chores.models import Chore, ChoreCompletion
    from apps.creations.models import Creation
    from apps.habits.models import Habit
    from apps.homework.models import HomeworkSubmission
    from apps.printing.models import PrintRequest
    from apps.rewards.models import ExchangeRequest, RewardRedemption
    from apps.timecards.models import Timecard

    family = user.family_id
    sources = {
        "chores": ChoreCompletion.objects.filter(user__family_id=family, status="pending"),
        "homework": HomeworkSubmission.objects.filter(user__family_id=family, status="pending"),
        "redemptions": RewardRedemption.objects.filter(user__family_id=family, status="pending"),
        "creations": Creation.objects.filter(user__family_id=family, status="pending"),
        "chore_proposals": Chore.objects.filter(family_id=family, pending_parent_review=True),
        "habit_proposals": Habit.objects.filter(user__family_id=family, pending_parent_review=True),
        "exchanges": ExchangeRequest.objects.filter(user__family_id=family, status="pending"),
        "timecards": Timecard.objects.filter(user__family_id=family, status__in=["pending", "disputed"]),
        "prints": PrintRequest.objects.filter(user__family_id=family, status="pending"),
        "deliveries": RewardRedemption.objects.filter(user__family_id=family, status="approved", fulfillment_kind_snapshot__in=["real_world", "both"]),
    }
    # Include the latest identity, so completing one request while a new one
    # arrives still invalidates an unchanged count. No evidence/content leaves
    # this count-only signal, and query work is constant in household size.
    aggregates = {
        key: queryset.aggregate(count=Count("pk"), latest=Max("pk"))
        for key, queryset in sources.items()
    }
    counts = {key: value["count"] for key, value in aggregates.items()}
    from apps.homework.models import HomeworkAssignment
    from apps.quests.models import ChallengeGoal, ChallengeOccurrence
    from apps.quests.goals import family_zone
    from apps.timecards.models import TimeEntry
    from apps.achievements.models import UserBadge
    from apps.families.queries import children_in
    from apps.projects.parent_overview import recurring_goal_window
    from django.utils import timezone

    # Invalidate the family overview after a co-parent edits work or a goal,
    # after confirmed progress, and when the household day rolls over. These
    # are concrete public work sources: no journal/activity bodies or presence
    # metadata participate in this signal.
    watched = [
        (HomeworkAssignment.objects.filter(assigned_to__family_id=family), "updated_at"),
        (Chore.objects.filter(family_id=family), "updated_at"),
        (ChallengeGoal.objects.filter(family_id=family, is_catalog=False), "updated_at"),
        (ChallengeOccurrence.objects.filter(goal__family_id=family, goal__is_catalog=False), "updated_at"),
        (TimeEntry.objects.filter(user__family_id=family, status="completed"), "clock_out"),
        (UserBadge.objects.filter(user__family_id=family), "earned_at"),
    ]
    marks = [query.aggregate(count=Count("pk"), latest=Max(field)) for query, field in watched]
    roster = list(children_in(user.family).order_by("pk").values("pk", "username", "display_name", "hourly_rate"))
    roster_revision = hashlib.sha256(json.dumps(roster, sort_keys=True, default=str).encode()).hexdigest()
    now = timezone.now()
    zone = family_zone(user)
    day = now.astimezone(zone).date().isoformat()
    recurring = ChallengeGoal.objects.filter(
        family_id=family, is_catalog=False, user_id__in=children_in(user.family).values("pk"),
    ).filter(Q(repeat_weekly=True) | Q(repeat_days__gt=0)).order_by("pk").values(
        "pk", "starts_at", "ends_at", "timezone_name", "repeat_weekly", "repeat_days",
    )
    # A rolling goal can start a new cycle during the household day without
    # any saved activity. Hash window identities so the next pulse refreshes
    # that projection, without publishing names or creating occurrences.
    windows = []
    for goal in recurring:
        window = recurring_goal_window(goal, now, zone)
        windows.append((goal["pk"], window[0].isoformat() if window else None))
    cycle_revision = hashlib.sha256(json.dumps(windows).encode()).hexdigest()
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "revision": ":".join(f"{key}={value['count']},{value['latest'] or 0}" for key, value in aggregates.items()) + f":{zone}:{day}:{marks}:{roster_revision}:{cycle_revision}",
    }
