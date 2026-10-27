"""Shared parent dashboard fixture comes from the actual scoped endpoint."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, UserBadge
from apps.chores.models import Chore, ChoreCompletion
from apps.homework.models import HomeworkAssignment, HomeworkSubmission
from apps.projects.models import Project
from apps.quests.models import ChallengeGoal, ChallengeOccurrence
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared_fixtures


FIXED_NOW = datetime(2026, 10, 19, 2, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class ParentApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def test_pet_evolution_notifications_keep_personal_and_child_family_destinations(self):
        from apps.notifications.models import Notification
        from apps.pets.models import PetSpecies, PotionType, UserPet
        from apps.pets.services import PetService

        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            household = make_family(
                "Companion Notification Fixture", family_id=65,
                parents=[{"id": 6, "username": "pet-fixture-parent", "display_name": "Alex"},
                         {"id": 8, "username": "pet-fixture-coparent"}],
                children=[{"id": 7, "username": "pet-fixture-child", "display_name": "Abby"}],
            )
            parent, child = household.parents[0], household.children[0]
            outsider = make_family(
                "Other Companion Fixture", family_id=66,
                parents=[{"id": 99, "username": "pet-fixture-outsider"}],
            ).parents[0]
            species = PetSpecies.objects.create(id=801, slug="fixture-notification-wolf", name="Woodland Wolf")
            potion = PotionType.objects.create(id=802, slug="fixture-notification-base", name="Base")
            for owner, pet_id in ((parent, 803), (child, 804)):
                type(owner).objects.select_for_update().get(pk=owner.pk)
                pet = UserPet.objects.create(
                    id=pet_id, user=owner, species=species, potion=potion, growth_points=100,
                )
                mount = PetService._save_growth(pet, update_fields=["growth_points"])
                self.assertEqual(mount.user_id, owner.pk)
                pet.refresh_from_db()
                self.assertTrue(pet.evolved_to_mount)

            def fixed_notification_id(title, wire_id):
                receipt = Notification.objects.get(user=parent, notification_type="pet_evolved", title=title)
                if receipt.pk != wire_id:
                    # Preserve actual service rows while pinning wire identities
                    # independently of the full PostgreSQL suite's sequences.
                    occupied = Notification.objects.filter(pk=wire_id)
                    if occupied.exists():
                        occupied.update(id=Notification.objects.latest("pk").pk + 1)
                    Notification.objects.filter(pk=receipt.pk).update(id=wire_id)
                return wire_id

            own_id = fixed_notification_id("Woodland Wolf evolved into a mount!", 901)
            child_id = fixed_notification_id("Abby's pet evolved", 902)
            self.client.force_authenticate(parent)
            own = self.assert_response_fixture(
                self.client.get(f"/api/notifications/{own_id}/", HTTP_X_ABBY_SPACE="personal"),
                "parent-personal-pet-notification.json",
            )
            child_update = self.assert_response_fixture(
                self.client.get(f"/api/notifications/{child_id}/"),
                "parent-child-pet-notification.json",
            )
            self.assertEqual(own["link"], "/bestiary?tab=mounts&space=personal")
            self.assertEqual(child_update["link"], "/family?child=7")
            child_receipt = Notification.objects.get(user=child, notification_type="pet_evolved")
            self.client.force_authenticate(child)
            self.assertEqual(self.client.get(f"/api/notifications/{child_receipt.pk}/").json()["link"],
                             "/bestiary?tab=mounts")
            self.assertFalse(Notification.objects.filter(user=outsider).exists())
            self.client.force_authenticate(outsider)
            for receipt_id in (own_id, child_id):
                self.assertEqual(self.client.get(f"/api/notifications/{receipt_id}/").status_code, 404)

    def test_personal_parent_dashboard_uses_own_progress_without_changing_role(self):
        from apps.habits.models import Habit
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            family = make_family(
                "Parent Personal Fixture", family_id=63,
                parents=[{"id": 6, "username": "personal-parent", "display_name": "Alex"}],
                children=[{"id": 7, "username": "personal-child"}],
            )
            parent, child = family.parents[0], family.children[0]
            Habit.objects.create(id=901, user=parent, created_by=parent, name="Read after breakfast")
            Habit.objects.create(id=902, user=child, created_by=parent, name="Child-only habit")
            CoinService.award_coins(parent, 35, CoinLedger.Reason.ADJUSTMENT)
            CoinService.award_coins(child, 700, CoinLedger.Reason.ADJUSTMENT)
            self.client.force_authenticate(parent)
            body = self.assert_response_fixture(
                self.client.get("/api/dashboard/", HTTP_X_ABBY_SPACE="personal"),
                "parent-personal-dashboard.json",
            )
            self.assertEqual(body["role"], "parent")
            self.assertEqual(body["coin_balance"], 35)
            self.assertNotIn("family_overview", body)
            self.assertEqual([row["title"] for row in body["next_actions"]], ["Read after breakfast"])

    def test_child_overview_is_read_only_and_contains_saved_progress(self):
        from apps.achievements.models import Skill, SkillCategory, SkillProgress
        from apps.rewards.models import CoinLedger
        from apps.rewards.services import CoinService
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            family = make_family(
                "Child Profile Fixture", family_id=64,
                parents=[{"id": 6, "username": "profile-parent"}],
                children=[{"id": 7, "username": "profile-child", "display_name": "Abby"}],
            )
            parent, child = family.parents[0], family.children[0]
            category = SkillCategory.objects.create(id=801, name="Creative practice")
            skill = Skill.objects.create(id=802, name="Drawing", category=category)
            SkillProgress.objects.create(id=803, user=child, skill=skill, xp_points=25, level=1)
            badge = Badge.objects.create(id=804, name="First drawing", criteria_type="manual")
            UserBadge.objects.create(id=805, user=child, badge=badge)
            CoinService.award_coins(child, 45, CoinLedger.Reason.ADJUSTMENT)
            self.client.force_authenticate(parent)
            before = list(CoinLedger.objects.values())
            body = self.assert_response_fixture(
                self.client.get(f"/api/children/{child.pk}/overview/"),
                "family-child-overview.json",
            )
            self.assertEqual(body["child"]["id"], child.pk)
            self.assertEqual(body["counts"]["skills"], 1)
            self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_family_overview_is_the_household_day_with_safe_confirmed_accomplishments(self):
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            household = make_family(
                "Parent Overview Fixture", family_id=61,
                parents=[{"id": 6, "username": "overview-fixture-parent"}],
                children=[
                    {"id": 7, "username": "abby", "display_name": "Abby", "hourly_rate": "10.00"},
                    {"id": 8, "username": "ben", "display_name": "Ben"},
                ],
            )
            parent, child = household.parents[0], household.children[0]
            for title, due in (("Math practice", date(2026, 10, 18)),
                               ("Reading worksheet", date(2026, 10, 17)),
                               ("Science notes", date(2026, 10, 16))):
                assignment = HomeworkAssignment.objects.create(
                    title=title, subject="math", assigned_to=child, created_by=parent,
                    due_date=due, notes="Synthetic private parent context, never in the overview.",
                )
                if title == "Science notes":
                    HomeworkSubmission.objects.create(
                        assignment=assignment, user=child, status="pending", timeliness="late",
                        notes="Synthetic private submission body, never in the overview.",
                    )
            Chore.objects.create(title="Tidy up", family=household.family, created_by=parent)
            chore = Chore.objects.create(
                title="Make the bed", family=household.family, created_by=parent, assigned_to=child,
            )
            ChoreCompletion.objects.create(
                chore=chore, user=child, completed_date=date(2026, 10, 18), status="approved",
                decided_at=FIXED_NOW - timedelta(hours=2), decided_by=parent,
                reward_amount_snapshot="0.00", coin_reward_snapshot=0,
            )
            goal = ChallengeGoal.objects.create(
                id=801, user=child, family=household.family, created_by=parent,
                name="Read together", metric="minutes", target="20", unit="minutes",
                timezone_name="America/Phoenix", starts_at=FIXED_NOW - timedelta(days=1),
                ends_at=FIXED_NOW + timedelta(days=1),
            )
            ChallengeOccurrence.objects.create(
                id=802, goal=goal, starts_at=goal.starts_at, ends_at=goal.ends_at,
                progress="7.500", snapshot={"name": "Read together", "target": "20.000", "unit": "minutes"},
            )
            badge = Badge.objects.create(id=901, name="Steady learner", criteria_type="homework_count")
            UserBadge.objects.create(user=child, badge=badge)
            project = Project.objects.create(
                id=401, title="Weekend build", assigned_to=child, created_by=parent, status="in_progress",
            )
            TimeEntry.objects.create(
                user=child, project=project, status="completed",
                clock_in=FIXED_NOW - timedelta(minutes=90), clock_out=FIXED_NOW,
            )
            outsider = make_family("Other Overview Fixture", children=[{"username": "other-child"}])
            HomeworkAssignment.objects.create(
                title="Other family's homework", subject="math", assigned_to=outsider.children[0],
                created_by=parent, due_date=date(2026, 10, 18),
            )
            self.client.force_authenticate(parent)
            body = self.assert_response_fixture(self.client.get("/api/dashboard/"), "parent-family-overview.json")
            self.assertEqual(body["family_overview"]["date"], "2026-10-18")
            self.assertEqual([row["kid_id"] for row in body["family_overview"]["children"]], [7, 8])
            self.assertNotIn("private", str(body["family_overview"]))


class ParentDeliveryApiFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def test_inactive_child_saved_delivery_is_shared_by_mcp_and_native_replay(self):
        from apps.mcp_server.context import override_user
        from apps.mcp_server.server import mcp
        from apps.rewards.models import CoinLedger, Reward, RewardRedemption
        from apps.rewards.services import CoinService, RewardService
        from apps.rpg.models import UserInventory
        household = make_family(
            "Inactive Delivery Fixture", family_id=62,
            parents=[{"id": 6, "username": "inactive-delivery-parent", "is_staff": True}],
            children=[{"id": 7, "username": "inactive-delivery-child", "display_name": "Abby"}],
        )
        parent, child = household.parents[0], household.children[0]
        self.client.force_authenticate(user=parent)
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            reward = Reward.objects.create(id=901, family=household.family, name="Saved park afternoon", cost_coins=20)
            CoinService.award_coins(child, 50, CoinLedger.Reason.ADJUSTMENT)
            redemption = RewardRedemption.objects.create(id=902, user=child, reward=reward, coin_cost_snapshot=20)
            approved = RewardService.approve(redemption, parent, notes="Saturday after lunch")
            child.is_active = False
            child.save(update_fields=["is_active"])
            before = list(CoinLedger.objects.values())
            with override_user(parent, scopes=frozenset({"mcp:read", "mcp:write"})):
                result = async_to_sync(mcp.call_tool)("deliver_reward_redemption", {"params": {
                    "user_id": child.pk, "redemption_id": redemption.pk,
                }, "confirmation": True})
            delivered = result[1] if isinstance(result, tuple) else result.structuredContent
            self.assertNotIn("error", delivered, delivered)
            self.assertEqual(delivered["status"], "fulfilled")
            response = self.client.post(f"/api/redemptions/{redemption.pk}/deliver/", {}, format="json")
            native = self.assert_response_fixture(response, "parent-reward-inactive-delivered.json")
            self.assertEqual(native["delivered_at"], delivered["delivered_at"])
            self.assertEqual(datetime.fromisoformat(native["decided_at"]), approved.decided_at)
            self.assertEqual(self.client.post(f"/api/redemptions/{redemption.pk}/deliver/", {}, format="json").json(), native)
            self.assertEqual(list(CoinLedger.objects.values()), before)
            self.assertFalse(UserInventory.objects.filter(user=child).exists())

    def test_real_world_approval_and_delivery_keep_distinct_audit_receipts(self):
        from apps.rewards.models import Reward, RewardRedemption
        from apps.rewards.services import CoinService
        from apps.rewards.models import CoinLedger
        household = make_family(
            "Parent Delivery Fixture", family_id=62,
            parents=[{"id": 6, "username": "delivery-parent"}],
            children=[{"id": 7, "username": "delivery-child", "display_name": "Abby"}],
        )
        parent, child = household.parents[0], household.children[0]
        self.client.force_authenticate(user=parent)
        with patch("django.utils.timezone.now", return_value=FIXED_NOW):
            reward = Reward.objects.create(id=901, family=household.family, name="Park afternoon", cost_coins=20)
            CoinService.award_coins(child, 50, CoinLedger.Reason.ADJUSTMENT)
            # Fixed synthetic request identity, including its frozen promise.
            redemption = RewardRedemption.objects.create(id=902, user=child, reward=reward, coin_cost_snapshot=20)
            approved = self.client.post(f"/api/redemptions/{redemption.pk}/approve/", {"notes": "Saturday after lunch"}, format="json")
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["status"], "approved")
            self.assert_response_fixture(approved, "parent-reward-approved.json")
            from apps.projects.parent_attention import parent_attention
            signal = parent_attention(parent)
            self.assertEqual(signal["counts"]["deliveries"], 1)
            delivered = self.client.post(f"/api/redemptions/{redemption.pk}/deliver/", {}, format="json")
            self.assertEqual(delivered.status_code, 200)
            self.assertEqual(delivered.json()["status"], "fulfilled")
            self.assert_response_fixture(delivered, "parent-reward-delivered.json")
            self.assertEqual(delivered.json()["decided_at"], approved.json()["decided_at"])
            self.assertEqual(parent_attention(parent)["counts"]["deliveries"], 0)
