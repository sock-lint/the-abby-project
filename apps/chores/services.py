import datetime
import logging

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.notifications.models import NotificationType
from apps.notifications.services import get_display_name, notify, notify_parents
from apps.rewards.models import CoinLedger
from apps.rewards.services import CoinService
from config.services import finalize_decision

from .models import Chore, ChoreCompletion

logger = logging.getLogger(__name__)


class ChoreNotAvailableError(Exception):
    pass


class ChoreService:
    @staticmethod
    def is_active_this_week(chore, target_date=None):
        """Return True if the chore is active for the week containing target_date."""
        if chore.week_schedule == Chore.WeekSchedule.EVERY_WEEK:
            return True
        if not chore.schedule_start_date:
            return True
        if target_date is None:
            target_date = timezone.localdate()
        target_iso_week = target_date.isocalendar()[1]
        start_iso_week = chore.schedule_start_date.isocalendar()[1]
        return (target_iso_week % 2) == (start_iso_week % 2)

    @staticmethod
    def _period_date(chore, target_date):
        """Return the canonical period date for a chore on the given date."""
        if chore.recurrence == Chore.Recurrence.WEEKLY:
            return target_date - datetime.timedelta(days=target_date.weekday())
        return target_date

    @staticmethod
    def get_available_chores(user, target_date=None):
        """Return chores available to a child, annotated with completion status.

        Each chore in the result has ``is_done_today`` (bool) and
        ``today_completion_status`` (str|None) annotations.
        """
        if target_date is None:
            target_date = timezone.localdate()

        qs = Chore.objects.filter(is_active=True, pending_parent_review=False)

        if user.role == "child":
            qs = qs.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))

        # Exclude alternating-week chores that are off this week.
        active_ids = [c.pk for c in qs if ChoreService.is_active_this_week(c, target_date)]
        qs = qs.filter(pk__in=active_ids)

        # Exclude one-time chores already completed (non-rejected).
        one_time_done = ChoreCompletion.objects.filter(
            chore=OuterRef("pk"),
            user=user,
        ).exclude(status=ChoreCompletion.Status.REJECTED)
        qs = qs.exclude(
            recurrence=Chore.Recurrence.ONE_TIME,
            pk__in=Chore.objects.filter(Exists(one_time_done)),
        )

        # Annotate whether a non-rejected completion exists for the current period.
        # For daily chores, period_date = today; for weekly, period_date = Monday.
        # We need per-chore period_date, but since we query in bulk we'll
        # annotate with the daily check first, then patch weekly in Python.
        daily_completion = ChoreCompletion.objects.filter(
            chore=OuterRef("pk"),
            user=user,
            completed_date=target_date,
        ).exclude(status=ChoreCompletion.Status.REJECTED)

        monday = target_date - datetime.timedelta(days=target_date.weekday())
        weekly_completion = ChoreCompletion.objects.filter(
            chore=OuterRef("pk"),
            user=user,
            completed_date=monday,
        ).exclude(status=ChoreCompletion.Status.REJECTED)

        qs = qs.annotate(
            _has_daily_completion=Exists(daily_completion),
            _has_weekly_completion=Exists(weekly_completion),
        )

        results = []
        for chore in qs:
            if chore.recurrence == Chore.Recurrence.WEEKLY:
                chore.is_done_today = chore._has_weekly_completion
            else:
                chore.is_done_today = chore._has_daily_completion

            # Fetch the actual completion status if done.
            if chore.is_done_today:
                pd = ChoreService._period_date(chore, target_date)
                completion = ChoreCompletion.objects.filter(
                    chore=chore, user=user, completed_date=pd,
                ).exclude(status=ChoreCompletion.Status.REJECTED).first()
                chore.today_completion_status = completion.status if completion else None
                chore.today_completion_id = completion.pk if completion else None
            else:
                chore.today_completion_status = None
                chore.today_completion_id = None
            results.append(chore)
        return results

    @staticmethod
    @transaction.atomic
    def submit_completion(user, chore, notes=""):
        """Child marks a chore as done. Creates a pending ChoreCompletion."""
        if not chore.is_active:
            raise ChoreNotAvailableError("This chore is no longer active.")

        if chore.pending_parent_review:
            raise ChoreNotAvailableError(
                "This duty is waiting for parent approval before it can be completed.",
            )

        if user.role != "child":
            raise ChoreNotAvailableError("Only children can complete chores.")

        if chore.assigned_to and chore.assigned_to != user:
            raise ChoreNotAvailableError("This chore is not assigned to you.")

        target_date = timezone.localdate()

        if not ChoreService.is_active_this_week(chore, target_date):
            raise ChoreNotAvailableError("This chore is not active this week.")

        period_date = ChoreService._period_date(chore, target_date)

        # Check for one-time already done.
        if chore.recurrence == Chore.Recurrence.ONE_TIME:
            if ChoreCompletion.objects.filter(
                chore=chore, user=user,
            ).exclude(status=ChoreCompletion.Status.REJECTED).exists():
                raise ChoreNotAvailableError("This one-time chore has already been completed.")

        # Check for duplicate in current period.
        if ChoreCompletion.objects.filter(
            chore=chore, user=user, completed_date=period_date,
        ).exclude(status=ChoreCompletion.Status.REJECTED).exists():
            raise ChoreNotAvailableError("You have already completed this chore for this period.")

        completion = ChoreCompletion.objects.create(
            chore=chore,
            user=user,
            completed_date=period_date,
            status=ChoreCompletion.Status.PENDING,
            notes=notes,
            reward_amount_snapshot=chore.reward_amount,
            coin_reward_snapshot=chore.coin_reward,
        )

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="approval",
            event_type="chore.submit",
            summary=f"Chore submitted: {chore.title}",
            actor=user,
            subject=user,
            target=completion,
            breakdown=[
                {"label": "reward", "value": str(chore.reward_amount), "op": "note"},
                {"label": "coins", "value": chore.coin_reward, "op": "note"},
            ],
            extras={
                "chore_id": chore.pk,
                "chore_title": chore.title,
                "reward_snapshot": str(chore.reward_amount),
                "coin_snapshot": chore.coin_reward,
            },
        )

        # Notify parents.
        display = get_display_name(user)
        notify_parents(
            title=f"Chore completed: {chore.title}",
            message=f'{display} completed "{chore.title}" and is waiting for approval.',
            notification_type=NotificationType.CHORE_SUBMITTED,
            link="/chores",
            about_user=user,
        )

        return completion

    @staticmethod
    @transaction.atomic
    def approve_completion(completion, parent, notes=""):
        """Parent approves. Posts to PaymentLedger + CoinLedger.

        ``notes`` is accepted for uniform signature with other approval
        services; ChoreCompletion has no ``parent_notes`` field, so we
        forward an empty string to ``finalize_decision`` and stash the
        caller's text on the activity-log row instead. (Previously the
        notes were silently dropped — ``finalize_decision`` now raises
        on a notes-less model, so we have to make the drop explicit.)
        """
        # Race guard: two parents tapping "approve" within ms of each other
        # would each see ``status == PENDING`` and double-pay XP/coins/money.
        # Re-fetch under a row-level lock so the status check + state
        # transition are serialized.
        completion = ChoreCompletion.objects.select_for_update().get(
            pk=completion.pk,
        )
        if completion.status != ChoreCompletion.Status.PENDING:
            return completion

        finalize_decision(
            completion, ChoreCompletion.Status.APPROVED, parent, "",
            activity_category="approval",
            activity_event_type="chore.approve",
            activity_summary=f"Chore approved: {completion.chore.title}",
            activity_subject=completion.user,
            activity_extras={
                "chore_id": completion.chore_id,
                "reward_snapshot": str(completion.reward_amount_snapshot),
                "coin_snapshot": completion.coin_reward_snapshot,
                # Notes don't have a column on ChoreCompletion; preserve
                # them on the audit trail so a future migration can
                # backfill ``parent_notes`` from this extras blob.
                "parent_notes": notes or None,
            },
        )

        # Paired money + coin + skill-XP award through a single distribution
        # call. When the chore has ChoreSkillTag rows, the skill-tree XP pool
        # comes from ``Chore.xp_reward`` and is split proportionally by
        # ``xp_weight``. No tags → no skill XP (chore is coin/money only).
        from apps.achievements.services import AwardService
        AwardService.grant(
            completion.user,
            xp_tags=completion.chore.skill_tags.select_related("skill"),
            xp=completion.chore.xp_reward,
            xp_source_label=f"Chore: {completion.chore.title}",
            coins=completion.coin_reward_snapshot,
            coin_reason=CoinLedger.Reason.CHORE_REWARD,
            coin_description=f"Chore: {completion.chore.title}",
            money=completion.reward_amount_snapshot,
            money_entry_type=PaymentLedger.EntryType.CHORE_REWARD,
            money_description=f"Chore: {completion.chore.title}",
            created_by=parent,
        )

        # Notify child.
        notify(
            completion.user,
            title=f"Chore approved: {completion.chore.title}",
            message=(
                f'Your chore "{completion.chore.title}" was approved! '
                f"You earned ${completion.reward_amount_snapshot} and {completion.coin_reward_snapshot} coins."
            ),
            notification_type=NotificationType.CHORE_APPROVED,
            link="/chores",
        )

        # RPG game loop — wrapped so a downstream crash can't unwind the
        # ledger write above. Shared helper so every approval flow uses
        # the same resilience policy.
        from apps.rpg.constants import TriggerType
        from apps.rpg.services import safe_game_loop_call
        safe_game_loop_call(
            completion.user, TriggerType.CHORE_COMPLETE, {"chore_id": completion.chore_id},
        )

        return completion

    @staticmethod
    @transaction.atomic
    def reject_completion(completion, parent, notes=""):
        """Parent rejects. No payment.

        ``notes`` is accepted for uniform signature; see ``approve_completion``.
        """
        # Race guard mirrors approve_completion — without the lock, an
        # approve + reject racing on the same row could both succeed.
        completion = ChoreCompletion.objects.select_for_update().get(
            pk=completion.pk,
        )
        if completion.status != ChoreCompletion.Status.PENDING:
            return completion

        finalize_decision(
            completion, ChoreCompletion.Status.REJECTED, parent, "",
            activity_category="approval",
            activity_event_type="chore.reject",
            activity_summary=f"Chore rejected: {completion.chore.title}",
            activity_subject=completion.user,
            activity_extras={
                "chore_id": completion.chore_id,
                "parent_notes": notes or None,
            },
        )
        return completion
