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
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.quests.models import DailyChallenge
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests.factories import make_family


FIXTURE_DIR = Path(settings.BASE_DIR) / "contracts" / "api" / "fixtures"
FIXED_NOW = datetime(2026, 10, 10, 19, 0, tzinfo=datetime_timezone.utc)
SYNTHETIC_TOKEN = "0123456789012345678901234567890123456789"


@override_settings(
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

    def test_empty_stable_and_inventory_keep_the_real_response_shapes(self):
        self.seed_companion_care()
        UserPet.objects.filter(user=self.child).delete()
        UserMount.objects.filter(user=self.child).delete()
        UserInventory.objects.filter(user=self.child).delete()
        self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-stable-empty.json")
        self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-empty.json")

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
