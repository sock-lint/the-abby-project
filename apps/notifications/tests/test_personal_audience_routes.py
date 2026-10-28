"""Saved notifications and push links select the recipient's actual workspace."""
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.chronicle.models import ChronicleComment, ChronicleEntry
from apps.chores.models import Chore, ChoreCompletion
from apps.notifications.models import Notification, NotificationType
from apps.payments.models import PaymentLedger
from apps.payments.services import PaymentService
from apps.projects.savings_service import SavingsGoalService
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PersonalNotificationAudienceTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Notification audience", parents=[{"username": "parent"}, {"username": "coparent"}],
            children=[{"username": "child"}, {"username": "sibling"}],
        )
        self.parent, self.coparent = family.parents
        self.child, self.sibling = family.children
        self.foreign = make_family("Other", parents=[{"username": "foreign"}]).parents[0]

    def entry(self, owner, *, kind="journal", private=False):
        today = timezone.localdate()
        return ChronicleEntry.objects.create(
            user=owner, kind=kind, occurred_on=today,
            chapter_year=today.year if today.month >= 8 else today.year - 1,
            is_private=private, title="Sensitive memory title", summary="Sensitive memory body",
        )

    def reply(self, actor, entry):
        self.client.force_authenticate(actor)
        return self.client.post(f"/api/chronicle/entries/{entry.pk}/comments/", {
            "body": "Sensitive reply text",
        }, format="json")

    def assert_safe_memory_notice(self, notification):
        text = notification.title + notification.message + notification.link
        for secret in ("Sensitive memory title", "Sensitive memory body", "Sensitive reply text"):
            self.assertNotIn(secret, text)
        self.assertNotIn("token", notification.link)

    def push_routes(self, push, notification_type):
        return {call.args[0]: call.args[3] for call in push.call_args_list
                if call.args[4] == notification_type}

    def assert_child_reply_routes(self, kind):
        entry = self.entry(self.child, kind=kind)
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push:
            response = self.reply(self.child, entry)
        self.assertEqual(response.status_code, 201, response.data)
        tab = "grades" if kind == "grade" else "journal"
        expected = f"/chronicle?tab={tab}&child={self.child.pk}&space=family"
        notices = Notification.objects.filter(notification_type=NotificationType.JOURNAL_REPLY)
        self.assertEqual(set(notices.values_list("user_id", flat=True)), {self.parent.pk, self.coparent.pk})
        for notice in notices:
            with self.subTest(recipient=notice.user_id):
                self.assertEqual(notice.link, expected)
                self.assert_safe_memory_notice(notice)
        self.assertEqual(self.push_routes(push, NotificationType.JOURNAL_REPLY), {
            self.parent.pk: expected, self.coparent.pk: expected,
        })
        self.assertFalse(Notification.objects.filter(user__in=[self.foreign, self.sibling]).exists())

    def test_child_journal_reply_opens_each_parents_family_journal(self):
        self.assert_child_reply_routes("journal")

    def test_child_grade_reply_opens_each_parents_family_grades(self):
        self.assert_child_reply_routes("grade")

    def test_coparent_reply_to_shared_parent_journal_opens_owners_personal_journal(self):
        entry = self.entry(self.parent)
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push:
            response = self.reply(self.coparent, entry)
        self.assertEqual(response.status_code, 201, response.data)
        note = Notification.objects.get(notification_type=NotificationType.JOURNAL_REPLY)
        self.assertEqual(note.user_id, self.parent.pk)
        with self.subTest(surface="saved_destination"):
            self.assertEqual(note.link, "/chronicle?tab=journal&space=personal")
        with self.subTest(surface="push_destination"):
            self.assertEqual(self.push_routes(push, NotificationType.JOURNAL_REPLY), {
                self.parent.pk: "/chronicle?tab=journal&space=personal",
            })
        self.assert_safe_memory_notice(note)
        self.client.force_authenticate(self.parent)
        hidden = self.client.patch(f"/api/chronicle/{entry.pk}/journal/", {"is_private": True}, format="json")
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.client.force_authenticate(self.coparent)
        self.assertEqual(self.client.get(f"/api/chronicle/entries/{entry.pk}/comments/").status_code, 404)
        self.assertEqual(ChronicleComment.objects.filter(entry=entry).count(), 1)

    def test_parent_reply_to_child_keeps_child_link_without_space_hint(self):
        response = self.reply(self.parent, self.entry(self.child))
        self.assertEqual(response.status_code, 201, response.data)
        note = Notification.objects.get(notification_type=NotificationType.JOURNAL_REPLY)
        self.assertEqual(note.user_id, self.child.pk)
        self.assertEqual(note.link, "/chronicle?tab=journal")
        self.assert_safe_memory_notice(note)

    def test_journal_destination_does_not_grant_private_or_foreign_comment_access(self):
        private = self.entry(self.parent, private=True)
        child_shared = self.entry(self.child)
        for actor, entry in ((self.coparent, private), (self.child, private),
                             (self.foreign, private), (self.foreign, child_shared),
                             (self.sibling, child_shared)):
            with self.subTest(actor=actor.pk, entry=entry.pk):
                self.assertEqual(self.reply(actor, entry).status_code, 404)
        self.assertFalse(ChronicleComment.objects.exists())
        self.assertFalse(Notification.objects.filter(notification_type=NotificationType.JOURNAL_REPLY).exists())

    def complete_savings_goal(self, owner):
        goal = SavingsGoalService.create_goal(owner, title="New bike", target_amount=Decimal("25.00"))
        PaymentService.record_entry(owner, Decimal("25.00"), PaymentLedger.EntryType.ADJUSTMENT,
                                    description="Saved test balance", created_by=self.parent)
        SavingsGoalService.check_and_complete(owner)
        goal.refresh_from_db()
        self.assertTrue(goal.is_completed)
        self.assertEqual(CoinLedger.objects.get(user=owner, description="Savings goal: New bike").amount, 50)
        self.assertEqual(PaymentLedger.objects.filter(user=owner).count(), 1)

    def test_child_savings_receipt_stays_personal_and_family_copies_open_child_overview(self):
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push, self.captureOnCommitCallbacks(execute=True):
            self.complete_savings_goal(self.child)
        expected = f"/family?child={self.child.pk}"
        notes = Notification.objects.filter(notification_type=NotificationType.SAVINGS_GOAL_COMPLETED)
        self.assertEqual(notes.count(), 3)
        self.assertEqual(notes.get(user=self.child).link, "/treasury?tab=hoards")
        for parent in (self.parent, self.coparent):
            with self.subTest(recipient=parent.pk):
                self.assertEqual(notes.get(user=parent).link, expected)
        self.assertEqual(self.push_routes(push, NotificationType.SAVINGS_GOAL_COMPLETED), {
            self.child.pk: "/treasury?tab=hoards", self.parent.pk: expected, self.coparent.pk: expected,
        })
        self.assertFalse(Notification.objects.filter(user__in=[self.foreign, self.sibling]).exists())

    def test_parent_savings_owner_receipt_opens_hoards_and_existing_family_copies_stay_family(self):
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push, self.captureOnCommitCallbacks(execute=True):
            self.complete_savings_goal(self.parent)
        notes = Notification.objects.filter(user=self.parent, notification_type=NotificationType.SAVINGS_GOAL_COMPLETED)
        with self.subTest(surface="owner_destination"):
            self.assertEqual(set(notes.values_list("link", flat=True)), {"/treasury?tab=hoards&space=personal", "/family"})
        with self.subTest(surface="push_destination"):
            routes = [(call.args[0], call.args[3]) for call in push.call_args_list
                      if call.args[4] == NotificationType.SAVINGS_GOAL_COMPLETED]
            self.assertCountEqual(routes, [(self.parent.pk, "/treasury?tab=hoards&space=personal"),
                                           (self.parent.pk, "/family"), (self.coparent.pk, "/family")])
        with self.subTest(surface="audience"):
            self.assertEqual(notes.count(), 2)
            self.assertEqual(Notification.objects.get(
                user=self.coparent, notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
            ).link, "/family")
            self.assertFalse(Notification.objects.filter(
                user__in=[self.child, self.sibling, self.foreign],
                notification_type=NotificationType.SAVINGS_GOAL_COMPLETED,
            ).exists())

    def test_parent_personal_chore_receipt_opens_own_chores(self):
        chore = Chore.objects.create(family=self.parent.family, created_by=self.parent,
                                     assigned_to=self.parent, title="My tidy", coin_reward=4)
        self.client.force_authenticate(self.parent)
        with patch("apps.notifications.push.push_enabled", return_value=True), patch(
            "apps.notifications.tasks.send_push_notification.delay",
        ) as push:
            completed = self.client.post(f"/api/chores/{chore.pk}/complete/", {}, format="json",
                                         HTTP_X_ABBY_SPACE="personal")
        self.assertEqual(completed.status_code, 201, completed.data)
        self.assertEqual(completed.data["status"], "approved")
        self.assertEqual(ChoreCompletion.objects.filter(chore=chore).count(), 1)
        self.assertFalse(PaymentLedger.objects.exists())
        note = Notification.objects.get(notification_type=NotificationType.CHORE_APPROVED)
        self.assertEqual(note.user_id, self.parent.pk)
        with self.subTest(surface="saved_destination"):
            self.assertEqual(note.link, "/chores?space=personal")
        with self.subTest(surface="push_destination"):
            self.assertEqual(self.push_routes(push, NotificationType.CHORE_APPROVED), {
                self.parent.pk: "/chores?space=personal",
            })

    def test_child_chore_approval_keeps_child_own_destination(self):
        chore = Chore.objects.create(family=self.child.family, created_by=self.parent,
                                     assigned_to=self.child, title="Child tidy", coin_reward=4)
        self.client.force_authenticate(self.child)
        submitted = self.client.post(f"/api/chores/{chore.pk}/complete/", {}, format="json")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self.assertEqual(submitted.data["status"], "pending")
        self.client.force_authenticate(self.parent)
        approved = self.client.post(f"/api/chore-completions/{submitted.data['id']}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        note = Notification.objects.get(notification_type=NotificationType.CHORE_APPROVED)
        self.assertEqual(note.user_id, self.child.pk)
        self.assertEqual(note.link, "/chores")
