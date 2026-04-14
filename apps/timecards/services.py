import logging
from decimal import Decimal

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

        hours = entry.duration_minutes / 60
        AwardService.grant(
            user,
            project=entry.project,
            xp=round(hours * 10),
            coins=round(hours * getattr(settings, "COINS_PER_HOUR", 5)),
            coin_reason=CoinLedger.Reason.HOURLY,
            coin_description=f"Hourly coins: {entry.project.title}",
        )

        # RPG game loop
        from apps.rpg.services import GameLoopService
        GameLoopService.on_task_completed(
            user, "clock_out",
            {"project_id": entry.project_id, "hours": hours},
        )

        return entry

    @staticmethod
    def get_active_entry(user):
        """Return the current active TimeEntry or None."""
        return TimeEntry.objects.filter(user=user, status="active").first()

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
    def generate_weekly_timecard(user, week_start):
        """Generate a timecard for a given week."""
        from datetime import timedelta
        week_end = week_start + timedelta(days=6)

        entries = TimeEntry.objects.filter(
            user=user, status="completed",
            clock_in__date__gte=week_start,
            clock_in__date__lte=week_end,
        )

        if not entries.exists():
            return None

        total_minutes = sum(e.duration_minutes for e in entries)
        total_hours = Decimal(str(round(total_minutes / 60, 2)))

        hourly_earnings = Decimal("0.00")
        for entry in entries.select_related("project"):
            rate = entry.project.hourly_rate_override or user.hourly_rate
            hours = Decimal(str(round(entry.duration_minutes / 60, 2)))
            hourly_earnings += hours * rate

        bonus_earnings = Decimal("0.00")
        completed_projects = user.assigned_projects.filter(
            status="completed",
            completed_at__date__gte=week_start,
            completed_at__date__lte=week_end,
        )
        for project in completed_projects:
            bonus_earnings += project.bonus_amount

        timecard, created = Timecard.objects.update_or_create(
            user=user, week_start=week_start,
            defaults={
                "week_end": week_end,
                "total_hours": total_hours,
                "hourly_earnings": hourly_earnings,
                "bonus_earnings": bonus_earnings,
                "total_earnings": hourly_earnings + bonus_earnings,
                "status": "pending",
            },
        )

        if created:
            for entry in entries.select_related("project"):
                rate = entry.project.hourly_rate_override or user.hourly_rate
                hours = Decimal(str(round(entry.duration_minutes / 60, 2)))
                amount = hours * rate
                PaymentService.record_entry(
                    user,
                    amount,
                    "hourly",
                    description=f"Hourly: {entry.project.title} ({hours}h @ ${rate}/hr)",
                    project=entry.project,
                    timecard=timecard,
                )

        return timecard

    @staticmethod
    def approve_timecard(timecard, parent_user, notes=""):
        """Approve a timecard."""
        timecard.mark_approved(parent_user, notes)

        from apps.achievements.services import BadgeService
        BadgeService.evaluate_badges(timecard.user)

        return timecard

    @staticmethod
    def mark_paid(timecard, parent_user, payout_amount):
        """Mark a timecard as paid and create payout ledger entry."""
        timecard.status = "paid"
        timecard.save()

        PaymentService.record_entry(
            timecard.user,
            -abs(payout_amount),
            "payout",
            description=f"Payout for week of {timecard.week_start}",
            timecard=timecard,
            created_by=parent_user,
        )

        return timecard
