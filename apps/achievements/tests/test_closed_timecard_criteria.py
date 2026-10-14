"""Closing a zero-dollar approved week preserves its badge eligibility."""
from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.achievements.models import Badge, UserBadge
from apps.achievements.services import BadgeService
from apps.payments.models import PaymentLedger
from apps.timecards.models import Timecard
from config.tests.factories import make_family


class ClosedTimecardBadgeTests(TestCase):
    def setUp(self):
        household = make_family(
            "Timecard badge family",
            parents=[{"username": "timecard-badge-parent"}],
            children=[{"username": "timecard-badge-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.card = Timecard.objects.create(
            user=self.child, week_start=date(2026, 10, 5),
            week_end=date(2026, 10, 11), status=Timecard.Status.APPROVED,
            decided_by=self.parent, decided_at=timezone.now(),
        )

    def test_badge_added_after_closure_can_still_be_earned_once(self):
        # The badge may be authored after the week was approved and closed.
        self.card.status = "closed"
        self.card.save(update_fields=["status"])
        badge = Badge.objects.create(
            name="Reviewed weekly work", criteria_type=Badge.CriteriaType.PERFECT_TIMECARD,
            criteria_value={},
        )

        awarded = BadgeService.evaluate_badges(self.child, scopes={"time"})
        self.assertIn(badge, awarded)
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"time"}), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child, badge=badge).count(), 1)
        self.assertFalse(PaymentLedger.objects.filter(timecard=self.card).exists())

    def test_unapproved_weeks_do_not_qualify(self):
        Badge.objects.create(
            name="Reviewed weekly work", criteria_type=Badge.CriteriaType.PERFECT_TIMECARD,
            criteria_value={},
        )
        for status in (Timecard.Status.PENDING, Timecard.Status.DISPUTED):
            with self.subTest(status=status):
                self.card.status = status
                self.card.save(update_fields=["status"])
                self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"time"}), [])
        self.assertFalse(UserBadge.objects.filter(user=self.child).exists())

