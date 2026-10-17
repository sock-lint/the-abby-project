"""Rendered Django responses shared by the React and Unity contract checks.

Keep values deterministic by controlling test inputs, clock and token entropy;
the views, serializers, authentication, pagination and game loop remain real.
"""
import json
import os
from datetime import datetime, timedelta, timezone as datetime_timezone
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.notifications.models import Notification, NotificationType
from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
from apps.projects.models import Project
from apps.quests.models import DailyChallenge
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory
from apps.timecards.models import TimeEntry
from config.tests.factories import make_family


FIXTURE_DIR = Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures"
FIXED_NOW = datetime(2026, 10, 10, 19, 0, tzinfo=datetime_timezone.utc)
SYNTHETIC_TOKEN = "0123456789012345678901234567890123456789"


@override_settings(
    # These wire-contract scenarios exercise a deliberately synthetic future
    # catalog. Production asset eligibility is covered separately by
    # test_catalog_api_contract_fixtures with the unchanged shipped registry.
    RPG_ASSET_SUPPORT_POLICY={
        "schema_version": 1,
        "pets": [
            {"species_slug": "fixture-fox", "sprite_key": "fox", "potion_slugs": ["base", "fire", "ice", "cosmic"]},
            {"species_slug": "fixture-wolf", "sprite_key": "wolf", "potion_slugs": ["base", "fire", "ice", "cosmic"]},
            {"species_slug": "fox", "sprite_key": "fox", "potion_slugs": ["fire", "ice"]},
        ],
        "potion_slugs": ["base", "fire", "ice", "cosmic"],
        "disabled_item_types": ["cosmetic_pet_accessory"],
        "features": {},
    },
    ALLOWED_HOSTS=["testserver"],
    TIME_ZONE="America/Phoenix",
    USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="",
    VAPID_PRIVATE_KEY="",
)
class SharedApiResponseFixtureTests(APITestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        # Pin wire identities even when the full suite advances PostgreSQL sequences.
        household = make_family(
            "Fixture Family", family_id=1,
            parents=[{
                "id": 6, "username": "fixture-parent", "password": "synthetic-password",
                "display_name": "Fixture Parent",
            }],
            children=[{
                "id": 7, "username": "fixture-child", "password": "synthetic-password",
                "display_name": "Fixture Child", "theme": "hyrule",
            }, {"id": 8, "username": "fixture-sibling"}],
        )
        family, parent = household.family, household.parents[0]
        self.child, self.sibling = household.children
        self.outsider = make_family(
            "Other Fixture Family", family_id=2,
            children=[{"id": 99, "username": "fixture-outsider"}],
        ).children[0]
        category = SkillCategory.objects.create(id=1, name="Language Arts")
        self.skill = Skill.objects.create(id=2, name="Reading", category=category)
        self.habit = Habit.objects.create(
            id=9, name='Read {a} book "today"', icon="book", user=self.child,
            created_by=parent, xp_reward=5, max_taps_per_day=1, strength=-2,
        )
        HabitSkillTag.objects.create(id=4, habit=self.habit, skill=self.skill, xp_weight=1)
        # Use the production page size (20), including actual safety flag variants.
        for index in range(2, 22):
            Habit.objects.create(
                id=index + 8, name=f"Ritual {index:02d}", user=self.child,
                created_by=parent,
                habit_type="negative" if index == 2 else "both" if index == 3 else "positive",
                is_active=index != 4,
            )
        # Extra rows must not leak into this child's paginated tap surface.
        for habit_id, owner, pending in ((91, self.sibling, False), (92, self.outsider, False), (93, self.child, True)):
            Habit.objects.create(
                id=habit_id, name=f"Hidden ritual {habit_id}", user=owner,
                created_by=parent if owner.family_id == family.id else self.outsider,
                pending_parent_review=pending,
            )
        self.auth_token = Token.objects.create(user=self.child, key="f" * 40)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.auth_token.key}")

    def assert_response_fixture(self, response, name, status=200):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        actual = response.json()
        path = FIXTURE_DIR / name
        if os.environ.get("UPDATE_API_CONTRACT_FIXTURES") == "1":
            self.assertFalse(os.environ.get("CI"), "Fixture regeneration is a local, reviewed operation.")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        expected = json.loads(path.read_text(encoding="utf-8"))
        # Python value equality treats True == 1 and 5 == 5.0. Canonical JSON
        # preserves these wire types while ignoring object key order.
        self.assertEqual(
            json.dumps(actual, sort_keys=True, indent=2),
            json.dumps(expected, sort_keys=True, indent=2),
            f"API response drifted from {path.name}; review the contract and regenerate deliberately.",
        )
        return actual

    def test_clock_idle_and_active_responses_are_self_scoped_json(self):
        project = Project.objects.create(
            id=401, title="Paper bookmark", created_by=self.child,
            assigned_to=self.child, status="in_progress",
        )
        # Another account's running timer must never replace this child's idle state.
        for entry_id, owner in ((502, self.sibling), (503, self.outsider)):
            TimeEntry.objects.create(
                id=entry_id, user=owner, project=project, clock_in=FIXED_NOW, status="active",
            )
        self.assertIsNone(self.assert_response_fixture(
            self.client.get("/api/clock/"), "clock-idle.json",
        ))
        entry = TimeEntry.objects.create(
            id=501, user=self.child, project=project,
            clock_in=FIXED_NOW - timedelta(minutes=6), status="active",
        )
        body = self.assert_response_fixture(self.client.get("/api/clock/"), "clock-active.json")
        self.assertEqual((body["id"], body["user"], body["project"]), (501, 7, 401))
        entry.clock_out = FIXED_NOW
        entry.status = "completed"
        entry.save()
        self.assertIsNone(self.assert_response_fixture(
            self.client.get("/api/clock/"), "clock-idle.json",
        ))

    def seed_companion_care(self):
        """Synthetic ownership and typed food inputs; production services stay real."""
        fox = PetSpecies.objects.create(
            id=41, slug="fixture-fox", name="Fox", icon="🦊", sprite_key="fox",
            description="A synthetic woodland friend.", food_preference="berries",
        )
        wolf = PetSpecies.objects.create(
            id=42, slug="fixture-wolf", name="Wolf", icon="🐺", sprite_key="wolf",
            description="A synthetic trail companion.", food_preference="meat",
        )
        fire = PotionType.objects.create(
            id=43, slug="fire", name="Fire", sprite_key="fire-potion",
            color_hex="#E75A3A", rarity="uncommon", description="A warm synthetic variant.",
        )
        ice = PotionType.objects.create(
            id=44, slug="ice", name="Ice", sprite_key="ice-potion",
            color_hex="#91D9F2", rarity="rare", description="A cool synthetic variant.",
        )
        fox.available_potions.add(fire, ice)
        wolf.available_potions.add(fire, ice)
        self.pet = UserPet.objects.create(
            id=51, user=self.child, species=fox, potion=fire, name='Sprout {a} "friend"',
            growth_points=20, is_active=True,
        )
        self.ready_pet = UserPet.objects.create(
            id=52, user=self.child, species=wolf, potion=fire, growth_points=90,
            last_fed_at=FIXED_NOW - timedelta(days=9),
        )
        self.evolved_pet = UserPet.objects.create(
            id=53, user=self.child, species=fox, potion=ice, growth_points=100,
            evolved_to_mount=True,
        )
        self.mount = UserMount.objects.create(
            id=61, user=self.child, species=fox, potion=ice, is_active=True,
        )
        self.other_mount = UserMount.objects.create(
            id=62, user=self.child, species=wolf, potion=ice,
            last_bred_at=FIXED_NOW - timedelta(days=2),
        )
        self.preferred_food = ItemDefinition.objects.create(
            id=71, slug="fixture-berry-bowl", name="Berry Bowl", icon="🫐",
            sprite_key="berry-bowl", item_type="food", food_species=fox,
            description="A synthetic favorite for foxes.",
        )
        self.neutral_food = ItemDefinition.objects.create(
            id=72, slug="fixture-trail-mix", name="Trail Mix", icon="🥜",
            item_type="food", description="A synthetic neutral snack.",
        )
        egg = ItemDefinition.objects.create(
            id=73, slug="fixture-fox-egg", name="Synthetic Egg", icon="🥚",
            sprite_key="big-egg", item_type="egg", pet_species=fox,
        )
        self.wolf_food = ItemDefinition.objects.create(
            id=74, slug="fixture-wolf-meal", name="Wolf Meal", icon="🍖",
            item_type="food", food_species=wolf,
        )
        for inventory_id, item, quantity in (
            (81, self.preferred_food, 2), (82, self.neutral_food, 1), (83, egg, 1), (84, self.wolf_food, 1),
        ):
            UserInventory.objects.create(id=inventory_id, user=self.child, item=item, quantity=quantity)
        for row_id, owner in ((81, self.sibling), (82, self.outsider)):
            UserPet.objects.create(
                id=row_id, user=owner, species=wolf, potion=ice, growth_points=10, is_active=True,
            )
            UserMount.objects.create(id=row_id, user=owner, species=fox, potion=fire, is_active=True)
            UserInventory.objects.create(id=row_id + 10, user=owner, item=self.preferred_food, quantity=2)

    def pin_next_mount_identity(self):
        # Evolution creates its real mount through an auto field. Reset only
        # this test table's sequence so PostgreSQL/full-suite ordering cannot
        # change the raw response's generated ID; never replace the service.
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute(
                    "UPDATE sqlite_sequence SET seq = (SELECT MAX(id) FROM pets_usermount) "
                    "WHERE name = 'pets_usermount'"
                )
            else:
                for sql in connection.ops.sequence_reset_sql(no_style(), [UserMount]):
                    cursor.execute(sql)

    def seed_hatching(self):
        fox = PetSpecies.objects.create(
            id=41, slug="fox", name="Fox", icon="🦊", sprite_key="fox",
            description="A synthetic fox for hatching checks.", food_preference="berries",
        )
        fire = PotionType.objects.create(
            id=43, slug="fire", name="Fire", color_hex="#FF4500", rarity="uncommon",
        )
        ice = PotionType.objects.create(
            id=44, slug="ice", name="Ice", sprite_key="ice-potion", color_hex="#00BBFF", rarity="rare",
        )
        fox.available_potions.add(fire, ice)
        self.hatch_species = fox
        self.hatch_potion = ice
        self.existing_hatch_pet = UserPet.objects.create(
            id=51, user=self.child, species=fox, potion=fire, is_active=True, growth_points=20,
        )
        self.hatch_egg = ItemDefinition.objects.create(
            id=73, slug="fixture-fox-egg", name="Synthetic Egg", icon="🥚",
            sprite_key="big-egg", item_type="egg", pet_species=fox,
        )
        self.hatch_potion_item = ItemDefinition.objects.create(
            id=75, slug="fixture-ice-potion", name="Synthetic Ice Potion", icon="🧪",
            sprite_key="ice-potion", item_type="potion", potion_type=ice, rarity="rare",
        )
        self.duplicate_hatch_potion = ItemDefinition.objects.create(
            id=76, slug="fixture-fire-potion", name="Synthetic Fire Potion", icon="🧪",
            item_type="potion", potion_type=fire, rarity="uncommon",
        )
        self.hatch_food = ItemDefinition.objects.create(
            id=71, slug="fixture-berry-bowl", name="Berry Bowl", icon="🫐",
            item_type="food", food_species=fox,
        )
        foreign_egg = ItemDefinition.objects.create(
            id=77, slug="fixture-foreign-egg", name="Other Synthetic Egg", icon="🥚",
            item_type="egg", pet_species=fox,
        )
        foreign_potion = ItemDefinition.objects.create(
            id=78, slug="fixture-foreign-potion", name="Other Synthetic Potion", icon="🧪",
            item_type="potion", potion_type=ice,
        )
        for row_id, item, quantity in (
            (83, self.hatch_egg, 2), (85, self.hatch_potion_item, 1),
            (86, self.duplicate_hatch_potion, 2), (81, self.hatch_food, 2),
        ):
            UserInventory.objects.create(id=row_id, user=self.child, item=item, quantity=quantity)
        for row_id, owner in ((81, self.sibling), (82, self.outsider)):
            # Another owner's identical combination must neither block this
            # child nor make those owners' ingredients available to the child.
            UserPet.objects.create(id=row_id, user=owner, species=fox, potion=ice)
            for offset, item in enumerate((self.hatch_egg, self.hatch_potion_item, foreign_egg, foreign_potion)):
                UserInventory.objects.create(id=row_id * 10 + offset, user=owner, item=item, quantity=3)

    def pin_next_hatched_pet_identity(self):
        # The real service creates this auto-field row. Reset the test table's
        # sequence after explicit IDs, including on PostgreSQL/full-suite runs.
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute(
                    "UPDATE sqlite_sequence SET seq = (SELECT MAX(id) FROM pets_userpet) "
                    "WHERE name = 'pets_userpet'"
                )
            else:
                for sql in connection.ops.sequence_reset_sql(no_style(), [UserPet]):
                    cursor.execute(sql)

    def hatching_state(self):
        return (
            list(UserInventory.objects.order_by("pk").values_list("pk", "user_id", "item_id", "quantity", "updated_at")),
            list(UserPet.objects.order_by("pk").values_list("pk", "user_id", "species_id", "potion_id", "growth_points", "is_active", "evolved_to_mount")),
        )

    def test_hatching_inventory_keeps_item_identity_and_typed_ingredients(self):
        self.seed_hatching()
        body = self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-hatching.json")
        self.assertEqual({row["id"] for row in body}, {81, 83, 85, 86})
        egg = next(row for row in body if row["item"]["id"] == 73)
        potion = next(row for row in body if row["item"]["id"] == 75)
        self.assertEqual((egg["id"], egg["quantity"], egg["item"]["pet_species_name"]), (83, 2, "Fox"))
        self.assertEqual((potion["id"], potion["quantity"], potion["item"]["potion_type_name"]), (85, 1, "Ice"))
        self.assertIsNone(egg["item"]["potion_type_name"])
        self.assertIsNone(potion["item"]["pet_species_name"])
        self.assertEqual((egg["item"]["lifecycle_stage"], egg["item"]["pet_species_slug"]), ("egg", "fox"))
        self.assertIsNone(potion["item"]["lifecycle_stage"])

    def test_hatch_consumes_exactly_one_pair_and_returns_a_new_inactive_pet(self):
        from apps.chronicle.models import ChronicleEntry

        self.seed_hatching()
        self.pin_next_hatched_pet_identity()
        foreign_inventory = list(UserInventory.objects.exclude(user=self.child).order_by("pk").values_list("pk", "quantity", "updated_at"))
        response = self.client.post("/api/pets/hatch/", {
            "egg_item_id": 73, "potion_item_id": 75, "user_id": self.outsider.pk,
        }, format="json")
        body = self.assert_response_fixture(response, "pet-hatch.json", status=201)
        pet = UserPet.objects.get(pk=body["id"])
        self.assertEqual((pet.user_id, pet.species_id, pet.potion_id), (self.child.pk, 41, 44))
        self.assertEqual((pet.growth_points, pet.is_active, pet.evolved_to_mount), (0, False, False))
        self.assertFalse(body["is_fully_grown"])
        self.assertEqual(body["lifecycle_stage"], "baby")
        self.assertEqual(body["happiness_level"], "happy")
        self.assertIsNone(pet.last_fed_at)
        self.assertIsNone(body["last_fed_at"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.hatch_egg).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.hatch_potion_item).exists())
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.duplicate_hatch_potion).quantity, 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.hatch_food).quantity, 2)
        self.existing_hatch_pet.refresh_from_db()
        self.assertTrue(self.existing_hatch_pet.is_active)
        self.assertEqual(self.existing_hatch_pet.growth_points, 20)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 2)
        self.assertFalse(UserMount.objects.filter(user=self.child).exists())
        self.assertEqual(foreign_inventory, list(UserInventory.objects.exclude(user=self.child).order_by("pk").values_list("pk", "quantity", "updated_at")))
        self.assertEqual(ChronicleEntry.objects.filter(user=self.child, event_slug="first_pet_hatched").count(), 1)
        stable = self.client.get("/api/pets/stable/").json()
        self.assertEqual(next(row for row in stable["pets"] if row["id"] == pet.pk), body)

    def test_hatch_rejects_missing_unavailable_and_inventory_row_ids_without_writes(self):
        self.seed_hatching()
        before = self.hatching_state()
        for submitted in ({}, {"egg_item_id": 73}, {"potion_item_id": 75}):
            with self.subTest(submitted=submitted):
                response = self.client.post("/api/pets/hatch/", submitted, format="json")
                self.assert_response_fixture(response, "pet-hatch-missing-ingredients.json", status=400)
        for egg_id in (77, 83, 999):
            with self.subTest(egg_item_id=egg_id):
                response = self.client.post("/api/pets/hatch/", {"egg_item_id": egg_id, "potion_item_id": 75}, format="json")
                self.assert_response_fixture(response, "pet-hatch-unavailable-egg.json", status=400)
        for potion_id in (78, 85, 999):
            with self.subTest(potion_item_id=potion_id):
                response = self.client.post("/api/pets/hatch/", {"egg_item_id": 73, "potion_item_id": potion_id}, format="json")
                self.assert_response_fixture(response, "pet-hatch-unavailable-potion.json", status=400)
        self.assertEqual(self.hatching_state(), before)

    def test_hatch_duplicate_including_evolved_pet_preserves_all_ingredients(self):
        self.seed_hatching()
        for evolved in (False, True):
            with self.subTest(evolved=evolved):
                self.existing_hatch_pet.evolved_to_mount = evolved
                self.existing_hatch_pet.growth_points = 100 if evolved else 20
                self.existing_hatch_pet.save(update_fields=["evolved_to_mount", "growth_points"])
                before = self.hatching_state()
                response = self.client.post("/api/pets/hatch/", {"egg_item_id": 73, "potion_item_id": 76}, format="json")
                self.assert_response_fixture(response, "pet-hatch-duplicate.json", status=400)
                self.assertEqual(self.hatching_state(), before)

    def test_hatch_rejects_owned_non_ingredient_types_without_writes(self):
        self.seed_hatching()
        before = self.hatching_state()
        for submitted, expected in (
            ({"egg_item_id": 71, "potion_item_id": 75}, "That item is not an egg"),
            ({"egg_item_id": 73, "potion_item_id": 71}, "That item is not a potion"),
        ):
            with self.subTest(submitted=submitted):
                response = self.client.post("/api/pets/hatch/", submitted, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"error": expected})
        self.assertEqual(self.hatching_state(), before)

    def test_hatch_requires_authentication_without_changing_any_inventory(self):
        self.seed_hatching()
        before = self.hatching_state()
        self.client.credentials()
        response = self.client.post("/api/pets/hatch/", {"egg_item_id": 73, "potion_item_id": 75}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.hatching_state(), before)

    def seed_expeditions(self):
        self.seed_companion_care()
        UserMount.objects.create(id=63, user=self.child, species_id=41, potion_id=43)
        DropTable.objects.create(
            id=301, trigger_type="expedition_returned", item=self.preferred_food, weight=10,
        )
        for row_id, mount_id in ((101, 81), (102, 82)):
            MountExpedition.objects.create(
                id=row_id, mount_id=mount_id, tier="short", status="active",
                started_at=FIXED_NOW - timedelta(hours=3), returns_at=FIXED_NOW - timedelta(hours=1),
                loot={"coins": 99, "items": []},
            )
        # Start still creates its real auto-field identity. Explicit foreign
        # rows plus a sequence reset pin responses across SQLite/PostgreSQL.
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute(
                    "UPDATE sqlite_sequence SET seq = (SELECT MAX(id) FROM pets_mountexpedition) "
                    "WHERE name = 'pets_mountexpedition'"
                )
            else:
                for sql in connection.ops.sequence_reset_sql(no_style(), [MountExpedition]):
                    cursor.execute(sql)

    def start_fixture_expedition(self, tier="short", mount_id=61, now=FIXED_NOW):
        # Keep the real roll and materialization. A single seeded drop-table
        # entry fixes item choice, and fixed random input removes coin jitter.
        with patch("django.utils.timezone.now", return_value=now), patch("apps.pets.expeditions.random.random", return_value=0.5):
            response = self.client.post(f"/api/mounts/{mount_id}/expedition/", {"tier": tier}, format="json")
        self.assertEqual(response.status_code, 201, response.json())
        return response

    def expedition_reward_state(self):
        return (
            list(UserInventory.objects.order_by("pk").values_list("pk", "user_id", "item_id", "quantity", "updated_at")),
            list(CoinLedger.objects.order_by("pk").values_list("pk", "user_id", "amount", "reason")),
            list(DropLog.objects.order_by("pk").values_list("pk", "user_id", "item_id")),
            list(SkillProgress.objects.order_by("pk").values_list("pk", "user_id", "skill_id", "xp_points", "level")),
            list(CharacterProfile.objects.order_by("pk").values_list("pk", "login_streak", "last_active_date")),
            list(Notification.objects.order_by("pk").values_list("pk", "user_id", "notification_type", "is_read")),
        )

    def expedition_rows_state(self):
        return list(MountExpedition.objects.order_by("pk").values_list("pk", "mount_id", "tier", "status", "loot", "claimed_at"))

    def test_expedition_start_tiers_lock_loot_without_awarding_or_changing_inventory(self):
        self.seed_expeditions()
        before = self.expedition_reward_state()
        for index, (tier, duration, coins, slots) in enumerate((
            ("short", 7200, 15, 1), ("standard", 14400, 35, 2), ("long", 28800, 75, 3),
        )):
            with self.subTest(tier=tier):
                now = FIXED_NOW + timedelta(seconds=index - 2)
                response = self.start_fixture_expedition(tier, 61 + index, now)
                body = self.assert_response_fixture(response, f"expedition-start-{tier}.json", status=201)
                expedition = MountExpedition.objects.get(pk=body["id"])
                self.assertEqual(expedition.mount.user_id, self.child.pk)
                self.assertEqual((expedition.returns_at - expedition.started_at).total_seconds(), duration)
                self.assertEqual((body["status"], body["is_ready"], body["seconds_remaining"], body["claimed_at"]), ("active", False, duration, None))
                self.assertEqual(body["loot"]["coins"], coins)
                self.assertEqual(len(body["loot"]["items"]), slots)
                self.assertEqual([slot["item_id"] for slot in body["loot"]["items"]], [71] * slots)
                self.assertEqual([slot["catalog_icon"] for slot in body["loot"]["items"]], [None] * slots)
                self.assertEqual(expedition.loot, body["loot"])
        self.assertEqual(self.expedition_reward_state(), before)
        rows = self.assert_response_fixture(self.client.get("/api/expeditions/?user_id=99"), "expeditions.json")["expeditions"]
        self.assertEqual([row["id"] for row in rows], [105, 104, 103])
        stable = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-expeditions.json")
        self.assertEqual({mount["active_expedition"]["id"] for mount in stable["mounts"]}, {103, 104, 105})
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(hours=2)):
            ready = self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-ready.json")["expeditions"]
        self.assertEqual([(row["id"], row["status"], row["is_ready"], row["seconds_remaining"]) for row in ready], [(103, "active", True, -2)])
        self.assertEqual(self.expedition_reward_state(), before)

    def test_empty_expedition_lists_exclude_ready_foreign_and_sibling_rows_without_writes(self):
        self.seed_expeditions()
        before = (self.expedition_reward_state(), self.expedition_rows_state())
        for query in ("", "?ready=true", "?ready=true&user_id=99"):
            self.assert_response_fixture(self.client.get("/api/expeditions/" + query), "expeditions-empty.json")
        self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), before)

    def test_expedition_rejections_preserve_ownership_inventory_and_locked_rows(self):
        self.seed_expeditions()
        before = (self.expedition_reward_state(), self.expedition_rows_state())
        for tier in (None, "marathon", 1):
            response = self.client.post("/api/mounts/61/expedition/", {} if tier is None else {"tier": tier}, format="json")
            self.assert_response_fixture(response, "expedition-invalid-tier.json", status=400)
        for mount_id in (81, 82, 999):
            response = self.client.post(f"/api/mounts/{mount_id}/expedition/", {"tier": "short"}, format="json")
            self.assert_response_fixture(response, "expedition-mount-not-owned.json", status=404)
        for expedition_id in (101, 102, 999):
            response = self.client.post(f"/api/expeditions/{expedition_id}/claim/", {}, format="json")
            self.assert_response_fixture(response, "expedition-not-owned.json", status=404)
        self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), before)

    def test_early_claim_and_active_duplicate_start_do_not_award_or_reroll(self):
        self.seed_expeditions()
        self.start_fixture_expedition()
        before = (self.expedition_reward_state(), self.expedition_rows_state())
        with patch("apps.pets.expeditions.ExpeditionService._roll_loot", side_effect=AssertionError("Existing expeditions must not reroll")):
            self.assert_response_fixture(self.client.post("/api/expeditions/103/claim/", {}, format="json"), "expedition-early-claim.json", status=400)
            self.assert_response_fixture(self.client.post("/api/mounts/61/expedition/", {"tier": "long"}, format="json"), "expedition-already-active.json", status=400)
        self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), before)

    def test_expedition_claim_commits_locked_loot_once_and_repeat_awards_nothing(self):
        from apps.rpg.services import GameLoopService

        self.seed_expeditions()
        planned = self.start_fixture_expedition().json()["loot"]
        self.preferred_food.name = "Renamed after the locked roll"
        self.preferred_food.save(update_fields=["name"])
        foreign_inventory = list(UserInventory.objects.exclude(user=self.child).order_by("pk").values_list("pk", "quantity", "updated_at"))
        claim_now = FIXED_NOW + timedelta(hours=2, seconds=5)
        with patch("django.utils.timezone.now", return_value=claim_now), patch("apps.pets.expeditions.ExpeditionService._roll_loot", side_effect=AssertionError("Claim must not reroll loot")), patch("apps.rpg.services.GameLoopService.on_task_completed", wraps=GameLoopService.on_task_completed) as game_loop:
            self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-ready-claim.json")
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/api/expeditions/103/claim/", {}, format="json")
            body = self.assert_response_fixture(response, "expedition-claim.json")
            self.assertEqual((body["expedition_id"], body["freshly_claimed"], body["coins_awarded"]), (103, True, 15))
            self.assertEqual(body["items"], planned["items"])
            self.assertEqual(body["items"][0]["name"], "Berry Bowl")
            self.assertEqual(UserInventory.objects.get(user=self.child, item=self.preferred_food).quantity, 3)
            expedition = MountExpedition.objects.get(pk=103)
            self.assertEqual((expedition.status, expedition.claimed_at, expedition.loot), ("claimed", claim_now, planned))
            ledger = CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.EXPEDITION)
            self.assertEqual(ledger.amount, body["coins_awarded"])
            self.assertFalse(DropLog.objects.filter(user=self.child).exists())
            self.assertEqual(game_loop.call_count, 1)
            self.assertEqual(str(game_loop.call_args.args[1]), "expedition_returned")
            self.assertFalse(game_loop.call_args.args[2]["drops_allowed"])
            history = self.assert_response_fixture(self.client.get("/api/expeditions/"), "expeditions-claimed.json")["expeditions"]
            self.assertEqual((history[0]["status"], history[0]["is_ready"], history[0]["seconds_remaining"]), ("claimed", True, -5))
            after_claim = (self.expedition_reward_state(), self.expedition_rows_state())
            with self.captureOnCommitCallbacks(execute=True):
                repeated = self.client.post("/api/expeditions/103/claim/", {}, format="json")
            repeat = self.assert_response_fixture(repeated, "expedition-claim-repeat.json")
            self.assertEqual((repeat["freshly_claimed"], repeat["coins_awarded"], repeat["items"]), (False, 0, body["items"]))
            self.assertEqual(game_loop.call_count, 1)
            self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), after_claim)
            self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-empty.json")
            daily = self.client.post("/api/mounts/61/expedition/", {"tier": "short"}, format="json")
            self.assert_response_fixture(daily, "expedition-daily-limit.json", status=400)
            rested = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-expedition-rested.json")
            rested_mount = next(mount for mount in rested["mounts"] if mount["id"] == 61)
            self.assertFalse(rested_mount["expedition_available"])
            self.assertEqual(rested_mount["expedition_available_at"], "2026-10-11T00:00:00-07:00")
            with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(days=1)):
                tomorrow = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-expedition-next-day.json")
            self.assertTrue(next(mount for mount in tomorrow["mounts"] if mount["id"] == 61)["expedition_available"])
            self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), after_claim)
        self.assertEqual(foreign_inventory, list(UserInventory.objects.exclude(user=self.child).order_by("pk").values_list("pk", "quantity", "updated_at")))

    def test_expedition_claim_reports_actual_boosted_base_coins(self):
        self.seed_expeditions()
        planned = self.start_fixture_expedition().json()["loot"]["coins"]
        claim_now = FIXED_NOW + timedelta(hours=2, seconds=5)
        CharacterProfile.objects.filter(user=self.child).update(coin_boost_expires_at=claim_now + timedelta(hours=1))
        with patch("django.utils.timezone.now", return_value=claim_now):
            self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-ready-claim.json")
            body = self.assert_response_fixture(self.client.post("/api/expeditions/103/claim/", {}, format="json"), "expedition-claim-boosted.json")
        self.assertEqual(body["coins_awarded"], planned * 2)
        self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.EXPEDITION).amount, body["coins_awarded"])

    def test_expedition_salvage_is_separate_from_base_coins_and_never_duplicates_inventory(self):
        self.seed_expeditions()
        cosmetic = ItemDefinition.objects.create(
            id=79, slug="fixture-expedition-frame", name="Synthetic Expedition Frame", icon="🖼️",
            item_type="cosmetic_frame", rarity="rare", coin_value=20, sprite_key="fixture-frame",
        )
        UserInventory.objects.create(id=89, user=self.child, item=cosmetic, quantity=1)
        DropTable.objects.filter(pk=301).update(item=cosmetic)
        self.start_fixture_expedition()
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(hours=2, seconds=5)):
            self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-ready-salvage.json")
            body = self.assert_response_fixture(self.client.post("/api/expeditions/103/claim/", {}, format="json"), "expedition-claim-salvage.json")
            self.assertEqual(body["coins_awarded"], 15)
            self.assertEqual(body["items"][0]["salvaged_to_coins"], 20)
            self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.EXPEDITION).amount, 15)
            self.assertEqual(CoinLedger.objects.get(user=self.child, reason=CoinLedger.Reason.ADJUSTMENT).amount, 20)
            self.assertEqual(UserInventory.objects.get(user=self.child, item=cosmetic).quantity, 1)
            before = (self.expedition_reward_state(), self.expedition_rows_state())
            repeat = self.client.post("/api/expeditions/103/claim/", {}, format="json").json()
            self.assertEqual((repeat["freshly_claimed"], repeat["coins_awarded"], repeat["items"]), (False, 0, body["items"]))
            self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), before)

    def test_archived_expedition_item_remains_a_planned_slot_without_invented_inventory(self):
        self.seed_expeditions()
        planned = self.start_fixture_expedition().json()["loot"]["items"]
        self.preferred_food.delete()
        before_inventory = list(UserInventory.objects.order_by("pk").values_list("pk", "quantity"))
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(hours=2, seconds=5)):
            self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-ready-claim.json")
            body = self.assert_response_fixture(self.client.post("/api/expeditions/103/claim/", {}, format="json"), "expedition-claim-archived-item.json")
        self.assertEqual(body["items"], planned)
        self.assertEqual(body["coins_awarded"], 15)
        self.assertEqual(list(UserInventory.objects.order_by("pk").values_list("pk", "quantity")), before_inventory)
        self.assertFalse(UserInventory.objects.filter(item_id=71).exists())

    def test_expired_expedition_rejection_and_authentication_preserve_all_state(self):
        self.seed_expeditions()
        self.start_fixture_expedition(now=FIXED_NOW - timedelta(hours=3))
        MountExpedition.objects.filter(pk=103).update(status="expired")
        before = (self.expedition_reward_state(), self.expedition_rows_state())
        history = self.assert_response_fixture(self.client.get("/api/expeditions/"), "expeditions-expired.json")["expeditions"]
        self.assertEqual((history[0]["status"], history[0]["is_ready"], history[0]["seconds_remaining"]), ("expired", True, -3600))
        self.assert_response_fixture(self.client.get("/api/expeditions/?ready=true"), "expeditions-empty.json")
        self.assert_response_fixture(self.client.post("/api/expeditions/103/claim/", {}, format="json"), "expedition-expired.json", status=400)
        self.client.credentials()
        for path, method, body in (
            ("/api/expeditions/", "get", None), ("/api/expeditions/?ready=true", "get", None),
            ("/api/mounts/62/expedition/", "post", {"tier": "short"}), ("/api/expeditions/103/claim/", "post", {}),
        ):
            response = self.client.get(path) if method == "get" else self.client.post(path, body, format="json")
            self.assertEqual(response.status_code, 401)
        self.assertEqual((self.expedition_reward_state(), self.expedition_rows_state()), before)

    def seed_breeding(self):
        self.seed_companion_care()
        self.other_mount.potion_id = 43
        self.other_mount.last_bred_at = FIXED_NOW - timedelta(days=7)
        self.other_mount.save(update_fields=["potion", "last_bred_at"])
        UserMount.objects.create(
            id=63, user=self.child, species_id=41, potion_id=43,
            last_bred_at=FIXED_NOW - timedelta(days=2),
        )
        cosmic = PotionType.objects.create(
            id=45, slug="cosmic", name="Cosmic", sprite_key="cosmic-potion",
            color_hex="#AA88FF", rarity="legendary",
        )
        base = PotionType.objects.create(id=46, slug="base", name="Base", color_hex="#8B7355")
        self.breeding_base = base
        self.mount.species.available_potions.add(cosmic, base)
        ItemDefinition.objects.create(
            id=75, slug="fixture-wolf-egg", name="Synthetic Wolf Egg", icon="🥚",
            sprite_key="big-egg", item_type="egg", pet_species_id=42,
        )
        for item_id, potion, name in (
            (76, PotionType.objects.get(pk=43), "Synthetic Fire Potion"),
            (77, PotionType.objects.get(pk=44), "Synthetic Ice Potion"),
            (78, cosmic, "Synthetic Cosmic Potion"),
            (79, base, "Synthetic Base Potion"),
        ):
            ItemDefinition.objects.create(
                id=item_id, slug=f"fixture-breeding-{potion.slug}", name=name, icon="🧪",
                sprite_key=potion.sprite_key, item_type="potion", potion_type=potion, rarity=potion.rarity,
            )
        UserInventory.objects.create(id=85, user=self.child, item_id=77, quantity=3)
        MountExpedition.objects.create(
            id=103, mount=self.mount, tier="short", status="active",
            started_at=FIXED_NOW - timedelta(hours=1), returns_at=FIXED_NOW + timedelta(hours=1),
            loot={"coins": 15, "items": []},
        )
        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute(
                    "UPDATE sqlite_sequence SET seq = (SELECT MAX(id) FROM rpg_userinventory) "
                    "WHERE name = 'rpg_userinventory'"
                )
            else:
                for sql in connection.ops.sequence_reset_sql(no_style(), [UserInventory]):
                    cursor.execute(sql)

    def breeding_state(self):
        return (
            self.expedition_reward_state(), self.expedition_rows_state(),
            list(UserMount.objects.order_by("pk").values_list("pk", "user_id", "species_id", "potion_id", "last_bred_at", "is_active", "updated_at")),
        )

    def assert_breeding_success(self, fixture, potion_item_id, chromatic=False):
        before_inventory = {
            (row.user_id, row.item_id): row.quantity for row in UserInventory.objects.all()
        }
        before_progress = self.expedition_reward_state()[1:5]
        before_expeditions = self.expedition_rows_state()
        before_pet_count = UserPet.objects.count()
        before_mount_count = UserMount.objects.count()
        with patch("apps.pets.services.random.choice", side_effect=lambda options: options[0]), patch("apps.pets.services.random.random", return_value=0.001 if chromatic else 0.5):
            response = self.client.post("/api/mounts/breed/", {
                "mount_a_id": 61, "mount_b_id": 62, "user_id": self.outsider.pk,
            }, format="json")
        body = self.assert_response_fixture(response, fixture, status=201)
        self.assertEqual(body["egg_item_id"], 73)
        self.assertEqual(body["egg_lifecycle_stage"], "egg")
        self.assertIsNone(body["egg_item_catalog_icon"])
        self.assertEqual(body["potion_item_id"], potion_item_id)
        self.assertEqual((body["picked_species"], body["picked_species_slug"]), ("Fox", "fixture-fox"))
        self.assertEqual(body["chromatic"], chromatic)
        self.assertEqual(body["cooldown_days"], 7)
        expected_inventory = before_inventory.copy()
        for item_id in (73, potion_item_id):
            key = (self.child.pk, item_id)
            expected_inventory[key] = expected_inventory.get(key, 0) + 1
        self.assertEqual({(row.user_id, row.item_id): row.quantity for row in UserInventory.objects.all()}, expected_inventory)
        self.assertEqual(self.expedition_reward_state()[1:5], before_progress)
        self.assertEqual(self.expedition_rows_state(), before_expeditions)
        self.assertEqual((UserPet.objects.count(), UserMount.objects.count()), (before_pet_count, before_mount_count))
        for mount_id in (61, 62):
            mount = UserMount.objects.get(pk=mount_id)
            self.assertEqual(mount.last_bred_at, FIXED_NOW)
            self.assertEqual(mount.is_active, mount_id == 61)
        self.assertEqual(UserMount.objects.get(pk=63).last_bred_at, FIXED_NOW - timedelta(days=2))
        self.assertTrue(all(UserMount.objects.get(pk=mount_id).last_bred_at is None for mount_id in (81, 82)))
        self.assertEqual(set(Notification.objects.filter(notification_type="mount_bred").values_list("user_id", flat=True)), {6, 7})
        return body

    def test_breeding_stable_eligibility_preserves_ready_away_and_cooldown_mounts(self):
        self.seed_breeding()
        before = self.breeding_state()
        body = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-breeding.json")
        mounts = {row["id"]: row for row in body["mounts"]}
        self.assertTrue(mounts[61]["can_breed"])
        self.assertEqual(mounts[61]["breeding_cooldown_seconds"], 0)
        self.assertEqual(mounts[61]["active_expedition"]["id"], 103)
        self.assertEqual((mounts[62]["can_breed"], mounts[62]["breeding_cooldown_seconds"]), (True, 0))
        self.assertEqual((mounts[63]["can_breed"], mounts[63]["breeding_cooldown_seconds"]), (False, 432000))
        self.assertEqual(self.breeding_state(), before)

    def test_breeding_grants_one_pair_stamps_both_parents_and_preserves_progression(self):
        self.seed_breeding()
        body = self.assert_breeding_success("mount-breed.json", 77)
        self.assertEqual((body["picked_potion"], body["picked_potion_slug"]), ("Ice", "ice"))
        self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-breeding.json")
        stable = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-breeding-after.json")
        for row in stable["mounts"]:
            if row["id"] in (61, 62):
                self.assertEqual((row["can_breed"], row["breeding_cooldown_seconds"]), (False, 604800))
        before_repeat = self.breeding_state()
        response = self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 62}, format="json")
        self.assert_response_fixture(response, "mount-breed-repeat-cooldown.json", status=400)
        self.assertEqual(self.breeding_state(), before_repeat)

    def test_breeding_chromatic_receipt_grants_the_supported_cosmic_potion_once(self):
        self.seed_breeding()
        body = self.assert_breeding_success("mount-breed-chromatic.json", 78, chromatic=True)
        self.assertEqual((body["picked_potion"], body["picked_potion_slug"]), ("Cosmic", "cosmic"))

    def test_breeding_fallback_receipt_uses_registered_compatibility_for_old_parents(self):
        self.seed_breeding()
        self.mount.species.available_potions.set([self.breeding_base])
        body = self.assert_breeding_success("mount-breed-fallback.json", 79)
        self.assertEqual((body["picked_potion"], body["picked_potion_slug"]), ("Base", "base"))
        self.assertNotIn(body["picked_potion_slug"], {self.mount.potion.slug, self.other_mount.potion.slug})

    def test_breeding_rejections_preserve_inventory_parents_and_other_families(self):
        self.seed_breeding()
        before = self.breeding_state()
        for submitted in ({}, {"mount_a_id": 61}, {"mount_b_id": 62}):
            self.assert_response_fixture(self.client.post("/api/mounts/breed/", submitted, format="json"), "mount-breed-missing-mounts.json", status=400)
        self.assert_response_fixture(self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 61}, format="json"), "mount-breed-same-mount.json", status=400)
        self.assert_response_fixture(self.client.post("/api/mounts/breed/", {"mount_a_id": "invalid", "mount_b_id": 62}, format="json"), "mount-breed-invalid-ids.json", status=400)
        for mount_id in (81, 82, 999):
            self.assert_response_fixture(self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": mount_id}, format="json"), "mount-breed-not-owned.json", status=400)
        self.assert_response_fixture(self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 63}, format="json"), "mount-breed-cooldown.json", status=400)
        self.assertEqual(self.breeding_state(), before)
        self.client.credentials()
        response = self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 62}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.breeding_state(), before)

    def test_breeding_service_and_projection_agree_at_the_exact_cooldown_boundary(self):
        self.seed_breeding()
        UserMount.objects.filter(pk=62).update(last_bred_at=FIXED_NOW - timedelta(days=7) + timedelta(microseconds=1))
        before = self.breeding_state()
        stable = self.client.get("/api/pets/stable/").json()
        resting = next(row for row in stable["mounts"] if row["id"] == 62)
        self.assertEqual((resting["can_breed"], resting["breeding_cooldown_seconds"]), (False, 1))
        response = self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 62}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Wolf is still resting — 1 day(s) until it can breed again"})
        self.assertEqual(self.breeding_state(), before)
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(microseconds=1)), patch("apps.pets.services.random.choice", side_effect=lambda options: options[0]), patch("apps.pets.services.random.random", return_value=0.5):
            stable = self.client.get("/api/pets/stable/").json()
            ready = next(row for row in stable["mounts"] if row["id"] == 62)
            self.assertEqual((ready["can_breed"], ready["breeding_cooldown_seconds"]), (True, 0))
            response = self.client.post("/api/mounts/breed/", {"mount_a_id": 61, "mount_b_id": 62}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_stable_and_inventory_preserve_companion_ownership_and_nested_data(self):
        self.seed_companion_care()
        stable = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable.json")
        inventory = self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-food.json")
        self.assertEqual({row["id"] for row in stable["pets"]}, {51, 52, 53})
        self.assertEqual({row["id"] for row in stable["mounts"]}, {61, 62})
        self.assertEqual((stable["total_pets"], stable["total_mounts"], stable["total_possible"]), (3, 2, 4))
        self.assertEqual({row["id"] for row in inventory}, {81, 82, 83, 84})
        foods = [row for row in inventory if row["item"]["item_type"] == "food"]
        self.assertEqual({row["item"]["id"] for row in foods}, {71, 72, 74})
        self.assertIsNone(next(row for row in foods if row["item"]["id"] == 72)["item"]["food_species_name"])
        self.assertEqual(stable["pets"][0]["potion"]["slug"], "fire")
        self.assertIsNone(stable["pets"][0]["last_fed_at"])
        self.assertEqual(next(row for row in stable["pets"] if row["id"] == 52)["happiness_level"], "stale")

    def test_generic_species_lifecycle_is_server_confirmed_at_growth_boundaries(self):
        self.seed_companion_care()
        UserPet.objects.filter(pk=self.pet.pk).update(growth_points=49)
        UserPet.objects.filter(pk=self.ready_pet.pk).update(growth_points=50)
        # Old saved growth does not itself establish the confirmed mount state.
        # Give this saved family its own sort key so raw response order does not
        # depend on how PostgreSQL/SQLite order matching species/potion rows.
        older_wolf = PetSpecies.objects.create(
            id=45, slug="fixture-older-wolf", name="Older Wolf", icon="🐺",
            sprite_key="older-wolf", description="A synthetic saved family.",
        )
        UserPet.objects.create(
            id=54, user=self.child, species=older_wolf,
            potion=self.mount.potion, growth_points=100,
        )
        before = list(UserPet.objects.order_by("pk").values())
        response = self.client.get("/api/pets/stable/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual({pet["id"]: pet["lifecycle_stage"] for pet in body["pets"]}, {
            51: "baby", 52: "middle", 53: "grown", 54: "middle",
        })
        self.assertTrue(all(mount["lifecycle_stage"] == "grown" for mount in body["mounts"]))
        for companion in body["pets"] + body["mounts"]:
            self.assertEqual(companion["species"]["lifecycle_stages"], ["egg", "baby", "middle", "grown"])
            self.assertIsNone(companion["evolution_stage"])
        self.assert_response_fixture(response, "pets-lifecycle-boundaries.json")
        self.assertEqual(list(UserPet.objects.order_by("pk").values()), before)

    def test_inventory_lifecycle_resolves_typed_and_legacy_eggs_without_granting_support(self):
        self.seed_companion_care()
        UserInventory.objects.filter(user=self.child).delete()
        # A typed identity wins over old metadata. Unresolved eggs stay eggs.
        typed = ItemDefinition.objects.get(pk=73)
        typed.metadata = {"species": "fixture-wolf"}
        typed.save(update_fields=["metadata"])
        legacy = ItemDefinition.objects.create(
            id=75, slug="fixture-legacy-egg", name="Legacy Egg", item_type="egg",
            metadata={"species": "fixture-wolf"},
        )
        unknown = ItemDefinition.objects.create(
            id=76, slug="fixture-unknown-egg", name="Unknown Egg", item_type="egg",
        )
        for pk, item in enumerate((typed, legacy, unknown, self.preferred_food), 191):
            UserInventory.objects.create(id=pk, user=self.child, item=item)
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        items = {row["item"]["id"]: row["item"] for row in response.json()}
        self.assertEqual({pk: (item["lifecycle_stage"], item["pet_species_slug"]) for pk, item in items.items()}, {
            73: ("egg", "fixture-fox"), 75: ("egg", "fixture-wolf"),
            76: ("egg", None), 71: (None, None),
        })
        self.assert_response_fixture(response, "inventory-lifecycle-identities.json")

    def test_empty_stable_and_inventory_keep_the_real_response_shapes(self):
        self.seed_companion_care()
        UserPet.objects.filter(user=self.child).delete()
        UserMount.objects.filter(user=self.child).delete()
        UserInventory.objects.filter(user=self.child).delete()
        self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-empty.json")
        self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-empty.json")

    def test_empty_stable_counts_restricted_species_variants(self):
        self.seed_companion_care()
        self.ready_pet.species.available_potions.set([self.ready_pet.potion])
        UserPet.objects.filter(user=self.child).delete()
        UserMount.objects.filter(user=self.child).delete()

        stable = self.assert_response_fixture(
            self.client.get("/api/pets/stable/"), "pets-stable-restricted-empty.json",
        )

        self.assertEqual(stable["total_possible"], 3)
        self.assertTrue(UserPet.objects.filter(user=self.sibling).exists())
        self.assertTrue(UserMount.objects.filter(user=self.outsider).exists())

    def test_feed_consumes_one_food_and_returns_confirmed_growth(self):
        self.seed_companion_care()
        response = self.client.post("/api/pets/51/feed/", {"food_item_id": 71}, format="json")
        body = self.assert_response_fixture(response, "pet-feed.json")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, body["new_growth"])
        self.assertEqual(self.pet.last_fed_at, FIXED_NOW)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.preferred_food).quantity, 1)
        self.assertFalse(self.pet.evolved_to_mount)
        self.assertFalse(body["evolved"])
        self.assertEqual(body["lifecycle_stage"], "baby")
        self.assertIsNone(body["mount_id"])
        self.assertEqual(UserInventory.objects.get(user=self.sibling, item=self.preferred_food).quantity, 2)

    def test_neutral_feed_depletes_food_without_evolving(self):
        self.seed_companion_care()
        response = self.client.post("/api/pets/51/feed/", {"food_item_id": 72}, format="json")
        body = self.assert_response_fixture(response, "pet-feed-neutral.json")
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, body["new_growth"])
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.neutral_food).exists())

    def test_feed_evolution_creates_the_confirmed_mount_and_retains_pet(self):
        self.seed_companion_care()
        self.pin_next_mount_identity()
        response = self.client.post("/api/pets/52/feed/", {"food_item_id": 74}, format="json")
        body = self.assert_response_fixture(response, "pet-feed-evolved.json")
        self.ready_pet.refresh_from_db()
        self.assertTrue(self.ready_pet.evolved_to_mount)
        self.assertEqual(self.ready_pet.growth_points, 100)
        self.assertEqual(self.ready_pet.last_fed_at, FIXED_NOW)
        self.assertEqual(body["new_growth"], self.ready_pet.growth_points)
        self.assertTrue(body["evolved"])
        self.assertEqual(body["lifecycle_stage"], "grown")
        mount = UserMount.objects.get(pk=body["mount_id"], user=self.child)
        self.assertEqual((mount.species_id, mount.potion_id), (self.ready_pet.species_id, self.ready_pet.potion_id))
        self.assertFalse(mount.is_active)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.wolf_food).exists())

    def test_activating_pet_and_mount_exclusively_switches_confirmed_ownership(self):
        self.seed_companion_care()
        pet = self.assert_response_fixture(self.client.post("/api/pets/52/activate/"), "pet-activate.json")
        mount = self.assert_response_fixture(self.client.post("/api/mounts/62/activate/"), "mount-activate.json")
        self.assertEqual(pet["id"], self.ready_pet.pk)
        self.assertTrue(pet["is_active"])
        self.assertEqual(mount["id"], self.other_mount.pk)
        self.assertTrue(mount["is_active"])
        self.assertEqual(list(UserPet.objects.filter(user=self.child, is_active=True).values_list("pk", flat=True)), [52])
        self.assertEqual(list(UserMount.objects.filter(user=self.child, is_active=True).values_list("pk", flat=True)), [62])

    def test_rejected_feed_does_not_consume_food_or_change_growth(self):
        self.seed_companion_care()
        response = self.client.post("/api/pets/51/feed/", {}, format="json")
        self.assert_response_fixture(response, "pet-feed-missing-food.json", status=400)
        response = self.client.post("/api/pets/51/feed/", {"food_item_id": 999}, format="json")
        self.assert_response_fixture(response, "pet-feed-unavailable-food.json", status=400)
        response = self.client.post("/api/pets/53/feed/", {"food_item_id": 71}, format="json")
        self.assert_response_fixture(response, "pet-feed-already-evolved.json", status=400)
        self.pet.refresh_from_db()
        self.assertEqual(self.pet.growth_points, 20)
        self.assertIsNone(self.pet.last_fed_at)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.preferred_food).quantity, 2)

    def test_foreign_and_unknown_companions_cannot_be_fed_or_activated(self):
        self.seed_companion_care()
        for row_id in (81, 82, 999):
            with self.subTest(row_id=row_id):
                response = self.client.post(f"/api/pets/{row_id}/feed/", {"food_item_id": 71}, format="json")
                self.assert_response_fixture(response, "pet-not-owned.json", status=400)
                response = self.client.post(f"/api/pets/{row_id}/activate/")
                self.assert_response_fixture(response, "pet-not-owned.json", status=400)
                response = self.client.post(f"/api/mounts/{row_id}/activate/")
                self.assert_response_fixture(response, "mount-not-owned.json", status=400)
        self.pet.refresh_from_db()
        self.mount.refresh_from_db()
        self.assertTrue(self.pet.is_active)
        self.assertTrue(self.mount.is_active)
        self.assertEqual(self.pet.growth_points, 20)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.preferred_food).quantity, 2)
        for owner in (self.sibling, self.outsider):
            self.assertEqual(UserPet.objects.get(user=owner).growth_points, 10)
            self.assertTrue(UserPet.objects.get(user=owner).is_active)
            self.assertTrue(UserMount.objects.get(user=owner).is_active)

    def test_companion_care_requires_authentication(self):
        self.seed_companion_care()
        self.client.credentials()
        for path, method, body in (
            ("/api/pets/stable/", "get", None), ("/api/inventory/", "get", None),
            ("/api/pets/51/feed/", "post", {"food_item_id": 71}),
            ("/api/pets/51/activate/", "post", {}), ("/api/mounts/61/activate/", "post", {}),
        ):
            with self.subTest(path=path):
                response = self.client.get(path) if method == "get" else self.client.post(path, body, format="json")
                self.assertEqual(response.status_code, 401)

    def test_login_and_verified_identity(self):
        with patch("rest_framework.authtoken.models.Token.generate_key", return_value=SYNTHETIC_TOKEN):
            login = self.client.post("/api/auth/", {
                "action": "login", "username": self.child.username, "password": "synthetic-password",
            }, format="json")
        body = self.assert_response_fixture(login, "auth-login-child.json")
        self.assertEqual(body["token"], Token.objects.get(user=self.child).key)
        self.assertFalse(Token.objects.filter(key=self.auth_token.key).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {body['token']}")
        identity = self.assert_response_fixture(self.client.get("/api/auth/me/"), "auth-me-child.json")
        self.assertEqual({key: value for key, value in body.items() if key != "token"}, identity)

    def test_paginated_habits_preserve_scope_and_safety_fields(self):
        first = self.assert_response_fixture(self.client.get("/api/habits/"), "habits-page-1.json")
        second = self.assert_response_fixture(self.client.get(first["next"]), "habits-page-2.json")
        self.assertEqual(first["count"], 21)
        self.assertEqual(len(first["results"]), 20)
        self.assertEqual(len(second["results"]), 1)
        self.assertEqual({row["id"] for row in first["results"] + second["results"]}, set(range(9, 30)))
        self.assertTrue(all(row["user"] == self.child.pk for row in first["results"] + second["results"]))
        self.assertFalse(any(row["pending_parent_review"] for row in first["results"] + second["results"]))

    def test_notification_pages_stay_same_origin_across_proxy_hops(self):
        for index in range(21):
            notification = Notification.objects.create(
                id=101 + index, user=self.child, title=f"Fixture update {index + 1:02d}",
                message="A synthetic saved update.", notification_type=NotificationType.DROP_RECEIVED,
                link="/inventory",
            )
            Notification.objects.filter(pk=notification.pk).update(
                created_at=FIXED_NOW - timedelta(minutes=index),
            )
        for row_id, owner in ((201, self.sibling), (202, self.outsider)):
            Notification.objects.create(
                id=row_id, user=owner, title="Private update", notification_type=NotificationType.JOURNAL_REPLY,
            )
        namespace = "0123456789abcdef0123456789abcdef"
        first_path = f"/api/notifications/?_abby_session={namespace}"
        second_path = first_path + "&page=2"
        # Cloudflare's HTTPS tunnel reaches Traefik over HTTP. Its untrusted
        # forwarded protocol may be replaced by that hop's HTTP protocol.
        for headers in ({}, {"secure": True}, {
            "HTTP_HOST": "internal:8000", "HTTP_X_FORWARDED_HOST": "testserver",
            "HTTP_X_FORWARDED_PROTO": "http",
        }, {"HTTP_X_FORWARDED_PROTO": "https"}):
            with self.subTest(headers=headers):
                response = self.client.get(first_path, **headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["next"], second_path)
                first = self.assert_response_fixture(response, "notifications-page-1.json")
                second = self.assert_response_fixture(
                    self.client.get(first["next"], **headers), "notifications-page-2.json",
                )
                self.assertEqual((first["count"], len(first["results"]), len(second["results"])), (21, 20, 1))
                self.assertIsNone(first["previous"])
                self.assertIsNone(second["next"])
                self.assertEqual(second["previous"], first_path)
                self.assertEqual(
                    [row["id"] for row in first["results"] + second["results"]], list(range(101, 122)),
                )
                self.assert_response_fixture(
                    self.client.get(second["previous"], **headers), "notifications-page-1.json",
                )
        self.assertEqual(Notification.objects.filter(user=self.child, is_read=False).count(), 21)
        self.assertEqual(self.client.get("/api/notifications/unread_count/").json()["count"], 21)
        for row_id in (201, 202):
            self.assertEqual(self.client.post(f"/api/notifications/{row_id}/mark_read/").status_code, 404)
            self.assertFalse(Notification.objects.get(pk=row_id).is_read)

    def test_empty_notification_page_and_authentication(self):
        self.assert_response_fixture(self.client.get("/api/notifications/"), "notifications-empty.json")
        self.client.credentials()
        self.assertEqual(self.client.get("/api/notifications/").status_code, 401)

    def test_empty_habits_still_use_pagination_envelope(self):
        Habit.objects.filter(user=self.child, pending_parent_review=False).delete()
        self.assert_response_fixture(self.client.get("/api/habits/"), "habits-empty.json")

    def test_confirmed_positive_tap_and_rejected_duplicate(self):
        DailyChallenge.objects.create(
            id=3, user=self.child, date=FIXED_NOW.date(), challenge_type="habits", target_value=2,
        )
        # Only the random input is fixed; no service/serializer result is mocked.
        with patch("apps.rpg.services.random.random", return_value=1.0):
            response = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        body = self.assert_response_fixture(response, "habit-positive-tap.json")
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 5)
        self.assertEqual(CharacterProfile.objects.get(user=self.child).login_streak, body["game_event"]["streak"]["streak"])
        rejected = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        self.assert_response_fixture(rejected, "habit-positive-tap-limit.json", status=400)
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])

    def test_confirmed_positive_tap_without_optional_game_event(self):
        # A missing optional event does not invalidate the persisted base tap.
        # This scenario alone replaces the game-loop boundary, never the view
        # or HabitService result; the ordinary fixture above runs the real loop.
        with patch("apps.rpg.services.GameLoopService.on_task_completed", return_value=None):
            response = self.client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        body = self.assert_response_fixture(response, "habit-positive-tap-no-event.json")
        self.assertIsNone(body["game_event"])
        self.habit.refresh_from_db()
        self.assertEqual(self.habit.strength, body["new_strength"])
        self.assertEqual(HabitLog.objects.filter(habit=self.habit, direction=1).count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 5)
