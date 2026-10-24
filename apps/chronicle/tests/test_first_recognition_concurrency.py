"""Competing first recognition shares the account gate through awards."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from unittest import skipUnless

from apps.achievements.models import Badge, UserBadge
from apps.chronicle.models import ChronicleEntry
from apps.chronicle.recognition import record_firsts
from apps.notifications.models import Notification
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "PostgreSQL account-lock interleaving")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], RPG_ASSET_SUPPORT_POLICY=None)
class FirstRecognitionConcurrencyTests(TransactionTestCase):
    def test_competing_firsts_pay_one_milestone_badge_and_notify_once(self):
        household = make_family("First race", children=[{"username": "first-race-child"}])
        child = household.children[0]
        badge = Badge.objects.create(
            name="First milestone", criteria_type=Badge.CriteriaType.CHRONICLE_MILESTONES_LOGGED,
            criteria_value={"count": 1}, xp_bonus=0, award_coins=True,
        )
        start = Barrier(2)

        def recognize():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=child.pk)
                start.wait(timeout=15)
                return record_firsts(user, TriggerType.QUEST_COMPLETE)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(recognize) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]

        self.assertEqual(sum(row["entry_id"] is not None for result in results for row in result), 1)
        self.assertEqual(ChronicleEntry.objects.filter(user=child, event_slug="first_quest_completed").count(), 1)
        self.assertEqual(UserBadge.objects.filter(user=child, badge=badge).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=child, reason="badge_bonus").count(), 1)
        self.assertEqual(Notification.objects.filter(user=child, notification_type="chronicle_first_ever").count(), 1)
