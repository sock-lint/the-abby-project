"""The feedback adapter retains fresh household authority through native reads."""
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, override_settings
from mcp.server.fastmcp.exceptions import ToolError

from apps.families.models import Family

from . import test_voyager_feedback_tool as fixtures


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class VoyagerFeedbackAuthorityTests(TransactionTestCase):
    setUp = fixtures.VoyagerFeedbackToolTests.setUp
    invoke = fixtures.VoyagerFeedbackToolTests.invoke
    saved_window = fixtures.VoyagerFeedbackToolTests.saved_window

    def test_native_report_runs_after_household_and_observer_locks(self):
        from apps.quests import voyager_feedback
        original = QuerySet.select_for_update
        authorize = voyager_feedback._authorized_observer
        locked = []

        def lock(query, *args, **kwargs):
            locked.append(query.model._meta.label_lower)
            return original(query, *args, **kwargs)

        def observe(actor):
            self.assertTrue(connection.in_atomic_block)
            self.assertIn("families.family", locked)
            self.assertIn("accounts.user", locked)
            return authorize(actor)

        with patch.object(QuerySet, "select_for_update", lock), patch.object(voyager_feedback, "_authorized_observer", observe):
            result = self.invoke()
        self.assertEqual(result["status"], "observations_available")

    def test_revocation_prevents_entry_into_native_report_even_with_stale_context(self):
        user = get_user_model().objects.filter(pk=self.parent.pk)
        for values in ({"is_staff": False}, {"is_active": False}, {"role": "child"}, {"family_id": self.other_parent.family_id}):
            with self.subTest(values=values):
                user.update(**values)
                try:
                    with patch("apps.quests.voyager_feedback.voyager_feedback", side_effect=AssertionError("Stale actor reached native report")) as native:
                        with self.assertRaisesRegex(ToolError, "permissions have changed"):
                            self.invoke()
                        native.assert_not_called()
                finally:
                    user.update(is_staff=True, is_active=True, role="parent", family_id=self.parent.family_id)

    @skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
    def test_revocation_committed_while_feedback_waits_on_household_lock_is_denied(self):
        attempting = Event()
        original = QuerySet.select_for_update

        def lock(query, *args, **kwargs):
            if query.model is Family:
                attempting.set()
            return original(query, *args, **kwargs)

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                Family.objects.select_for_update().get(pk=self.parent.family_id)
                get_user_model().objects.filter(pk=self.parent.pk).update(is_staff=False)
                with patch.object(QuerySet, "select_for_update", lock):
                    result = executor.submit(self.invoke)
                    self.assertTrue(attempting.wait(timeout=5), "Feedback bypassed the household lock")
                    self.assertFalse(result.done(), "Feedback returned before the pending revocation committed")
            with self.assertRaisesRegex(ToolError, "permissions have changed"):
                result.result(timeout=10)
