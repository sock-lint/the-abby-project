"""Daily duty reminders must stay inside their owning household."""
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.chores.models import Chore, ChoreCompletion
from apps.google_integration.tasks import send_daily_reminders_task
from apps.notifications.models import Notification, NotificationType
from config.tests.factories import make_family


class DailyReminderScopingTests(TestCase):
    def setUp(self):
        own = make_family(
            "Reminder family",
            parents=[{"username": "reminder-parent"}],
            children=[
                {"username": "reminder-child"},
                {"username": "reminder-sibling"},
                {"username": "reminder-inactive", "is_active": False},
            ],
        )
        other = make_family(
            "Other reminder family",
            parents=[{"username": "other-reminder-parent"}],
            children=[{"username": "other-reminder-child"}],
        )
        self.family = own.family
        self.parent = own.parents[0]
        self.child, self.sibling, self.inactive = own.children
        self.other_family = other.family
        self.other_parent = other.parents[0]
        self.other_child = other.children[0]
        self.today = date(2026, 10, 11)

        sync_patch = patch("apps.google_integration.tasks.sync_chore_task.delay")
        sync_patch.start()
        self.addCleanup(sync_patch.stop)
        push_patch = patch("apps.notifications.services._push")
        push_patch.start()
        self.addCleanup(push_patch.stop)
        date_patch = patch("apps.google_integration.tasks.date")
        date_patch.start().today.return_value = self.today
        self.addCleanup(date_patch.stop)
        localdate_patch = patch("apps.chores.services.timezone.localdate", return_value=self.today)
        localdate_patch.start()
        self.addCleanup(localdate_patch.stop)

    def chore(self, title, **kwargs):
        return Chore.objects.create(**{
            "family": self.family,
            "created_by": self.parent,
            "title": title,
            **kwargs,
        })

    def completion(self, chore, **kwargs):
        return ChoreCompletion.objects.create(**{
            "chore": chore,
            "user": self.child,
            "completed_date": self.today,
            "reward_amount_snapshot": "0.00",
            "coin_reward_snapshot": 0,
            **kwargs,
        })

    def reminder_recipients(self):
        return set(Notification.objects.filter(
            notification_type=NotificationType.CHORE_REMINDER,
        ).values_list("user_id", "title"))

    def test_shared_and_assigned_reminders_stay_in_chore_family(self):
        self.chore("Own shared duty", created_by=self.other_parent)
        self.chore("Own assigned duty", assigned_to=self.child)
        self.chore("Sibling assigned duty", assigned_to=self.sibling)
        self.chore("Foreign shared duty", family=self.other_family, created_by=self.other_parent)
        self.chore("Foreign assigned duty", family=self.other_family, assigned_to=self.other_child)
        self.chore("Malformed foreign assignment", family=self.other_family, assigned_to=self.child)

        result = send_daily_reminders_task()

        self.assertEqual(self.reminder_recipients(), {
            (self.child.pk, "Don't forget: Own shared duty"),
            (self.sibling.pk, "Don't forget: Own shared duty"),
            (self.child.pk, "Don't forget: Own assigned duty"),
            (self.sibling.pk, "Don't forget: Sibling assigned duty"),
            (self.other_child.pk, "Don't forget: Foreign shared duty"),
            (self.other_child.pk, "Don't forget: Foreign assigned duty"),
        })
        self.assertEqual(result, "Daily reminders sent: 6")
        self.assertFalse(Notification.objects.filter(
            user__in=[self.parent, self.other_parent, self.inactive],
        ).exists())

    def test_inactive_and_unapproved_duties_do_not_generate_reminders(self):
        self.chore("Inactive shared duty", is_active=False)
        self.chore("Unapproved shared proposal", pending_parent_review=True)
        self.chore("Unapproved own proposal", assigned_to=self.child, pending_parent_review=True)
        self.chore("Inactive child assignment", assigned_to=self.inactive)

        self.assertEqual(send_daily_reminders_task(), "Daily reminders sent: 0")
        self.assertFalse(Notification.objects.exists())

    def test_eligible_reminders_preserve_completion_and_alternating_week_rules(self):
        done_today = self.chore("Done today", assigned_to=self.child)
        self.completion(done_today)
        done_once = self.chore("Finished one-time duty", assigned_to=self.child, recurrence="one_time")
        self.completion(done_once, completed_date=self.today - timedelta(days=4))
        rejected = self.chore("Rejected duty", assigned_to=self.child)
        self.completion(rejected, status=ChoreCompletion.Status.REJECTED)
        self.chore(
            "Off-week duty", assigned_to=self.child, week_schedule="alternating",
            schedule_start_date=self.today - timedelta(days=7),
        )
        self.chore(
            "On-week duty", assigned_to=self.child, week_schedule="alternating",
            schedule_start_date=self.today,
        )

        send_daily_reminders_task()

        self.assertEqual(self.reminder_recipients(), {
            (self.child.pk, "Don't forget: Rejected duty"),
            (self.child.pk, "Don't forget: On-week duty"),
        })
        # Pending completions notify only the parent of the completing child.
        approvals = Notification.objects.filter(notification_type=NotificationType.APPROVAL_REMINDER)
        self.assertEqual(list(approvals.values_list("user_id", flat=True)), [self.parent.pk])
