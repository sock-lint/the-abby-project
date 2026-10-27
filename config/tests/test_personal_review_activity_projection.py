"""Personal activity displays match payouts and preserve the personal visit gap."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge
from apps.activity.models import ActivityEvent
from apps.chores.models import Chore, ChoreCompletion, ChoreSkillTag
from apps.notifications.models import Notification, NotificationType
from apps.payments.models import PaymentLedger
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PersonalActivityProjectionTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Activity projections", parents=[{"username": "parent"}, {"username": "coparent"}],
            children=[{"username": "child"}],
        )
        self.family = family.family
        self.parent, self.coparent = family.parents
        self.child = family.children[0]
        self.foreign = make_family("Other", parents=[{"username": "foreign"}]).parents[0]
        self.client.force_authenticate(self.parent)

    def personal(self, method, path, data=None):
        return getattr(self.client, method)(path, data, format="json", HTTP_X_ABBY_SPACE="personal")

    def chore(self, title="Existing own chore", owner=None, **kwargs):
        owner = owner or self.parent
        return Chore.objects.create(
            family=owner.family, assigned_to=owner, created_by=self.parent,
            title=title, reward_amount=Decimal("5.00"), coin_reward=4, xp_reward=12,
            **kwargs,
        )

    def test_personal_catalog_projects_zero_cash_without_changing_family_or_history(self):
        chore = self.chore()
        historical = ChoreCompletion.objects.create(
            chore=chore, user=self.parent, completed_date=timezone.localdate() - timedelta(days=1),
            status="approved", reward_amount_snapshot=Decimal("3.00"), coin_reward_snapshot=2,
        )
        for path in ("/api/chores/", f"/api/chores/{chore.pk}/"):
            with self.subTest(path=path):
                response = self.personal("get", path)
                self.assertEqual(response.status_code, 200, response.data)
                row = response.data[0] if isinstance(response.data, list) else response.data
                self.assertEqual(row["reward_amount"], "0.00")
                self.assertEqual((row["coin_reward"], row["xp_reward"]), (4, 12))
        chore.refresh_from_db()
        self.assertEqual(chore.reward_amount, Decimal("5.00"))
        family = self.client.get(f"/api/chores/{chore.pk}/")
        self.assertEqual(family.data["reward_amount"], "5.00")
        history = self.personal("get", f"/api/chore-completions/{historical.pk}/")
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(history.data["reward_amount_snapshot"], "3.00")

    def test_personal_dashboard_and_next_action_show_only_payable_rewards(self):
        chore = self.chore()
        response = self.personal("get", "/api/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        today = response.data["chores_today"][0]
        action = next(row for row in response.data["next_actions"] if row["id"] == chore.pk)
        with self.subTest(surface="today"):
            self.assertEqual(today["reward_amount"], "0.00")
            self.assertEqual(today["coin_reward"], 4)
        with self.subTest(surface="next_action"):
            self.assertEqual(action["reward"], {"money": "0.00", "coins": 4})
            self.assertNotIn("$", action["subtitle"])

    def test_unpayable_cash_does_not_rank_personal_chores_ahead(self):
        first = self.chore("A regular chore")
        Chore.objects.filter(pk=first.pk).update(reward_amount=0)
        second = self.chore("Z stored cash chore")
        response = self.personal("get", "/api/dashboard/")
        self.assertEqual([row["id"] for row in response.data["next_actions"]], [first.pk, second.pk])

    def test_child_cash_projection_and_cash_tiebreak_are_unchanged_even_with_header(self):
        first = self.chore("A regular child chore", self.child)
        Chore.objects.filter(pk=first.pk).update(reward_amount=0)
        second = self.chore("Z paid child chore", self.child)
        self.client.force_authenticate(self.child)
        for headers in ({}, {"HTTP_X_ABBY_SPACE": "personal"}):
            with self.subTest(headers=headers):
                response = self.client.get("/api/dashboard/", **headers)
                actions = response.data["next_actions"]
                self.assertEqual([row["id"] for row in actions], [second.pk, first.pk])
                self.assertEqual(actions[0]["reward"], {"money": "5.00", "coins": 4})
                self.assertIn("$5.00", actions[0]["subtitle"])
                chores = self.client.get("/api/chores/", **headers).data
                self.assertEqual(next(row for row in chores if row["id"] == second.pk)["reward_amount"], "5.00")

    def test_personal_completion_has_no_cash_claim_and_keeps_coins_and_xp(self):
        chore = self.chore()
        category = SkillCategory.objects.create(name="Practice")
        skill = Skill.objects.create(name="Drawing", category=category)
        ChoreSkillTag.objects.create(chore=chore, skill=skill)
        response = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "approved")
        self.assertEqual(response.data["reward_amount_snapshot"], "0.00")
        self.assertFalse(PaymentLedger.objects.filter(user=self.parent).exists())
        self.assertEqual(list(CoinLedger.objects.filter(user=self.parent, reason="chore_reward").values_list("amount", flat=True)), [4])
        self.assertGreaterEqual(SkillProgress.objects.get(user=self.parent, skill=skill).xp_points, 12)
        note = Notification.objects.get(user=self.parent, notification_type=NotificationType.CHORE_APPROVED)
        with self.subTest(surface="notification"):
            self.assertNotIn("$", note.message)
            self.assertIn(chore.title, note.message)
        with self.subTest(surface="submission_audit"):
            event = ActivityEvent.objects.get(subject=self.parent, event_type="chore.submit")
            self.assertEqual(Decimal(event.context["extras"]["reward_snapshot"]), 0)
            reward_note = next(row for row in event.context["breakdown"] if row["label"] == "reward")
            self.assertEqual(Decimal(reward_note["value"]), 0)

    def test_child_submission_and_approval_keep_cash_snapshot_and_notification(self):
        chore = self.chore(owner=self.child)
        self.client.force_authenticate(self.child)
        submitted = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self.assertEqual(submitted.data["status"], "pending")
        self.assertEqual(submitted.data["reward_amount_snapshot"], "5.00")
        self.assertFalse(PaymentLedger.objects.exists())
        self.client.force_authenticate(self.parent)
        approved = self.client.post(f"/api/chore-completions/{submitted.data['id']}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(PaymentLedger.objects.get(user=self.child).amount, Decimal("5.00"))
        note = Notification.objects.get(user=self.child, notification_type=NotificationType.CHORE_APPROVED)
        self.assertIn("$5.00", note.message)

    def test_paused_personal_chore_remains_editable_and_cannot_complete_until_reenabled(self):
        chore = self.chore()
        paused = self.personal("patch", f"/api/chores/{chore.pk}/", {"is_active": False})
        self.assertEqual(paused.status_code, 200, paused.data)
        listed = self.personal("get", "/api/chores/")
        with self.subTest(surface="editable_list"):
            self.assertEqual([row["id"] for row in listed.data], [chore.pk])
            self.assertFalse(listed.data[0]["is_active"])
            self.assertFalse(listed.data[0]["is_available"])
        self.assertEqual(self.personal("post", f"/api/chores/{chore.pk}/complete/").status_code, 400)
        self.assertFalse(ChoreCompletion.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
        dashboard = self.personal("get", "/api/dashboard/").data
        self.assertEqual(dashboard["chores_today"], [])
        self.assertEqual(dashboard["next_actions"], [])
        enabled = self.personal("patch", f"/api/chores/{chore.pk}/", {"is_active": True})
        self.assertEqual(enabled.status_code, 200, enabled.data)
        self.assertTrue(self.personal("get", "/api/chores/").data[0]["is_available"])
        self.assertEqual(self.personal("post", f"/api/chores/{chore.pk}/complete/").status_code, 201)

    def test_inactive_personal_list_preserves_proposal_filter_and_owner_boundaries(self):
        inactive = self.chore("Own paused", is_active=False)
        pending = self.chore("Own proposal", is_active=False, pending_parent_review=True)
        for owner in (self.child, self.coparent, self.foreign):
            for proposal in (False, True):
                self.chore(f"Other paused {owner.pk} {proposal}", owner, is_active=False, pending_parent_review=proposal)
        Chore.objects.create(family=self.family, title="Shared paused", created_by=self.parent, is_active=False)
        listed = self.personal("get", "/api/chores/")
        self.assertEqual([row["id"] for row in listed.data], [inactive.pk])
        proposals = self.personal("get", "/api/chores/?pending=true")
        self.assertEqual([row["id"] for row in proposals.data["results"]], [pending.pk])
        self.assertFalse(proposals.data["results"][0]["is_available"])
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/chores/").data, [])
        self.client.force_authenticate(self.parent)
        family_ids = {row["id"] for row in self.client.get("/api/chores/").data["results"]}
        self.assertIn(inactive.pk, family_ids)
        self.assertIn(pending.pk, family_ids)
        self.assertFalse(ChoreCompletion.objects.exists())

    def test_offweek_personal_chore_remains_editable_without_becoming_available(self):
        chore = self.chore(
            "Own alternating chore", week_schedule="alternating",
            schedule_start_date=timezone.localdate() - timedelta(days=7),
        )
        listed = self.personal("get", "/api/chores/")
        with self.subTest(surface="editable_list"):
            self.assertEqual([row["id"] for row in listed.data], [chore.pk])
            self.assertTrue(listed.data[0]["is_active"])
            self.assertFalse(listed.data[0]["is_available"])
            self.assertIsNone(listed.data[0]["today_status"])
        self.assertEqual(self.personal("post", f"/api/chores/{chore.pk}/complete/").status_code, 400)
        self.assertFalse(ChoreCompletion.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
        self.assertFalse(PaymentLedger.objects.exists())
        dashboard = self.personal("get", "/api/dashboard/").data
        self.assertEqual(dashboard["chores_today"], [])
        self.assertEqual(dashboard["next_actions"], [])
        edited = self.personal("patch", f"/api/chores/{chore.pk}/", {"title": "Edited alternating chore"})
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(self.personal("delete", f"/api/chores/{chore.pk}/").status_code, 204)

    def test_completed_one_time_personal_chore_stays_editable_with_saved_status(self):
        chore = self.chore("Own one-time chore", recurrence="one_time")
        completed = self.personal("post", f"/api/chores/{chore.pk}/complete/")
        self.assertEqual(completed.status_code, 201, completed.data)
        self.assertEqual(completed.data["status"], "approved")
        ChoreCompletion.objects.filter(pk=completed.data["id"]).update(
            completed_date=timezone.localdate() - timedelta(days=2),
        )
        coin_count = CoinLedger.objects.filter(user=self.parent).count()
        listed = self.personal("get", "/api/chores/")
        with self.subTest(surface="editable_list"):
            self.assertEqual([row["id"] for row in listed.data], [chore.pk])
            self.assertFalse(listed.data[0]["is_available"])
            self.assertEqual(listed.data[0]["today_status"], "approved")
            self.assertEqual(listed.data[0]["today_completion_id"], completed.data["id"])
        self.assertEqual(self.personal("post", f"/api/chores/{chore.pk}/complete/").status_code, 400)
        self.assertEqual(ChoreCompletion.objects.filter(chore=chore).count(), 1)
        self.assertEqual(CoinLedger.objects.filter(user=self.parent).count(), coin_count)
        self.assertFalse(PaymentLedger.objects.exists())
        dashboard = self.personal("get", "/api/dashboard/").data
        self.assertEqual(dashboard["chores_today"], [])
        self.assertEqual(dashboard["next_actions"], [])
        edited = self.personal("patch", f"/api/chores/{chore.pk}/", {"description": "Kept for reference"})
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(self.personal("delete", f"/api/chores/{chore.pk}/").status_code, 204)

    def test_personal_catalog_retention_keeps_child_family_and_proposal_scopes(self):
        offweek = self.chore("Own offweek", week_schedule="alternating",
                             schedule_start_date=timezone.localdate() - timedelta(days=7))
        pending = self.chore("Own pending", pending_parent_review=True)
        for owner in (self.child, self.coparent, self.foreign):
            self.chore(f"Other offweek {owner.pk}", owner, week_schedule="alternating",
                       schedule_start_date=timezone.localdate() - timedelta(days=7))
            self.chore(f"Other one-time {owner.pk}", owner, recurrence="one_time", is_active=False)
        Chore.objects.create(family=self.family, created_by=self.parent, title="Shared published")
        with self.subTest(surface="personal_published"):
            self.assertEqual([row["id"] for row in self.personal("get", "/api/chores/").data], [offweek.pk])
        self.assertEqual([row["id"] for row in self.personal("get", "/api/chores/?pending=true").data["results"]], [pending.pk])
        family_rows = self.client.get("/api/chores/").data["results"]
        self.assertIn(offweek.pk, [row["id"] for row in family_rows])
        self.assertIn(pending.pk, [row["id"] for row in family_rows])
        self.assertFalse(any(row["assigned_to"] == self.foreign.pk for row in family_rows))
        self.client.force_authenticate(self.child)
        child_rows = self.personal("get", "/api/chores/").data
        self.assertEqual([row["title"] for row in child_rows], ["Shared published"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PersonalVisitProjectionTests(APITestCase):
    def setUp(self):
        family = make_family("Visit gap", parents=[{"username": "parent"}], children=[{"username": "child"}])
        self.parent = family.parents[0]
        self.child = family.children[0]

    def authenticate_fresh(self, user):
        user.refresh_from_db()
        self.client.force_authenticate(user)

    def test_background_family_refresh_preserves_personal_gap_until_my_space_is_opened(self):
        last_seen = timezone.now() - timedelta(days=2)
        get_user_model().objects.filter(pk=self.parent.pk).update(last_seen_at=last_seen)
        badge = Badge.objects.create(name="Saved badge", criteria_type="first_project")
        UserBadge.objects.create(user=self.parent, badge=badge)
        CoinLedger.objects.create(user=self.parent, amount=9, reason="adjustment")
        CoinLedger.objects.create(user=self.parent, amount=-3, reason="redemption")
        Notification.objects.create(user=self.parent, title="Approved work", notification_type=NotificationType.CHORE_APPROVED)
        for _ in range(2):
            self.authenticate_fresh(self.parent)
            family = self.client.get("/api/dashboard/")
            self.assertEqual(family.status_code, 200, family.data)
            self.assertNotIn("since_last_visit", family.data)
        with self.subTest(surface="family_visit_marker"):
            self.parent.refresh_from_db()
            self.assertEqual(self.parent.last_seen_at, last_seen)
        self.authenticate_fresh(self.parent)
        personal = self.client.get("/api/dashboard/", HTTP_X_ABBY_SPACE="personal")
        with self.subTest(surface="personal_catchup"):
            self.assertEqual(personal.data["since_last_visit"], {
                "last_seen_at": last_seen.isoformat(), "badges_earned": 1, "coins_earned": 9, "approvals": 1,
            })
        self.authenticate_fresh(self.parent)
        self.assertGreater(self.parent.last_seen_at, last_seen)
        again = self.client.get("/api/dashboard/", HTTP_X_ABBY_SPACE="personal")
        self.assertEqual({key: value for key, value in again.data["since_last_visit"].items() if key != "last_seen_at"},
                         {"badges_earned": 0, "coins_earned": 0, "approvals": 0})

    def test_child_dashboard_continues_stamping_with_or_without_personal_hint(self):
        last_seen = timezone.now() - timedelta(days=2)
        for headers in ({}, {"HTTP_X_ABBY_SPACE": "personal"}):
            with self.subTest(headers=headers):
                get_user_model().objects.filter(pk=self.child.pk).update(last_seen_at=last_seen)
                self.authenticate_fresh(self.child)
                response = self.client.get("/api/dashboard/", **headers)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["since_last_visit"]["last_seen_at"], last_seen.isoformat())
                self.child.refresh_from_db()
                self.assertGreater(self.child.last_seen_at, last_seen)
