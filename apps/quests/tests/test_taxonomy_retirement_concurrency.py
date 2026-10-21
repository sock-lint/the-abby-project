"""New-reference admission and retirement have one PostgreSQL commit order."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

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

    def preview_fixture(self, definition):
        from apps.rpg.content.workbench import create_draft, save_draft
        draft = create_draft(self.staff, "Synthetic lock ordering preview")
        return save_draft(self.staff, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": definition.pk, "key": "display-edit",
            "values": {"description": "Synthetic description only"},
        }])

    def assert_reader_and_preview_complete(self, action, draft, patcher, ready, release):
        from apps.rpg.content.workbench import preview_draft
        with patcher, ThreadPoolExecutor(max_workers=2) as pool:
            reader = pool.submit(self.run_connection, "reader", action)
            preview = None
            try:
                self.assertTrue(ready.wait(5), "First high-category admission did not complete")
                preview = pool.submit(self.run_connection, "preview", lambda: preview_draft(
                    self.staff, draft["id"], draft["revision"],
                ))
                # Before the fix preview owns LOW and waits for HIGH. After
                # the fix reader owns both: preview waits before owning LOW.
                self.assert_blocked("preview", "reader", preview)
            finally:
                release.set()
            # Do not hide 40P01, lock-timeout, or worker errors as a passing
            # timing check. Both real service transactions must commit.
            result = reader.result(timeout=20)
            self.assertIsNotNone(preview)
            self.assertIn("revision", preview.result(timeout=20))
        return result

    def test_catalog_enrollment_and_preview_use_one_transaction_wide_category_order(self):
        from apps.quests import reference_locks
        from apps.quests.goals import list_goals
        high_category = SkillCategory.objects.create(name="Higher enrollment category")
        high_skill = Skill.objects.create(name="Higher enrollment skill", category=high_category)
        definitions = [QuestDefinition.objects.create(name=name, quest_type="collection", target_value=2,
            is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
            for name in ("A first high category", "B second low category")]
        for definition, skill in zip(definitions, (high_skill, self.skill)):
            QuestSkillTag.objects.create(quest_definition=definition, skill=skill, xp_weight=1)
        draft = self.preview_fixture(definitions[0])
        ready, release = Event(), Event()
        original = reference_locks.admit_definition_choices

        def pause_high(definition):
            result = original(definition)
            if definition.pk == definitions[0].pk:
                ready.set()
                if not release.wait(10):
                    raise RuntimeError("Enrollment was not released")
            return result

        result = self.assert_reader_and_preview_complete(lambda: list_goals(self.child), draft,
            patch.object(reference_locks, "admit_definition_choices", side_effect=pause_high), ready, release)
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(ChallengeGoal.objects.filter(user=self.child).count(), 2)

    def test_registered_template_cross_category_admissions_and_preview_share_the_order(self):
        from apps.rpg import taxonomy_references
        high_category = SkillCategory.objects.create(name="Higher template category")
        definition = QuestDefinition.objects.create(name="Preview-only quest", quest_type="collection", target_value=2,
            is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
        draft = self.preview_fixture(definition)
        ready, release = Event(), Event()
        original = taxonomy_references.admit_references

        def pause_high(model, ids, **kwargs):
            result = original(model, ids, **kwargs)
            if model is SkillCategory and set(ids) == {high_category.pk}:
                ready.set()
                if not release.wait(10):
                    raise RuntimeError("Template admission was not released")
            return result

        def create_template():
            with override_user(self.parent):
                return async_to_sync(mcp.call_tool)("create_template", {"params": {
                    "title": "Cross category template", "request_id": str(uuid4()), "category_id": high_category.pk,
                    "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
                }})

        result = self.assert_reader_and_preview_complete(create_template, draft,
            patch.object(taxonomy_references, "admit_references", side_effect=pause_high), ready, release)
        self.assertFalse(getattr(result, "isError", False), result)
        from apps.projects.models import ProjectTemplate
        template = ProjectTemplate.objects.get(title="Cross category template")
        self.assertEqual(template.category_id, high_category.pk)
        self.assertEqual(template.skill_tags.get().skill_id, self.skill.pk)

    def test_reverse_yaml_category_loader_and_enrollment_share_the_global_order(self):
        from apps.quests.goals import list_goals
        from apps.rpg.content.loader import ContentPack
        high_category = SkillCategory.objects.create(name="Higher source category")
        high_skill = Skill.objects.create(name="Higher source skill", category=high_category)
        for name, skill in (("A high source goal", high_skill), ("B low source goal", self.skill)):
            definition = QuestDefinition.objects.create(name=name, quest_type="collection", target_value=2,
                is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
            QuestSkillTag.objects.create(quest_definition=definition, skill=skill, xp_weight=1)
        # Parsed content is the normal loader input after YAML parsing. Its
        # source order deliberately differs from category primary-key order.
        parsed = {"skill_tree": {"categories": [
            {"name": high_category.name, "description": "Synthetic higher source update"},
            {"name": self.category.name, "description": "Synthetic lower source update"},
        ]}}
        ready, release = Event(), Event()
        original = ContentPack._upsert

        def pause_high(loader, model, **kwargs):
            result = original(loader, model, **kwargs)
            if model is SkillCategory and kwargs.get("name") == high_category.name:
                ready.set()
                if not release.wait(10):
                    raise RuntimeError("Source loader was not released")
            return result

        with TemporaryDirectory(prefix="taxonomy-loader-order-") as directory:
            with patch.object(ContentPack, "_upsert", new=pause_high), ThreadPoolExecutor(max_workers=2) as pool:
                loader = pool.submit(self.run_connection, "loader", lambda: ContentPack(
                    Path(directory), parsed_content=parsed,
                ).load())
                reader = None
                try:
                    self.assertTrue(ready.wait(5), "Source loader never completed its high-category update")
                    reader = pool.submit(self.run_connection, "reader", lambda: list_goals(self.child))
                    self.assert_blocked("reader", "loader", reader)
                finally:
                    release.set()
                loader.result(timeout=20)
                self.assertIsNotNone(reader)
                self.assertEqual(len(reader.result(timeout=20)["results"]), 2)
        self.category.refresh_from_db()
        high_category.refresh_from_db()
        self.assertEqual(self.category.description, "Synthetic lower source update")
        self.assertEqual(high_category.description, "Synthetic higher source update")
