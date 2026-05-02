from celery import shared_task


@shared_task
def expire_quests_task():
    """Daily: expire active quests past their end date."""
    from apps.quests.services import QuestService
    expired = QuestService.expire_quests()
    return f"Expired {expired} quests"


@shared_task
def apply_boss_rage_task():
    """Daily: climb rage on idle boss quests, decay it on active ones."""
    from apps.quests.services import QuestService
    result = QuestService.apply_boss_rage()
    return f"Rage: +{result['raged']} idle, -{result['decayed']} active"


@shared_task
def rotate_daily_challenges_task():
    """Daily (00:30 local): create today's challenge for every active child.

    Idempotent — `DailyChallengeService.get_or_create_today` uniquely keys on
    (user, date), so a re-run within the same day is a no-op. Skips users
    with role != "child" so parents don't accumulate daily-challenge clutter.
    """
    from apps.families.queries import children_across_families
    from apps.quests.services import DailyChallengeService

    created = 0
    skipped = 0
    for _family, user in children_across_families():
        challenge = DailyChallengeService.get_or_create_today(user)
        if challenge.current_progress == 0 and challenge.completed_at is None:
            created += 1
        else:
            skipped += 1
    return f"Daily challenges: {created} fresh, {skipped} preserved"
