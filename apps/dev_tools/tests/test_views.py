"""HTTP-level tests for /api/dev/*.

The 8 operation endpoints' BEHAVIOR is covered by ``test_commands.py``
(via the management commands, which call the same operations). These
tests focus on the HTTP boundary:

  * Permission: anonymous + child + cross-family-parent all blocked
  * Permission: parent in caller's family with the gate open succeeds
  * Gate: with DEBUG=False AND DEV_TOOLS_ENABLED=False, every endpoint 403s
  * Cross-family safety: parent in family A can't fire a drop into family B's child
  * Selectors: children/rewards return only the caller's family
"""
from __future__ import annotations

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from django.test import override_settings

from config.tests.factories import make_family


def _login(client, user):
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class GateTests(APITestCase):
    def setUp(self):
        fam = make_family(
            parents=[{"username": "parent_a", "is_staff": True}],
            children=[{"username": "child_a"}],
        )
        self.parent = fam.parents[0]
        self.child = fam.children[0]

    def test_anonymous_blocked(self):
        r = self.client.get("/api/dev/ping/")
        self.assertIn(r.status_code, {401, 403})

    def test_child_blocked(self):
        _login(self.client, self.child)
        r = self.client.get("/api/dev/ping/")
        self.assertEqual(r.status_code, 403)

    def test_parent_with_gate_open_succeeds(self):
        _login(self.client, self.parent)
        r = self.client.get("/api/dev/ping/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["enabled"])

    def test_non_staff_parent_blocked(self):
        # Signup-created parents have is_staff=False — production deploys
        # only let the founding superuser into /api/dev/. Pinned so a
        # future loosening of the gate is loud.
        non_staff = make_family(
            name="non-staff",
            parents=[{"username": "regular_parent"}],  # is_staff defaults False
        ).parents[0]
        _login(self.client, non_staff)
        r = self.client.get("/api/dev/ping/")
        self.assertEqual(r.status_code, 403)

    @override_settings(DEBUG=False, DEV_TOOLS_ENABLED=False)
    def test_gate_off_blocks_parent_via_view_permission(self):
        # Even if the URL is mounted (we only mount when gate-on at startup),
        # the view permission re-checks. Here the URL won't be mounted at
        # all, so we get a 404 from the catch-all SPA. Either way, no 200.
        _login(self.client, self.parent)
        r = self.client.get("/api/dev/ping/")
        self.assertNotEqual(r.status_code, 200)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class CrossFamilySafetyTests(APITestCase):
    def setUp(self):
        from apps.rpg.models import ItemDefinition

        a = make_family(
            name="A",
            parents=[{"username": "parent_a", "is_staff": True}],
            children=[{"username": "child_a"}],
        )
        b = make_family(
            name="B",
            parents=[{"username": "parent_b", "is_staff": True}],
            children=[{"username": "child_b"}],
        )
        self.parent_a = a.parents[0]
        self.child_a = a.children[0]
        self.parent_b = b.parents[0]
        self.child_b = b.children[0]

        self.item = ItemDefinition.objects.create(
            slug="testitem", name="Test", icon="✨",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            rarity=ItemDefinition.Rarity.COMMON,
        )

    def test_parent_a_cannot_force_drop_into_family_b(self):
        from apps.rpg.models import DropLog

        _login(self.client, self.parent_a)
        r = self.client.post("/api/dev/force-drop/", {
            "user_id": self.child_b.id,
            "slug": "testitem",
        }, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(DropLog.objects.filter(user=self.child_b).exists())

    def test_children_select_returns_only_callers_family(self):
        _login(self.client, self.parent_a)
        r = self.client.get("/api/dev/children/")
        self.assertEqual(r.status_code, 200)
        usernames = {c["username"] for c in r.data}
        self.assertEqual(usernames, {"child_a"})

    def test_rewards_select_returns_only_callers_family(self):
        from apps.rewards.models import Reward

        Reward.objects.create(
            family=self.parent_a.family, name="Reward A",
            cost_coins=10, rarity=Reward.Rarity.COMMON,
        )
        Reward.objects.create(
            family=self.parent_b.family, name="Reward B",
            cost_coins=10, rarity=Reward.Rarity.COMMON,
        )

        _login(self.client, self.parent_a)
        r = self.client.get("/api/dev/rewards/")
        self.assertEqual(r.status_code, 200)
        names = {row["name"] for row in r.data}
        self.assertEqual(names, {"Reward A"})

    def test_set_reward_stock_404s_on_other_family_reward(self):
        from apps.rewards.models import Reward

        other_reward = Reward.objects.create(
            family=self.parent_b.family, name="B-only",
            cost_coins=10, rarity=Reward.Rarity.COMMON, stock=5,
        )

        _login(self.client, self.parent_a)
        r = self.client.post("/api/dev/set-reward-stock/", {
            "reward_id": other_reward.id, "stock": 0,
        }, format="json")
        self.assertEqual(r.status_code, 404)

        other_reward.refresh_from_db()
        self.assertEqual(other_reward.stock, 5)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class HappyPathTests(APITestCase):
    """One representative POST per endpoint. Operation behavior is covered
    in ``test_commands.py``; these just pin the HTTP wiring + return shape."""

    def setUp(self):
        from apps.rpg.models import ItemDefinition

        fam = make_family(
            parents=[{"username": "parent", "is_staff": True}],
            children=[{"username": "child"}],
        )
        self.parent = fam.parents[0]
        self.child = fam.children[0]
        self.item = ItemDefinition.objects.create(
            slug="happy-item", name="Happy", icon="🎯",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            rarity=ItemDefinition.Rarity.RARE,
        )
        _login(self.client, self.parent)

    def test_force_drop_returns_item_meta(self):
        r = self.client.post("/api/dev/force-drop/", {
            "user_id": self.child.id, "slug": "happy-item",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["item"]["slug"], "happy-item")
        self.assertEqual(r.data["count"], 1)
        self.assertFalse(r.data["salvaged"])

    def test_force_celebration_streak_milestone(self):
        from apps.notifications.models import Notification, NotificationType

        r = self.client.post("/api/dev/force-celebration/", {
            "user_id": self.child.id, "kind": "streak_milestone", "days": 30,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["days"], 30)
        self.assertTrue(
            Notification.objects.filter(
                user=self.child,
                notification_type=NotificationType.STREAK_MILESTONE,
            ).exists(),
        )

    def test_set_streak(self):
        from apps.rpg.models import CharacterProfile

        r = self.client.post("/api/dev/set-streak/", {
            "user_id": self.child.id, "days": 14,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["login_streak"], 14)
        self.assertEqual(
            CharacterProfile.objects.get(user=self.child).login_streak, 14,
        )

    def test_expire_journal(self):
        from apps.chronicle.models import ChronicleEntry

        r = self.client.post("/api/dev/expire-journal/", {
            "user_id": self.child.id,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn(r.data["action"], {"created", "backdated", "noop_already_present"})
        self.assertTrue(
            ChronicleEntry.objects.filter(
                user=self.child, kind=ChronicleEntry.Kind.JOURNAL,
            ).exists(),
        )

    def test_tick_perfect_day(self):
        r = self.client.post("/api/dev/tick-perfect-day/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["task"], "evaluate_perfect_day_task")

    def test_reset_day_counters(self):
        from apps.homework.models import HomeworkDailyCounter
        from django.utils import timezone

        HomeworkDailyCounter.objects.create(
            user=self.child, occurred_on=timezone.localdate(), count=1,
        )

        r = self.client.post("/api/dev/reset-day-counters/", {
            "user_id": self.child.id, "kind": "homework",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["deleted"]["homework"], 1)

    def test_set_pet_happiness_400s_when_no_pet(self):
        # Operation raises OperationError → view returns 400.
        r = self.client.post("/api/dev/set-pet-happiness/", {
            "user_id": self.child.id, "level": "stale",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_force_drop_without_rarity_or_slug_400s(self):
        r = self.client.post("/api/dev/force-drop/", {
            "user_id": self.child.id,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_checklist_returns_markdown(self):
        r = self.client.get("/api/dev/checklist/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Manual Testing", r.data["markdown"])

    def test_items_select_filters_by_rarity(self):
        r = self.client.get("/api/dev/items/?rarity=rare")
        self.assertEqual(r.status_code, 200)
        slugs = {row["slug"] for row in r.data}
        self.assertIn("happy-item", slugs)


@override_settings(DEV_TOOLS_ENABLED=True, DEBUG=False)
class ToastCeremonyEndpointTests(APITestCase):
    """HTTP wiring for the 8 toast & ceremony ops + the 2 new selectors.

    Operation behavior is covered in ``test_operations.py``; these pin the
    URL → view → serializer round trip and the new ``ChildSelectView``
    nested-data shape.
    """

    def setUp(self):
        fam = make_family(
            parents=[{"username": "p", "is_staff": True}],
            children=[{"username": "abby"}],
        )
        self.parent = fam.parents[0]
        self.child = fam.children[0]
        _login(self.client, self.parent)

    def test_children_response_carries_pets_and_mounts(self):
        from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet

        species = PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        potion_a = PotionType.objects.create(slug="ember", name="Ember")
        potion_b = PotionType.objects.create(slug="frost", name="Frost")
        UserPet.objects.create(
            user=self.child, species=species, potion=potion_a,
            growth_points=42,
        )
        UserMount.objects.create(
            user=self.child, species=species, potion=potion_b,
        )

        r = self.client.get("/api/dev/children/")
        self.assertEqual(r.status_code, 200)
        kid = next(c for c in r.data if c["username"] == "abby")
        self.assertEqual(len(kid["pets"]), 1)
        self.assertEqual(kid["pets"][0]["growth_points"], 42)
        self.assertEqual(len(kid["mounts"]), 1)
        self.assertFalse(kid["mounts"][0]["has_active_expedition"])

    def test_pet_species_selector_returns_seeded_rows(self):
        from apps.pets.models import PetSpecies

        PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        r = self.client.get("/api/dev/pet-species/")
        self.assertEqual(r.status_code, 200)
        slugs = {row["slug"] for row in r.data}
        self.assertIn("fox", slugs)

    def test_potion_types_selector_returns_seeded_rows(self):
        from apps.pets.models import PotionType

        PotionType.objects.create(slug="ember", name="Ember")
        r = self.client.get("/api/dev/potion-types/")
        self.assertEqual(r.status_code, 200)
        slugs = {row["slug"] for row in r.data}
        self.assertIn("ember", slugs)

    def test_force_approval_notification_returns_type(self):
        r = self.client.post("/api/dev/force-approval-notification/", {
            "user_id": self.child.id,
            "flow": "chore",
            "outcome": "approved",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["notification_type"], "chore_approved")

    def test_force_quest_progress_400s_when_no_definition(self):
        r = self.client.post("/api/dev/force-quest-progress/", {
            "user_id": self.child.id, "delta": 10,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_force_quest_progress_happy_path(self):
        from apps.quests.models import QuestDefinition

        QuestDefinition.objects.create(
            name="Test", description="t", icon="⚔️",
            quest_type=QuestDefinition.QuestType.BOSS,
            target_value=100, duration_days=7,
            is_system=True,
        )
        r = self.client.post("/api/dev/force-quest-progress/", {
            "user_id": self.child.id, "delta": 15,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["current_progress"], 15)

    def test_mark_daily_challenge_ready(self):
        r = self.client.post("/api/dev/mark-daily-challenge-ready/", {
            "user_id": self.child.id,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["ready"])
        self.assertEqual(r.data["current_progress"], r.data["target_value"])

    def test_set_pet_growth_happy_path(self):
        from apps.pets.models import PetSpecies, PotionType, UserPet

        species = PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        potion = PotionType.objects.create(slug="ember", name="Ember")
        pet = UserPet.objects.create(
            user=self.child, species=species, potion=potion,
        )
        r = self.client.post("/api/dev/set-pet-growth/", {
            "user_id": self.child.id, "pet_id": pet.pk, "growth": 99,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["growth_points"], 99)

    def test_grant_hatch_ingredients_400s_on_missing_slug(self):
        r = self.client.post("/api/dev/grant-hatch-ingredients/", {
            "user_id": self.child.id,
            "species_slug": "nope",
            "potion_slug": "nope",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_clear_breed_cooldowns_returns_count(self):
        from apps.pets.models import PetSpecies, PotionType, UserMount

        species = PetSpecies.objects.create(slug="fox", name="Fox", icon="🦊")
        potion = PotionType.objects.create(slug="ember", name="Ember")
        UserMount.objects.create(
            user=self.child, species=species, potion=potion,
        )
        r = self.client.post("/api/dev/clear-breed-cooldowns/", {
            "user_id": self.child.id,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["mounts_reset"], 1)

    def test_seed_companion_growth_requires_species_seed(self):
        # No PetSpecies(slug=companion) → 400
        r = self.client.post("/api/dev/seed-companion-growth/", {
            "user_id": self.child.id, "ticks": 2,
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_mark_expedition_ready_no_mount_400s(self):
        r = self.client.post("/api/dev/mark-expedition-ready/", {
            "user_id": self.child.id, "tier": "standard",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cross_family_force_approval_404s(self):
        other = make_family(
            name="other",
            parents=[{"username": "po", "is_staff": True}],
            children=[{"username": "otherkid"}],
        )
        r = self.client.post("/api/dev/force-approval-notification/", {
            "user_id": other.children[0].id,
            "flow": "chore",
            "outcome": "approved",
        }, format="json")
        self.assertEqual(r.status_code, 404)
