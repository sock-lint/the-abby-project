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
    """Bounded repair; new bonuses arise from activity rather than rotation."""
    from .activity import retry_pending_activity
    from .daily_bonus import settle_legacy_bonuses
    return f"Daily bonuses: {retry_pending_activity(limit=100)} facts repaired, {settle_legacy_bonuses(limit=100)} legacy bonuses settled"
