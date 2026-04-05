from decimal import Decimal

from django.utils import timezone

from apps.payments.models import PaymentLedger

from .models import Timecard, TimeEntry


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

        from apps.achievements.services import SkillService, BadgeService
        hours = entry.duration_minutes / 60
        xp = round(hours * 10)
        if xp > 0:
            SkillService.distribute_project_xp(user, entry.project, xp)
        BadgeService.evaluate_badges(user)

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
                PaymentLedger.objects.create(
                    user=user,
                    amount=amount,
                    entry_type="hourly",
                    description=f"Hourly: {entry.project.title} ({hours}h @ ${rate}/hr)",
                    project=entry.project,
                    timecard=timecard,
                )

        return timecard

    @staticmethod
    def approve_timecard(timecard, parent_user, notes=""):
        """Approve a timecard."""
        timecard.status = "approved"
        timecard.approved_by = parent_user
        timecard.approved_at = timezone.now()
        timecard.parent_notes = notes
        timecard.save()

        from apps.achievements.services import BadgeService
        BadgeService.evaluate_badges(timecard.user)

        return timecard

    @staticmethod
    def mark_paid(timecard, parent_user, payout_amount):
        """Mark a timecard as paid and create payout ledger entry."""
        timecard.status = "paid"
        timecard.save()

        PaymentLedger.objects.create(
            user=timecard.user,
            amount=-abs(payout_amount),
            entry_type="payout",
            description=f"Payout for week of {timecard.week_start}",
            timecard=timecard,
            created_by=parent_user,
        )

        return timecard
