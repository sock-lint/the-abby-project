import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


def _track_previous_value(instance, sender, field, default=None):
    """Read a field's DB value before save for post_save comparison."""
    if instance.pk:
        try:
            return getattr(sender.objects.get(pk=instance.pk), field)
        except sender.DoesNotExist:
            return default
    return default


@receiver(pre_save, sender="projects.Project")
def track_project_status_change(sender, instance, **kwargs):
    """Track the previous status for post_save comparison."""
    instance._previous_status = _track_previous_value(instance, sender, "status")


@receiver(post_save, sender="projects.Project")
def handle_project_status_change(sender, instance, created, **kwargs):
    """Handle status transitions for projects."""
    if created:
        return

    previous = getattr(instance, "_previous_status", None)
    if previous == instance.status:
        return

    if instance.status == "in_progress" and not instance.started_at:
        sender.objects.filter(pk=instance.pk).update(started_at=timezone.now())

    elif instance.status == "completed" and previous != "completed":
        logger.info(
            "Project completed: '%s' by user %s (payment_kind=%s)",
            instance.title, instance.assigned_to, getattr(instance, "payment_kind", "required"),
        )
        from apps.achievements.services import AwardService
        from apps.rewards.models import CoinLedger
        from apps.notifications.services import notify

        if instance.assigned_to:
            notify(instance.assigned_to, f"Project approved: {instance.title}",
                   "Your project has been approved! Great work!", "project_approved",
                   link=f"/projects/{instance.id}")

        sender.objects.filter(pk=instance.pk).update(completed_at=timezone.now())

        is_bounty = getattr(instance, "payment_kind", "required") == "bounty"

        if instance.assigned_to:
            from apps.activity.services import ActivityLogService
            ActivityLogService.record(
                category="approval",
                event_type="project.complete",
                summary=f"Project complete: {instance.title}",
                actor=instance.created_by,
                subject=instance.assigned_to,
                target=instance,
                breakdown=[
                    {"label": "payment kind",
                     "value": "bounty" if is_bounty else "required",
                     "op": "note"},
                    {"label": "difficulty", "value": instance.difficulty, "op": "note"},
                ],
                extras={
                    "project_id": instance.pk,
                    "project_title": instance.title,
                    "payment_kind": "bounty" if is_bounty else "required",
                    "difficulty": instance.difficulty,
                },
            )
            coin_bonus = (25 if is_bounty else 10) * max(1, instance.difficulty)
            label = "Bounty payout" if is_bounty else "Project bonus"
            AwardService.grant(
                instance.assigned_to,
                project=instance,
                xp=instance.xp_reward or (50 * instance.difficulty),
                coins=coin_bonus,
                coin_reason=(
                    CoinLedger.Reason.BOUNTY_BONUS if is_bounty
                    else CoinLedger.Reason.PROJECT_BONUS
                ),
                coin_description=f"{'Bounty' if is_bounty else 'Project'} complete: {instance.title}",
                money=instance.bonus_amount or 0,
                money_entry_type=(
                    "bounty_payout" if is_bounty else "project_bonus"
                ),
                money_description=f"{label}: {instance.title}",
                created_by=instance.created_by,
            )

        # RPG game loop — wrapped via shared helper so a downstream crash
        # can't unwind the ledger writes posted above.
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import safe_game_loop_call
        if instance.assigned_to:
            safe_game_loop_call(
                instance.assigned_to, TriggerType.PROJECT_COMPLETE,
                {"project_id": instance.pk},
            )


@receiver(pre_save, sender="projects.ProjectMilestone")
def track_milestone_completion(sender, instance, **kwargs):
    """Track previous completion state."""
    instance._was_completed = _track_previous_value(
        instance, sender, "is_completed", default=False,
    )


@receiver(post_save, sender="projects.ProjectMilestone")
def handle_milestone_completed(sender, instance, created, **kwargs):
    """Award XP and bonuses when a milestone is completed."""
    if not instance.is_completed:
        return
    if getattr(instance, "_was_completed", False):
        return

    logger.info("Milestone completed: '%s' on project %s", instance.title, instance.project_id)
    sender.objects.filter(pk=instance.pk).update(completed_at=timezone.now())

    user = instance.project.assigned_to

    if user:
        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="milestone.complete",
            summary=f"Milestone: {instance.title}",
            actor=None,
            subject=user,
            target=instance,
            money_delta=instance.bonus_amount or None,
            breakdown=[
                {"label": "project", "value": instance.project.title, "op": "note"},
                {"label": "bonus", "value": str(instance.bonus_amount or 0), "op": "note"},
            ],
            extras={
                "project_id": instance.project_id,
                "milestone_id": instance.pk,
                "bonus_amount": str(instance.bonus_amount or 0),
            },
        )

    from apps.notifications.services import notify
    if user:
        notify(user, f"Milestone completed: {instance.title}",
               f"You completed a milestone on {instance.project.title}!", "milestone_completed",
               link=f"/projects/{instance.project_id}")

    if not user:
        return

    from apps.achievements.services import SkillService, BadgeService
    from apps.achievements.models import MilestoneSkillTag

    milestone_tags = MilestoneSkillTag.objects.filter(milestone=instance)
    if milestone_tags.exists():
        for tag in milestone_tags.select_related("skill"):
            SkillService.award_xp(user, tag.skill, tag.xp_amount)
    else:
        SkillService.distribute_project_xp(user, instance.project, 15)

    if instance.bonus_amount:
        from apps.payments.services import PaymentService
        PaymentService.record_entry(
            user,
            instance.bonus_amount,
            "milestone_bonus",
            description=f"Milestone bonus: {instance.title}",
            project=instance.project,
        )

    # Audit H8: milestone completion moves milestone counters, skill XP
    # (per MilestoneSkillTag), money (bonus), and the BADGES_EARNED meta.
    BadgeService.evaluate_badges(
        user, scopes={"milestone", "skill_xp", "money", "badges"},
    )

    # RPG game loop — wrapped via shared helper.
    from apps.rpg.constants import TriggerType
    from apps.rpg.services import safe_game_loop_call
    if instance.project.assigned_to:
        safe_game_loop_call(
            instance.project.assigned_to, TriggerType.MILESTONE_COMPLETE,
            {"project_id": instance.project_id, "milestone_id": instance.pk},
        )
