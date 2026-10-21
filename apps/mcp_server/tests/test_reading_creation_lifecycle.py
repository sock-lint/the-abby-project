"""Reading responses must materialize before their family locks are released."""
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from mcp.types import CallToolResult
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.reading import services, views
from apps.reading.models import ReadingBook
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReadingCreationLifecycleTests(TransactionTestCase):
    def setUp(self):
        household = make_family(
            "Original readers", parents=[{"username": "reading-original-parent", "is_staff": True}],
            children=[{"username": "reading-moving-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        next_family = make_family(
            "Next readers", parents=[{"username": "reading-next-parent", "is_staff": True}],
        )
        self.next_parent = next_family.parents[0]
        self.book = ReadingBook.objects.create(
            user=self.child, title="Original title", author="Original author",
            client_request_id=uuid4(), create_payload={},
        )
        self.params = {
            "user_id": self.child.pk, "book": self.book.pk, "section": "Chapter 1",
            "client_request_id": str(uuid4()),
        }
        self.assertEqual(self.rest().status_code, 201)

    def rest(self, actor=None):
        request = APIRequestFactory().post("/api/reading-sessions/", self.params, format="json")
        force_authenticate(request, user=actor or self.parent)
        return views.ReadingSessionViewSet.as_view({"post": "create"})(request)

    def wire(self):
        with override_user(self.parent):
            result = async_to_sync(mcp.call_tool)("log_reading_session", {"params": self.params})
        if isinstance(result, CallToolResult):
            return result
        return CallToolResult(content=result[0], structuredContent=result[1])

    @contextmanager
    def after_replay_commit(self, callback):
        existing_request = services._existing_request
        fired = []

        def replay(*args, **kwargs):
            record = existing_request(*args, **kwargs)
            self.assertIsNotNone(record)
            self.assertTrue(connection.in_atomic_block)

            def committed():
                self.assertFalse(connection.in_atomic_block)
                callback()
                fired.append(True)

            transaction.on_commit(committed)
            return record

        with patch.object(services, "_existing_request", side_effect=replay):
            yield
        self.assertEqual(fired, [True])

    def move_and_edit(self):
        User.objects.filter(pk=self.child.pk).update(family_id=self.next_parent.family_id)
        moved = User.objects.get(pk=self.child.pk)
        services.update_reading_book(self.next_parent, moved, self.book.pk, {
            "title": "Next family's private title", "author": "Next family's private author",
        })

    def delete_child(self):
        User.objects.filter(pk=self.child.pk).delete()

    def assert_original_book(self, payload):
        self.assertEqual(payload["book_title"], "Original title")
        self.assertEqual(payload["book_author"], "Original author")
        self.assertIsNone(payload["reading_reward"])

    def test_rest_replay_cannot_disclose_a_post_commit_family_edit(self):
        with self.after_replay_commit(self.move_and_edit):
            response = self.rest()
        self.assertEqual(response.status_code, 200)
        self.assert_original_book(response.data)
        self.assertEqual(ReadingBook.objects.get(pk=self.book.pk).title, "Next family's private title")
        self.assertEqual(self.rest().status_code, 404)

    def test_registered_mcp_replay_cannot_disclose_a_post_commit_family_edit(self):
        with self.after_replay_commit(self.move_and_edit):
            response = self.wire()
        self.assertFalse(response.isError)
        self.assert_original_book(response.structuredContent)
        self.assertEqual(ReadingBook.objects.get(pk=self.book.pk).title, "Next family's private title")
        denied = self.wire()
        self.assertTrue(denied.isError)
        self.assertEqual(denied.structuredContent["error"]["code"], "not_found")

    def test_parent_rest_replay_retains_required_fields_on_account_deletion(self):
        self.assert_rest_deletion_response(self.parent)

    def test_child_rest_replay_retains_required_fields_on_account_deletion(self):
        self.assert_rest_deletion_response(self.child)

    def assert_rest_deletion_response(self, actor):
        with self.after_replay_commit(self.delete_child):
            response = self.rest(actor)
        self.assertEqual(response.status_code, 200)
        self.assert_original_book(response.data)
        self.assertFalse(ReadingBook.objects.filter(pk=self.book.pk).exists())

    def test_registered_mcp_replay_retains_its_contract_on_account_deletion(self):
        with self.after_replay_commit(self.delete_child):
            response = self.wire()
        self.assertFalse(response.isError)
        self.assert_original_book(response.structuredContent)
        self.assertFalse(ReadingBook.objects.filter(pk=self.book.pk).exists())
