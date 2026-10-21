"""Private quest category filters cannot race taxonomy deletion."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.achievements.models import Badge, SkillCategory
from apps.achievements.serializers import BadgeWriteSerializer
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.models import QuestDefinition
from apps.quests.serializers import QuestWriteSerializer
from apps.rpg.content.taxonomy_deletion import TaxonomyInUse, delete_taxonomy
from config.tests.factories import make_family


class CategoryFixtures:
    def setUp(self):
        own = make_family(parents=[{"username": "category-reference-parent", "is_staff": True}])
        other = make_family(parents=[{"username": "category-reference-deleter", "is_staff": True}])
        self.parent, self.deleter = own.parents[0], other.parents[0]
        self.category = SkillCategory.objects.create(name="Private category filter")
        self.payload = {"name": "Private category quest", "description": "Synthetic", "quest_type": "collection",
                        "target_value": 1, "trigger_filter": {"skill_category_id": self.category.pk}}

    def rest(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        return client.post("/api/quests/", self.payload, format="json")

    def wire(self, request_id=None):
        with override_user(self.parent):
            return async_to_sync(mcp.call_tool)("create_quest_definition", {
                "params": {**self.payload, "request_id": str(request_id or uuid4())},
            })


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryReferenceValidationTests(CategoryFixtures, TestCase):
    def test_rest_rechecks_category_after_request_validation_and_rolls_back_definition(self):
        original = QuestWriteSerializer.is_valid

        def validate_then_delete(serializer, **kwargs):
            result = original(serializer, **kwargs)
            SkillCategory.objects.filter(pk=self.category.pk).delete()
            return result

        with patch.object(QuestWriteSerializer, "is_valid", validate_then_delete):
            response = self.rest()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(QuestDefinition.objects.exists())

    def test_registered_mcp_rechecks_category_and_rolls_back_definition_and_receipt(self):
        from apps.mcp_server.models import MCPMutationReceipt
        from apps.mcp_server.tools import quests
        original = quests.validate_trigger_filter

        def validate_then_delete(value):
            result = original(value)
            SkillCategory.objects.filter(pk=self.category.pk).delete()
            return result

        with patch.object(quests, "validate_trigger_filter", validate_then_delete):
            result = self.wire()
        self.assertTrue(getattr(result, "isError", False))
        self.assertEqual(result.structuredContent["error"]["code"], "invalid_request")
        self.assertFalse(QuestDefinition.objects.exists())
        self.assertFalse(MCPMutationReceipt.objects.exists())

    def test_mcp_uuid_replay_precedes_new_reference_validation(self):
        request_id = uuid4()
        first = self.wire(request_id)
        self.assertFalse(getattr(first, "isError", False))
        # Simulate pre-guard legacy/operator removal, not a permitted API delete.
        SkillCategory.objects.filter(pk=self.category.pk).delete()
        retry = self.wire(request_id)
        self.assertFalse(getattr(retry, "isError", False))
        first_data = first.structuredContent if hasattr(first, "structuredContent") else first[1]
        retry_data = retry.structuredContent if hasattr(retry, "structuredContent") else retry[1]
        self.assertEqual(retry_data, first_data)
        self.assertEqual(QuestDefinition.objects.count(), 1)

    def test_rest_badge_create_rechecks_revoked_staff_after_validation(self):
        original = BadgeWriteSerializer.is_valid

        def validate_then_revoke(serializer, **kwargs):
            result = original(serializer, **kwargs)
            User.objects.filter(pk=self.parent.pk).update(is_staff=False)
            return result

        client = APIClient()
        client.force_authenticate(self.parent)
        with patch.object(BadgeWriteSerializer, "is_valid", validate_then_revoke):
            response = client.post("/api/badges/", {"name": "New named category badge", "description": "Rule",
                "criteria_type": "category_mastery", "criteria_value": {"category": self.category.name}}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Badge.objects.exists())

    def test_rest_badge_update_rechecks_revoked_staff_after_validation(self):
        badge = Badge.objects.create(name="Original badge", description="Rule", criteria_type="first_project")
        original = BadgeWriteSerializer.is_valid

        def validate_then_revoke(serializer, **kwargs):
            result = original(serializer, **kwargs)
            User.objects.filter(pk=self.parent.pk).update(is_active=False)
            return result

        client = APIClient()
        client.force_authenticate(self.parent)
        with patch.object(BadgeWriteSerializer, "is_valid", validate_then_revoke):
            response = client.patch(f"/api/badges/{badge.pk}/", {"name": "Must not save"}, format="json")
        self.assertEqual(response.status_code, 403)
        badge.refresh_from_db()
        self.assertEqual(badge.name, "Original badge")

    def test_named_badge_rules_keep_existing_unknown_name_authoring_contract(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post("/api/badges/", {"name": "Future category badge", "description": "Rule",
            "criteria_type": "category_mastery", "criteria_value": {"category": "Category not installed yet"}}, format="json")
        self.assertEqual(response.status_code, 201)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CategoryReferenceConcurrencyTests(CategoryFixtures, TransactionTestCase):
    def assert_writer_blocks_delete(self, callback, model=QuestDefinition):
        ready, release, deletion_done = Event(), Event(), Event()
        pids = {}
        original = model.objects.create

        def pause_after_insert(*args, **kwargs):
            record = original(*args, **kwargs)
            ready.set()
            if not release.wait(8):
                raise RuntimeError("Writer not released")
            return record

        def run(role, action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '6s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[role] = cursor.fetchone()[0]
                return action()
            finally:
                if role == "delete":
                    deletion_done.set()
                connections.close_all()

        def delete():
            try:
                delete_taxonomy(self.deleter, SkillCategory, self.category.pk)
                return "deleted"
            except TaxonomyInUse:
                return "in_use"

        blocked = False
        with patch.object(model.objects, "create", pause_after_insert), ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(run, "writer", callback)
            self.assertTrue(ready.wait(5))
            deletion = pool.submit(run, "delete", delete)
            try:
                deadline = monotonic() + 5
                while monotonic() < deadline and not deletion_done.is_set():
                    if "delete" in pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [pids["writer"], pids["delete"]])
                            blocked = cursor.fetchone()[0]
                        if blocked:
                            break
                    deletion_done.wait(0.01)
            finally:
                release.set()
            response = writer.result(timeout=15)
            self.assertEqual(deletion.result(timeout=15), "in_use")
        self.assertTrue(blocked)
        self.assertTrue(SkillCategory.objects.filter(pk=self.category.pk).exists())
        return response

    def test_private_rest_insert_obtains_definition_table_before_category_reference(self):
        self.assertEqual(self.assert_writer_blocks_delete(self.rest).status_code, 201)

    def test_registered_private_mcp_insert_commits_before_category_delete_rechecks(self):
        self.assertFalse(getattr(self.assert_writer_blocks_delete(self.wire), "isError", False))

    def test_badge_rest_catalog_write_fence_serializes_named_category_reference(self):
        def create():
            client = APIClient()
            client.force_authenticate(self.parent)
            return client.post("/api/badges/", {"name": "Protected category rule", "description": "Rule",
                "criteria_type": "category_mastery", "criteria_value": {"category": self.category.name}}, format="json")

        self.assertEqual(self.assert_writer_blocks_delete(create, Badge).status_code, 201)

    def assert_delete_first_rejects_writer(self, callback, *, mcp_writer):
        from apps.rpg.content import taxonomy_deletion as deletion
        locked, release, writer_started = Event(), Event(), Event()
        pids = {}
        original = deletion._has_incoming_relation

        def check(obj):
            locked.set()
            if not release.wait(8):
                raise RuntimeError("Delete was not released")
            return original(obj)

        def run(role, action):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '6s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[role] = cursor.fetchone()[0]
                if role == "writer":
                    writer_started.set()
                return action()
            finally:
                connections.close_all()

        blocked = False
        with patch.object(deletion, "_has_incoming_relation", side_effect=check), ThreadPoolExecutor(max_workers=2) as pool:
            deleter = pool.submit(run, "delete", lambda: delete_taxonomy(self.deleter, SkillCategory, self.category.pk))
            writer = None
            try:
                self.assertTrue(locked.wait(5))
                writer = pool.submit(run, "writer", callback)
                self.assertTrue(writer_started.wait(5))
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [pids["delete"], pids["writer"]])
                        blocked = cursor.fetchone()[0]
                    if blocked or writer.done():
                        break
                    release.wait(0.01)
            finally:
                release.set()
            self.assertEqual(deleter.result(timeout=15), self.category.pk)
            self.assertIsNotNone(writer)
            response = writer.result(timeout=15)
        self.assertTrue(blocked, "Definition INSERT did not wait behind catalog deletion")
        if mcp_writer:
            self.assertTrue(response.isError)
            self.assertEqual(response.structuredContent["error"]["code"], "invalid_request")
        else:
            self.assertEqual(response.status_code, 400)
        self.assertFalse(SkillCategory.objects.filter(pk=self.category.pk).exists())
        self.assertFalse(QuestDefinition.objects.exists())

    def test_delete_first_rolls_back_private_rest_definition_after_table_lock_wait(self):
        self.assert_delete_first_rejects_writer(self.rest, mcp_writer=False)

    def test_delete_first_rolls_back_registered_mcp_definition_after_table_lock_wait(self):
        self.assert_delete_first_rejects_writer(self.wire, mcp_writer=True)
