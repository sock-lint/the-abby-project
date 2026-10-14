"""Catalog anti-farm policy stays separate from parent-authorized facts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.creations.models import CreationDailyCounter
from apps.creations.services import CreationService
from apps.homework.models import HomeworkDailyCounter
from apps.homework.services import HomeworkService
from apps.quests.activity import record_activity, retry_pending_activity
from apps.quests.goals import create_goal, list_goals
from apps.quests.models import ChallengeActivity, ChallengeEnrollment, ChallengeOccurrence, QuestDefinition
from config.tests.factories import make_family


class CatalogDailyCapTests(TestCase):
    def setUp(self):
        family = make_family("Catalog caps", parents=[{"username": "capsparent"}],
                             children=[{"username": "capschild"}])
        self.parent, self.child = family.parents[0], family.children[0]
        category = SkillCategory.objects.create(name="Art & Crafts")
        self.skill = Skill.objects.create(name="Cap drawing", category=category)
        ChallengeEnrollment.objects.create(user=self.child, starts_at=timezone.now() - timedelta(days=1))

    def catalog_goal(self, trigger, target):
        definition = QuestDefinition.objects.create(
            name=f"Catalog {trigger}", quest_type="collection", is_system=True,
            target_value=target, duration_days=7, coin_reward=40,
            trigger_filter={"allowed_triggers": [trigger]},
        )
        list_goals(self.child)
        return ChallengeOccurrence.objects.get(goal__catalog_definition=definition)

    def homework(self, suffix):
        return HomeworkService.create_assignment(self.child, {
            "title": f"Planning {suffix}", "subject": "math",
            "due_date": timezone.localdate() + timedelta(days=7),
        })

    def creation(self):
        return CreationService.log_creation(self.child, image="synthetic-cap.jpg",
                                            primary_skill_id=self.skill.pk)

    def parent_goal(self, trigger, target):
        return create_goal(self.parent, self.child, {
            "name": "Parent-authorized work", "metric": "count", "target": Decimal(target),
            "unit": "actions", "trigger_type": trigger, "period": "this_week",
            "repeat_weekly": False, "coin_reward": 7, "xp_reward": 0, "skill_tags": [],
        })

    def test_five_same_day_homework_plans_cannot_complete_catalog_goal(self):
        catalog = self.catalog_goal("homework_created", 5)
        for index in range(5):
            self.homework(index)
        catalog.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (1, "active"))
        self.assertIsNone(catalog.awarded_at)
        self.assertEqual(catalog.reward_receipt, {})
        self.assertEqual(HomeworkDailyCounter.objects.get(user=self.child).count, 5)
        payload = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{catalog.pk}")
        self.assertEqual(payload["what_counts"], "planned homework (first per day)")

    def test_parent_weekly_goal_counts_all_valid_plans_without_catalog_cap(self):
        catalog = self.catalog_goal("homework_created", 5)
        for index in range(5):
            self.homework(index)
        parent = self.parent_goal("homework_created", 5)
        self.assertEqual((parent.progress, parent.status), (5, "completed"))
        self.assertEqual(parent.reward_receipt["coins"], 7)
        payload = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{parent.pk}")
        self.assertEqual(payload["what_counts"], "planned homework")
        catalog.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (1, "active"))

    def test_soft_delete_voids_unpaid_plan_without_rearming_catalog_gate(self):
        catalog = self.catalog_goal("homework_created", 5)
        first = self.homework("first")
        client = APIClient()
        client.force_authenticate(self.parent)
        self.assertEqual(client.delete(f"/api/homework/{first.pk}/").status_code, 204)
        for index in range(4):
            self.homework(index)
        catalog.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (0, "active"))
        self.assertIsNone(catalog.awarded_at)
        self.assertTrue(ChallengeActivity.objects.get(user=self.child, source_type="homework_created",
                                                     source_id=str(first.pk)).voided)
        self.assertEqual(HomeworkDailyCounter.objects.get(user=self.child).count, 5)
        parent = self.parent_goal("homework_created", 5)
        self.assertEqual((parent.progress, parent.status), (4, "active"))

    def test_third_creation_counts_parent_goal_but_not_catalog_goal(self):
        catalog = self.catalog_goal("creation_logged", 3)
        parent = self.parent_goal("creation_logged", 3)
        for _ in range(3):
            self.creation()
        catalog.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (2, "active"))
        self.assertIsNone(catalog.awarded_at)
        self.assertEqual((parent.progress, parent.status), (3, "completed"))
        self.assertEqual(parent.reward_receipt["coins"], 7)
        self.assertEqual(CreationDailyCounter.objects.get(user=self.child).count, 3)
        payload = next(row for row in list_goals(self.child)["results"] if row["id"] == f"goal:{catalog.pk}")
        self.assertEqual(payload["what_counts"], "logged creations (first two per day)")

    def test_creation_delete_does_not_rearm_catalog_gate(self):
        catalog = self.catalog_goal("creation_logged", 3)
        first = self.creation()
        self.creation()
        first.delete()
        self.creation()
        catalog.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (1, "active"))
        self.assertIsNone(catalog.awarded_at)
        self.assertEqual(CreationDailyCounter.objects.get(user=self.child).count, 3)

    def test_catalog_attestation_is_not_taken_from_incoming_context(self):
        from apps.homework.models import HomeworkAssignment
        catalog = self.catalog_goal("homework_created", 1)
        source = HomeworkAssignment.objects.create(
            assigned_to=self.child, created_by=self.child, title="Saved outside reward service",
            due_date=timezone.localdate() + timedelta(days=7),
        )
        record_activity(self.child, "homework_created", {"assignment_id": source.pk, "catalog_eligible": True})
        catalog.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (0, "active"))
        fact = ChallengeActivity.objects.get(user=self.child, source_type="homework_created", source_id=str(source.pk))
        self.assertNotIn("catalog_eligible", fact.context)
        parent = self.parent_goal("homework_created", 1)
        self.assertEqual((parent.progress, parent.status), (1, "completed"))

    def test_pending_retry_uses_original_counter_decision(self):
        catalog = self.catalog_goal("homework_created", 3)
        parent = self.parent_goal("homework_created", 2)
        with self.assertLogs("apps.quests.activity", level="ERROR"):
            with patch("apps.quests.goals._process", side_effect=RuntimeError("Retryable evaluator")):
                first, second = self.homework("first"), self.homework("second")
        facts = ChallengeActivity.objects.filter(user=self.child, source_type="homework_created").order_by("pk")
        self.assertEqual([fact.context["catalog_eligible"] for fact in facts], [True, False])
        self.assertTrue(all(fact.processed_at is None for fact in facts))
        self.assertEqual(retry_pending_activity(self.child), 2)
        catalog.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual((catalog.progress, catalog.status), (1, "active"))
        self.assertEqual((parent.progress, parent.status), (2, "completed"))
        # Replaying a second source with a forged flag cannot upgrade its decision.
        record_activity(self.child, "homework_created", {"assignment_id": second.pk, "catalog_eligible": True})
        self.assertFalse(facts.get(source_id=str(second.pk)).context["catalog_eligible"])
        self.assertTrue(facts.get(source_id=str(first.pk)).context["catalog_eligible"])

    def test_soft_delete_keeps_paid_catalog_reward_without_rearming(self):
        catalog = self.catalog_goal("homework_created", 1)
        first = self.homework("first")
        catalog.refresh_from_db()
        original_awarded_at, original_receipt = catalog.awarded_at, catalog.reward_receipt
        client = APIClient()
        client.force_authenticate(self.parent)
        self.assertEqual(client.delete(f"/api/homework/{first.pk}/").status_code, 204)
        self.homework("second")
        catalog.refresh_from_db()
        self.assertEqual((catalog.status, catalog.progress), ("completed", 1))
        self.assertEqual((catalog.awarded_at, catalog.reward_receipt), (original_awarded_at, original_receipt))
        self.assertEqual(catalog.reward_receipt["coins"], 40)
        self.assertEqual(HomeworkDailyCounter.objects.get(user=self.child).count, 2)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
class CatalogCapConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = make_family("Concurrent caps", parents=[{"username": "racecapsparent"}],
                             children=[{"username": "racecapschild"}])
        self.child = family.children[0]
        category = SkillCategory.objects.create(name="Art & Crafts")
        self.skill = Skill.objects.create(name="Concurrent cap drawing", category=category)
        ChallengeEnrollment.objects.create(user=self.child, starts_at=timezone.now() - timedelta(days=1))

    def race_sources(self, trigger, count):
        definition = QuestDefinition.objects.create(
            name=f"Concurrent {trigger}", quest_type="collection", is_system=True,
            target_value=count, duration_days=7, coin_reward=40,
            trigger_filter={"allowed_triggers": [trigger]},
        )
        list_goals(self.child)
        barrier = Barrier(count)

        def worker(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                user = get_user_model().objects.get(pk=self.child.pk)
                barrier.wait(timeout=5)
                if trigger == "homework_created":
                    return HomeworkService.create_assignment(user, {
                        "title": f"Concurrent plan {index}",
                        "due_date": timezone.localdate() + timedelta(days=7),
                    })
                return CreationService.log_creation(user, image="synthetic-race-cap.jpg",
                                                    primary_skill_id=self.skill.pk)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(worker, index) for index in range(count)]
            for future in futures:
                future.result(timeout=15)
        return ChallengeOccurrence.objects.get(goal__catalog_definition=definition)

    def test_concurrent_plans_freeze_one_eligible_catalog_fact(self):
        occurrence = self.race_sources("homework_created", 2)
        self.assertEqual((occurrence.progress, occurrence.status), (1, "active"))
        self.assertEqual(HomeworkDailyCounter.objects.get(user=self.child).count, 2)
        flags = [fact.context["catalog_eligible"] for fact in
                 ChallengeActivity.objects.filter(user=self.child, source_type="homework_created")]
        self.assertCountEqual(flags, [True, False])

    def test_concurrent_creations_freeze_two_eligible_catalog_facts(self):
        occurrence = self.race_sources("creation_logged", 4)
        self.assertEqual((occurrence.progress, occurrence.status), (2, "active"))
        self.assertEqual(CreationDailyCounter.objects.get(user=self.child).count, 4)
        flags = [fact.context["catalog_eligible"] for fact in
                 ChallengeActivity.objects.filter(user=self.child, source_type="creation_logged")]
        self.assertCountEqual(flags, [True, True, False, False])
