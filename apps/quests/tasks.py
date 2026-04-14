from celery import shared_task


@shared_task
def expire_quests_task():
    """Daily: expire active quests past their end date."""
    from apps.quests.services import QuestService
    expired = QuestService.expire_quests()
    return f"Expired {expired} quests"


@shared_task
def apply_boss_rage_task():
    """Daily: apply rage shield to idle boss quests."""
    from apps.quests.services import QuestService
    raged = QuestService.apply_boss_rage()
    return f"Applied rage to {raged} boss quests"
