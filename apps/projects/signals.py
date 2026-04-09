from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(pre_save, sender="projects.Project")
def track_project_status_change(sender, instance, **kwargs):
    """Track the previous status for post_save comparison."""
    if instance.pk:
        try:
            instance._previous_status = sender.objects.get(pk=instance.pk).status
        except sender.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


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
        from apps.payments.models import PaymentLedger
        from apps.achievements.services import BadgeService, SkillService
        from .notifications import notify

        if instance.assigned_to:
            notify(instance.assigned_to, f"Project approved: {instance.title}",
                   "Your project has been approved! Great work!", "project_approved")

        sender.objects.filter(pk=instance.pk).update(completed_at=timezone.now())

        if instance.bonus_amount and instance.assigned_to:
            is_bounty = getattr(instance, "payment_kind", "required") == "bounty"
            entry_type = "bounty_payout" if is_bounty else "project_bonus"
            label = "Bounty payout" if is_bounty else "Project bonus"
            PaymentLedger.objects.create(
                user=instance.assigned_to,
                amount=instance.bonus_amount,
                entry_type=entry_type,
                description=f"{label}: {instance.title}",
                project=instance,
                created_by=instance.created_by,
            )

        if instance.assigned_to:
            xp = instance.xp_reward or (50 * instance.difficulty)
            SkillService.distribute_project_xp(instance.assigned_to, instance, xp)

            # Coin bonus on project completion. Bounty projects pay a
            # higher coin bonus scaled to difficulty.
            from apps.rewards.services import CoinService
            from apps.rewards.models import CoinLedger
            is_bounty = getattr(instance, "payment_kind", "required") == "bounty"
            coin_bonus = (25 if is_bounty else 10) * max(1, instance.difficulty)
            CoinService.award_coins(
                instance.assigned_to, coin_bonus,
                CoinLedger.Reason.BOUNTY_BONUS if is_bounty else CoinLedger.Reason.PROJECT_BONUS,
                description=f"{'Bounty' if is_bounty else 'Project'} complete: {instance.title}",
                created_by=instance.created_by,
            )

            BadgeService.evaluate_badges(instance.assigned_to)


@receiver(pre_save, sender="projects.ProjectMilestone")
def track_milestone_completion(sender, instance, **kwargs):
    """Track previous completion state."""
    if instance.pk:
        try:
            instance._was_completed = sender.objects.get(pk=instance.pk).is_completed
        except sender.DoesNotExist:
            instance._was_completed = False
    else:
        instance._was_completed = False


@receiver(post_save, sender="projects.ProjectMilestone")
def handle_milestone_completed(sender, instance, created, **kwargs):
    """Award XP and bonuses when a milestone is completed."""
    if not instance.is_completed:
        return
    if getattr(instance, "_was_completed", False):
        return

    sender.objects.filter(pk=instance.pk).update(completed_at=timezone.now())

    user = instance.project.assigned_to

    from .notifications import notify
    if user:
        notify(user, f"Milestone completed: {instance.title}",
               f"You completed a milestone on {instance.project.title}!", "milestone_completed")

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
        from apps.payments.models import PaymentLedger
        PaymentLedger.objects.create(
            user=user,
            amount=instance.bonus_amount,
            entry_type="milestone_bonus",
            description=f"Milestone bonus: {instance.title}",
            project=instance.project,
        )

    BadgeService.evaluate_badges(user)
