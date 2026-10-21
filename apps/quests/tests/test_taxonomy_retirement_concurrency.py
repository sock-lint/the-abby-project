"""New-reference admission and retirement have one PostgreSQL commit order."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeGoal, QuestDefinition, QuestSkillTag
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row/table locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyRetirementConcurrencyTests(TransactionTestCase):
    def setUp(self):
        own = make_family(parents=[{"username": "retirement-writer"}], children=[{"username": "retirement-child"}])
        maintenance = make_family(parents=[{"username": "retirement-staff", "is_staff": True}])
        self.parent, self.child, self.staff = own.parents[0], own.children[0], maintenance.parents[0]
        self.category = SkillCategory.objects.create(name="Concurrent retirement category")
        self.subject = Subject.objects.create(name="Concurrent retirement subject", category=self.category)
        self.skill = Skill.objects.create(name="Concurrent retirement skill", category=self.category, subject=self.subject)
        self.pids = {}

    def run_connection(self, role, action):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '7s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                self.pids[role] = cursor.fetchone()[0]
            return action()
        finally:
            connections.close_all()

    def assert_blocked(self, waiter, blocker, future):
        deadline = monotonic() + 5
        while monotonic() < deadline and not future.done():
            if waiter in self.pids:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [self.pids[blocker], self.pids[waiter]])
                    if cursor.fetchone()[0]:
                        return
            Event().wait(.01)
        self.fail(f"{waiter} did not block on {blocker}; completed={future.done()}")

    def retire(self):
        client = APIClient()
        client.force_authenticate(self.staff)
        return client.patch(f"/api/categories/{self.category.pk}/", {"is_retired": True}, format="json")

    def private_quest(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        return client.post("/api/quests/", {"name": "Concurrent private reference", "description": "Synthetic",
            "quest_type": "collection", "target_value": 1,
            "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}, format="json")

    def goal(self):
        return create_goal(self.parent, self.child, {"name": "Concurrent goal", "metric": "count", "target": Decimal(2),
            "unit": "actions", "trigger_type": "chore_complete", "period": "from_today", "repeat_weekly": False,
            "xp_reward": 15, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]})

    def assert_writer_commits_before_retirement(self, manager, method, action):
        ready, release = Event(), Event()
        original = getattr(manager, method)

        def pause(*args, **kwargs):
            ready.set()
            if not release.wait(10):
                raise RuntimeError("Writer was not released")
            return original(*args, **kwargs)

        with patch.object(manager, method, pause), ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(self.run_connection, "writer", action)
            retiring = None
            try:
                self.assertTrue(ready.wait(5), "Writer never reached persistence boundary")
                retiring = pool.submit(self.run_connection, "retirement", self.retire)
                self.assert_blocked("retirement", "writer", retiring)
            finally:
                release.set()
            result = writer.result(timeout=18)
            self.assertEqual(retiring.result(timeout=18).status_code, 200)
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_retired)
        return result

    def test_goal_holds_effective_category_until_saved_json_promise_commits(self):
        occurrence = self.assert_writer_commits_before_retirement(ChallengeGoal.objects, "create", self.goal)
        self.assertEqual(occurrence.snapshot["skill_tags"][0]["skill_id"], self.skill.pk)
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            self.goal()

    def test_private_quest_admits_catalog_table_before_reference_row_lock(self):
        response = self.assert_writer_commits_before_retirement(QuestSkillTag.objects, "bulk_create", self.private_quest)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(QuestSkillTag.objects.get().skill_id, self.skill.pk)
        self.assertEqual(self.private_quest().status_code, 400)

    def test_registered_private_quest_retag_admits_catalog_table_before_row_lock(self):
        definition = QuestDefinition.objects.create(name="Retag private", description="Synthetic", created_by=self.parent,
                                                    quest_type="collection", target_value=1)

        def retag():
            with override_user(self.parent):
                return async_to_sync(mcp.call_tool)("set_quest_definition_skill_tags", {"confirmation": True,
                    "params": {"quest_definition_id": definition.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}})

        result = self.assert_writer_commits_before_retirement(QuestSkillTag.objects, "bulk_create", retag)
        self.assertFalse(getattr(result, "isError", False), result)
        self.assertEqual(definition.skill_tags.get().skill_id, self.skill.pk)

    def test_retirement_first_blocks_definition_insert_then_rejects_and_rolls_back(self):
        ready, release = Event(), Event()
        original = SkillCategory.save

        def pause_after_retire(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            if instance.pk == self.category.pk and instance.is_retired:
                ready.set()
                if not release.wait(10):
                    raise RuntimeError("Retirement was not released")
            return result

        with patch.object(SkillCategory, "save", pause_after_retire), ThreadPoolExecutor(max_workers=2) as pool:
            retiring = pool.submit(self.run_connection, "retirement", self.retire)
            writer = None
            try:
                self.assertTrue(ready.wait(5), "Retirement never reached save boundary")
                writer = pool.submit(self.run_connection, "writer", self.private_quest)
                self.assert_blocked("writer", "retirement", writer)
            finally:
                release.set()
            self.assertEqual(retiring.result(timeout=18).status_code, 200)
            response = writer.result(timeout=18)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(QuestDefinition.objects.exists())
        self.assertFalse(QuestSkillTag.objects.exists())
