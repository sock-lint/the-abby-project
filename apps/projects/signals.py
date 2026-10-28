import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


def _track_previous_value(instance, sender, field, default=None):
    """Read the prior transition state without erasing its accepted timestamp."""
    if instance.pk:
        try:
            previous = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            return default
        # A full save loaded before another completion can carry None even
        # after waiting for its child gate. Preserve the committed first time.
        if instance.completed_at is None:
            instance.completed_at = previous.completed_at
        return getattr(previous, field)
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

    if instance.is_homework:
        return

    if instance.status == "in_progress" and not instance.started_at:
        sender.objects.filter(pk=instance.pk).update(started_at=timezone.now())

    elif instance.status == "completed" and previous != "completed":
        # Project.save keeps this unique receipt and every award in one
        # transaction. Concurrent approvals and reopening/reassigning a project
        # may change its status again, but cannot create another reward.
        if instance.assigned_to_id:
            from .models import ProjectCompletionRewardReceipt

            _receipt, first_completion = ProjectCompletionRewardReceipt.objects.get_or_create(
                project=instance, defaults={"user_id": instance.assigned_to_id},
            )
            if not first_completion:
                return

        logger.info(
            "Project completed: '%s' by user %s (payment_kind=%s)",
            instance.title, instance.assigned_to, getattr(instance, "payment_kind", "required"),
        )
        from apps.achievements.services import AwardService
        from apps.rewards.models import CoinLedger
        from apps.notifications.services import notify

        if instance.assigned_to:
            parent_owner = instance.assigned_to.role == "parent"
            verb = "completed" if parent_owner else "approved"
            message = ("You completed your project! Great work!" if parent_owner
                       else "Your project has been approved! Great work!")
            link = f"/projects/{instance.pk}" + ("?space=personal" if parent_owner else "")
            notify(instance.assigned_to, f"Project {verb}: {instance.title}",
                   message, "project_approved", link=link)

        if instance.completed_at is None:
            instance.completed_at = timezone.now()
        sender.objects.filter(pk=instance.pk).update(completed_at=instance.completed_at)

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
                {
                    "project_id": instance.pk,
                    "payment_kind": "bounty" if is_bounty else "required",
                },
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

    user = instance.project.assigned_to
    is_homework = instance.project.is_homework
    receipt = None
    if user and not is_homework:
        from .models import MilestoneCompletionRewardReceipt

        receipt, first_completion = MilestoneCompletionRewardReceipt.objects.get_or_create(
            milestone=instance, defaults={"user_id": user.pk},
        )
        if not first_completion:
            # A stale full save may have overwritten the first completion's
            # timestamp with None. Keep completion progress without replaying
            # XP, money, notifications, badges or a drop opportunity.
            if instance.completed_at is None:
                instance.completed_at = receipt.created_at
                sender.objects.filter(pk=instance.pk).update(completed_at=instance.completed_at)
            return
        instance._completion_reward_claimed = True

    logger.info("Milestone completed: '%s' on project %s", instance.title, instance.project_id)
    instance.completed_at = instance.completed_at or (receipt.created_at if receipt else timezone.now())
    sender.objects.filter(pk=instance.pk).update(completed_at=instance.completed_at)

    if is_homework:
        return

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

    from django.db.models import Sum
    from apps.achievements.services import SkillService, BadgeService, _lock_award_user
    from apps.achievements.models import MilestoneSkillTag, SkillProgress

    # Take the shared award gate before the XP snapshots. MCP reports this
    # single signal-owned award rather than distributing tagged XP a second time.
    _lock_award_user(user)
    progress = SkillProgress.objects.filter(user=user)
    xp_before = progress.aggregate(total=Sum("xp_points"))["total"] or 0
    milestone_tags = MilestoneSkillTag.objects.filter(milestone=instance)
    if milestone_tags.exists():
        for tag in milestone_tags.select_related("skill"):
            SkillService.award_xp(user, tag.skill, tag.xp_amount)
    else:
        SkillService.distribute_project_xp(user, instance.project, 15)
    xp_after = progress.aggregate(total=Sum("xp_points"))["total"] or 0
    instance._completion_reward_xp = xp_after - xp_before

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
