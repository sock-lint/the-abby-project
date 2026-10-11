import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.payments.services import PaymentService

from .models import Timecard, TimeEntry

logger = logging.getLogger(__name__)


class TimeEntryService:
    """Shared read-side helpers for completed time entries."""

    @staticmethod
    def completed_entries(user):
        return TimeEntry.objects.filter(user=user, status="completed")

    @classmethod
    def daily_minute_totals(cls, user):
        """Return a queryset of {'day': date, 'total': minutes} for the user."""
        return (
            cls.completed_entries(user)
            .annotate(day=TruncDate("clock_in"))
            .values("day")
            .annotate(total=Sum("duration_minutes"))
        )

    @classmethod
    def distinct_days(cls, user):
        """Return a list of distinct dates the user has worked, newest first."""
        return list(
            cls.completed_entries(user)
            .annotate(day=TruncDate("clock_in"))
            .values_list("day", flat=True)
            .distinct()
            .order_by("-day")
        )

    @classmethod
    def current_streak(cls, user):
        """Number of consecutive days (ending today or most recent) worked."""
        days = cls.distinct_days(user)
        if not days:
            return 0
        streak = 1
        for i in range(1, len(days)):
            if (days[i - 1] - days[i]).days == 1:
                streak += 1
            else:
                break
        return streak

    @classmethod
    def longest_streak_at_least(cls, user, target_days):
        """True if the user has *any* consecutive-day streak >= target_days."""
        days = cls.distinct_days(user)
        if not days:
            return False
        streak = 1
        for i in range(1, len(days)):
            if (days[i - 1] - days[i]).days == 1:
                streak += 1
                if streak >= target_days:
                    return True
            else:
                streak = 1
        return streak >= target_days


class ClockService:
    QUIET_HOURS_START = 22  # 10 PM
    QUIET_HOURS_END = 7  # 7 AM
    MAX_ENTRY_HOURS = 8

    @classmethod
    def clock_in(cls, user, project):
        """Create a new time entry. Validates constraints."""
        active = cls.get_active_entry(user)
        if active:
            raise ValueError("Already clocked in. Clock out first.")

        if project.assigned_to != user:
            raise ValueError("Project is not assigned to you.")

        if project.status not in ("active", "in_progress"):
            raise ValueError("Project is not in a workable status.")

        now = timezone.localtime()
        if cls.QUIET_HOURS_START <= now.hour or now.hour < cls.QUIET_HOURS_END:
            raise ValueError(
                f"Cannot clock in during quiet hours "
                f"({cls.QUIET_HOURS_START}:00 - {cls.QUIET_HOURS_END}:00)."
            )

        entry = TimeEntry.objects.create(
            user=user, project=project, clock_in=timezone.now(), status="active",
        )

        if project.status == "active":
            project.status = "in_progress"
            project.save()

        from apps.activity.services import ActivityLogService
        ActivityLogService.record(
            category="timecard",
            event_type="timecard.clock_in",
            summary=f"Clocked in: {project.title}",
            actor=user,
            subject=user,
            target=entry,
            extras={"project_id": project.pk, "project_title": project.title},
        )

        return entry

    @classmethod
    def clock_out(cls, user, notes=""):
        """Clock out the current active entry."""
        entry = cls.get_active_entry(user)
        if not entry:
            raise ValueError("No active clock-in found.")

        entry.clock_out = timezone.now()
        entry.notes = notes
        entry.status = "completed"
        entry.save()

        from django.conf import settings
        from apps.achievements.services import AwardService
        from apps.rewards.models import CoinLedger
        from apps.activity.services import ActivityLogService, activity_scope

        hours = entry.duration_minutes / 60
        coins = round(hours * getattr(settings, "COINS_PER_HOUR", 5))
        xp = round(hours * 10)

        with activity_scope():
            ActivityLogService.record(
                category="timecard",
                event_type="timecard.clock_out",
                summary=f"Clocked out: {entry.project.title} ({hours:.2f}h)",
                actor=user,
                subject=user,
                target=entry,
                xp_delta=xp,
                coins_delta=coins,
                breakdown=[
                    {"label": "hours", "value": round(hours, 2), "op": "×"},
                    {"label": "coins/hr",
                     "value": getattr(settings, "COINS_PER_HOUR", 5), "op": "="},
                    {"label": "coins", "value": coins, "op": "note"},
                    {"label": "xp", "value": xp, "op": "note"},
                ],
                extras={
                    "project_id": entry.project_id,
                    "project_title": entry.project.title,
                    "hours": round(hours, 4),
                    "duration_minutes": entry.duration_minutes,
                    "auto_clocked_out": entry.auto_clocked_out,
                },
            )

            AwardService.grant(
                user,
                project=entry.project,
                xp=xp,
                coins=coins,
                coin_reason=CoinLedger.Reason.HOURLY,
                coin_description=f"Hourly coins: {entry.project.title}",
                # Audit H8: clock-out moves time-tracking criteria, skill
                # XP (per ProjectSkillTag), and coins. Skip everything else.
                badge_scopes={"time", "skill_xp", "coin", "badges"},
            )

            # RPG game loop — wrapped via shared helper so a downstream
            # crash can't unwind the hourly award above.
            from apps.rpg.constants import TriggerType
            from apps.rpg.services import safe_game_loop_call
            safe_game_loop_call(
                user, TriggerType.CLOCK_OUT,
                {"project_id": entry.project_id, "hours": hours},
            )

        return entry

    @staticmethod
    def get_active_entry(user):
        """Return the current active TimeEntry or None.

        Selects the project in the same query so dashboard callers can
        render ``entry.project.title`` without a follow-up round-trip.
        """
        return (
            TimeEntry.objects.filter(user=user, status="active")
            .select_related("project")
            .first()
        )

    @classmethod
    def auto_clock_out(cls):
        """Auto clock-out entries older than MAX_ENTRY_HOURS."""
        cutoff = timezone.now() - timezone.timedelta(hours=cls.MAX_ENTRY_HOURS)
        stale = TimeEntry.objects.filter(status="active", clock_in__lte=cutoff)
        count = 0
        for entry in stale:
            entry.clock_out = timezone.now()
            entry.auto_clocked_out = True
            entry.status = "completed"
            entry.notes = (entry.notes + "\n[Auto clocked out]").strip()
            entry.save()
            count += 1
        if count:
            logger.info("Auto clocked out %d stale time entries", count)
        return count


class TimecardService:
    @staticmethod
    @transaction.atomic
    def generate_weekly_timecard(user, week_start):
        """Reconcile an open week without rewriting its ledger or settled totals."""
        from datetime import timedelta
        from django.contrib.auth import get_user_model
        from apps.payments.models import PaymentLedger

        # A user lock serializes even the first generation, before a weekly
        # timecard exists. All timecard decisions take locks in this order.
        user = get_user_model().objects.select_for_update().get(pk=user.pk)
        week_end = week_start + timedelta(days=6)
        timecard = Timecard.objects.select_for_update().filter(
            user=user, week_start=week_start,
        ).first()
        if timecard and (
            timecard.status in (Timecard.Status.APPROVED, Timecard.Status.PAID)
            or PaymentLedger.objects.filter(
                timecard=timecard, entry_type=PaymentLedger.EntryType.PAYOUT,
            ).exists()
        ):
            return timecard

        entries = list(TimeEntry.objects.filter(
            user=user, status="completed",
            clock_in__date__gte=week_start,
            clock_in__date__lte=week_end,
        ).select_related("project"))
        if not entries and timecard is None:
            return None

        total_minutes = sum(e.duration_minutes for e in entries)
        cents = Decimal("0.01")
        total_hours = (Decimal(total_minutes) / 60).quantize(cents, rounding=ROUND_HALF_UP)
        expected_by_project = {}
        entry_amounts = []
        for entry in entries:
            rate = entry.project.hourly_rate_override
            if rate is None:
                rate = user.hourly_rate
            hours = (Decimal(entry.duration_minutes) / 60).quantize(cents, rounding=ROUND_HALF_UP)
            amount = (hours * rate).quantize(cents, rounding=ROUND_HALF_UP)
            entry_amounts.append((entry, hours, rate, amount))
            expected_by_project[entry.project_id] = (
                expected_by_project.get(entry.project_id, Decimal("0.00")) + amount
            )
        hourly_earnings = sum(expected_by_project.values(), Decimal("0.00"))

        bonus_earnings = Decimal("0.00")
        completed_projects = user.assigned_projects.filter(
            status="completed",
            completed_at__date__gte=week_start,
            completed_at__date__lte=week_end,
        )
        for project in completed_projects:
            bonus_earnings += project.bonus_amount

        created = timecard is None
        if created:
            timecard = Timecard(user=user, week_start=week_start)
        timecard.week_end = week_end
        timecard.total_hours = total_hours
        timecard.hourly_earnings = hourly_earnings
        timecard.bonus_earnings = bonus_earnings
        timecard.total_earnings = hourly_earnings + bonus_earnings
        timecard.save()
        if created:
            for entry, hours, rate, amount in entry_amounts:
                PaymentService.record_entry(
                    user,
                    amount,
                    "hourly",
                    description=f"Hourly: {entry.project.title} ({hours}h @ ${rate}/hr)",
                    project=entry.project,
                    timecard=timecard,
                )
        else:
            # Reconcile legacy partial writes as well as edited/voided hours.
            # Corrections stay append-only and retain their project attribution.
            actual_by_project = {
                row["project_id"]: row["amount"]
                for row in PaymentLedger.objects.filter(
                    user=user, timecard=timecard, entry_type=PaymentLedger.EntryType.HOURLY,
                ).values("project_id").annotate(amount=Sum("amount"))
            }
            from apps.projects.models import Project
            projects = Project.objects.in_bulk(
                (expected_by_project.keys() | actual_by_project.keys()) - {None},
            )
            corrections = []
            for project_id in expected_by_project.keys() | actual_by_project.keys():
                delta = expected_by_project.get(project_id, Decimal("0.00")) - actual_by_project.get(
                    project_id, Decimal("0.00"),
                )
                if delta:
                    corrections.append((project_id, delta))
            # Each ledger write checks savings goals. Reverse old credits
            # before adding replacements so a temporary inflated balance
            # cannot permanently unlock a goal or its rewards.
            for project_id, delta in sorted(corrections, key=lambda correction: correction[1]):
                PaymentService.record_entry(
                    user, delta, PaymentLedger.EntryType.HOURLY,
                    description=f"Hourly correction for week of {week_start}",
                    project=projects.get(project_id), timecard=timecard,
                )

        return timecard

    @staticmethod
    @transaction.atomic
    def approve_timecard(timecard, parent_user, notes=""):
        """Approve a timecard and stamp audit fields atomically.

        Uses ``finalize_decision`` now that Timecard inherits from
        ``ApprovalWorkflowModel`` (migration 0002).
        """
        from config.services import finalize_decision
        from django.contrib.auth import get_user_model
        from apps.payments.models import PaymentLedger

        get_user_model().objects.select_for_update().get(pk=timecard.user_id)
        locked = Timecard.objects.select_for_update().get(pk=timecard.pk)
        if locked.status in (Timecard.Status.APPROVED, Timecard.Status.PAID) or (
            PaymentLedger.objects.filter(
                timecard=locked, entry_type=PaymentLedger.EntryType.PAYOUT,
            ).exists()
        ):
            timecard.refresh_from_db()
            return timecard

        finalize_decision(
            locked, Timecard.Status.APPROVED, parent_user, notes,
            activity_category="timecard",
            activity_event_type="timecard.approve",
            activity_summary=f"Timecard approved: week of {locked.week_start}",
            activity_subject=locked.user,
            activity_extras={
                "week_start": str(locked.week_start),
                "total_hours": str(locked.total_hours),
                "total_amount": str(locked.total_earnings),
            },
        )

        from apps.achievements.services import BadgeService
        # Audit H8: timecard approval moves PERFECT_TIMECARD (time-scoped)
        # and the BADGES_EARNED meta. Nothing else flips between week-end
        # and approval.
        BadgeService.evaluate_badges(
            locked.user,
            created_by=parent_user,
            scopes={"time", "badges"},
        )

        timecard.refresh_from_db()
        return timecard

    @staticmethod
    @transaction.atomic
    def dispute_timecard(timecard):
        from django.contrib.auth import get_user_model
        from apps.payments.models import PaymentLedger

        get_user_model().objects.select_for_update().get(pk=timecard.user_id)
        locked = Timecard.objects.select_for_update().get(pk=timecard.pk)
        if locked.status == Timecard.Status.PAID or PaymentLedger.objects.filter(
            timecard=locked, entry_type=PaymentLedger.EntryType.PAYOUT,
        ).exists():
            raise ValueError("Paid timecards cannot be reopened.")
        locked.status = Timecard.Status.DISPUTED
        locked.save(update_fields=["status", "updated_at"])
        timecard.refresh_from_db()
        return timecard

    @staticmethod
    @transaction.atomic
    def mark_paid(timecard, parent_user, payout_amount):
        """Commit one payout per timecard, including retries and stale callers."""
        from apps.payments.models import PaymentLedger
        from django.contrib.auth import get_user_model

        if getattr(parent_user, "role", None) != "parent":
            raise PermissionDenied("Only parents can pay timecards.")
        try:
            amount = Decimal(str(payout_amount))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Invalid payout amount.") from None
        if not amount.is_finite() or amount <= 0 or amount > Decimal("999999.99"):
            raise ValueError("Payout amount must be between $0.01 and $999,999.99.")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Payout amount must have at most two decimal places.")

        get_user_model().objects.select_for_update().get(pk=timecard.user_id)
        locked = Timecard.objects.select_for_update().get(pk=timecard.pk)
        if not parent_user.family_id or parent_user.family_id != locked.user.family_id:
            raise PermissionDenied("You can only pay timecards in your family.")
        # The ledger is authoritative even if a later dispute/regeneration
        # changed the status, or this caller loaded the row before a payout.
        if not PaymentLedger.objects.filter(
            timecard=locked, entry_type=PaymentLedger.EntryType.PAYOUT,
        ).exists():
            from apps.payments.greenlight import validate_payable
            from rest_framework.exceptions import ValidationError

            if locked.status not in (Timecard.Status.APPROVED, Timecard.Status.PAID):
                raise ValueError("Approve the timecard before marking it paid.")
            if amount != locked.total_earnings:
                raise ValueError("A timecard payment must equal its full total.")
            try:
                validate_payable(locked.user, amount)
            except ValidationError as exc:
                raise ValueError(str(exc.detail["error"])) from None
            PaymentService.record_entry(
                locked.user,
                -amount,
                PaymentLedger.EntryType.PAYOUT,
                description=f"Payout for week of {locked.week_start}",
                timecard=locked,
                created_by=parent_user,
            )

        if locked.status != Timecard.Status.PAID:
            locked.status = Timecard.Status.PAID
            locked.save(update_fields=["status", "updated_at"])
        timecard.refresh_from_db()

        return timecard
