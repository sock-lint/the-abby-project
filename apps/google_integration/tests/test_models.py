"""Tests for google_integration models."""
from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from apps.google_integration.models import CalendarEventMapping, GoogleAccount
from apps.projects.models import User


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="child", password="pw", role="child")


class GoogleAccountTests(_Fixture):
    def test_create_google_account(self):
        account = GoogleAccount.objects.create(
            user=self.parent,
            google_id="google-123",
            google_email="parent@example.com",
            encrypted_credentials=b"encrypted-blob",
        )
        self.assertEqual(account.user, self.parent)
        self.assertEqual(account.google_email, "parent@example.com")
        self.assertFalse(account.calendar_sync_enabled)
        self.assertEqual(account.calendar_id, "primary")
        self.assertIsNone(account.linked_by)

    def test_one_to_one_with_user(self):
        GoogleAccount.objects.create(
            user=self.parent, google_id="g-1",
            google_email="a@x.com", encrypted_credentials=b"x",
        )
        with self.assertRaises(IntegrityError):
            GoogleAccount.objects.create(
                user=self.parent, google_id="g-2",
                google_email="b@x.com", encrypted_credentials=b"y",
            )

    def test_google_id_unique(self):
        GoogleAccount.objects.create(
            user=self.parent, google_id="g-same",
            google_email="a@x.com", encrypted_credentials=b"x",
        )
        with self.assertRaises(IntegrityError):
            GoogleAccount.objects.create(
                user=self.child, google_id="g-same",
                google_email="b@x.com", encrypted_credentials=b"y",
            )

    def test_linked_by_attribution(self):
        account = GoogleAccount.objects.create(
            user=self.child, google_id="child-g",
            google_email="child@x.com", encrypted_credentials=b"x",
            linked_by=self.parent,
        )
        self.assertEqual(account.linked_by, self.parent)
        self.assertIn(account, self.parent.linked_google_accounts.all())

    def test_str_rendering(self):
        account = GoogleAccount.objects.create(
            user=self.parent, google_id="g",
            google_email="parent@example.com", encrypted_credentials=b"",
        )
        self.assertIn("parent@example.com", str(account))


class CalendarEventMappingTests(_Fixture):
    def test_create_mapping(self):
        mapping = CalendarEventMapping.objects.create(
            user=self.parent,
            content_type="project_due",
            object_id=42,
            google_event_id="gevent-1",
        )
        self.assertEqual(mapping.content_type, "project_due")
        self.assertEqual(mapping.object_id, 42)

    def test_unique_per_user_type_object(self):
        CalendarEventMapping.objects.create(
            user=self.parent, content_type="chore", object_id=1,
            google_event_id="gev-1",
        )
        with self.assertRaises(IntegrityError):
            CalendarEventMapping.objects.create(
                user=self.parent, content_type="chore", object_id=1,
                google_event_id="gev-2",
            )

    def test_different_users_can_share_object(self):
        CalendarEventMapping.objects.create(
            user=self.parent, content_type="chore", object_id=1,
            google_event_id="a",
        )
        # Different user, same content — allowed.
        CalendarEventMapping.objects.create(
            user=self.child, content_type="chore", object_id=1,
            google_event_id="b",
        )
        self.assertEqual(CalendarEventMapping.objects.count(), 2)

    def test_str_rendering(self):
        m = CalendarEventMapping.objects.create(
            user=self.parent, content_type="chore", object_id=7,
            google_event_id="evid",
        )
        s = str(m)
        self.assertIn("chore:7", s)
        self.assertIn("evid", s)
