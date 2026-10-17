"""Automatic challenge bodies produced by real authenticated Django requests.

Only clocks, table sequences and drop randomness are controlled. The goals,
movement logging, game loop, rewards, serializers and permissions remain real.
"""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from django.core.cache import cache
from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.movement.models import MovementSession, MovementType, MovementTypeSkillTag
from apps.quests.models import QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests import test_api_contract_fixtures as shared_fixtures
from config.tests.factories import make_family


FIXED_NOW = datetime(2026, 10, 14, 19, tzinfo=timezone.utc)


@override_settings(
    ALLOWED_HOSTS=["testserver"], TIME_ZONE="America/Phoenix", USE_TZ=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "challenge-api-contract-fixtures",
    }},
    VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="",
)
class ChallengeApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared_fixtures.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        super().setUp()
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        random_input = patch("apps.rpg.services.random.random", return_value=1.0)
        random_input.start()
        self.addCleanup(random_input.stop)
        household = make_family(
            "Challenge Fixture Family", family_id=41,
            parents=[{"id": 6, "username": "challenge-fixture-parent"}],
            children=[
                {"id": 7, "username": "challenge-fixture-child"},
                {"id": 8, "username": "challenge-fixture-sibling"},
            ],
        )
        self.child, self.sibling = household.children
        self.parent = household.parents[0]
        other = make_family(
            "Other Challenge Fixture Family", family_id=42,
            parents=[{"id": 98, "username": "challenge-fixture-other-parent"}],
            children=[{"id": 99, "username": "challenge-fixture-other-child"}],
        )
        self.other_parent, self.other_child = other.parents[0], other.children[0]
        category = SkillCategory.objects.create(id=21, name="Physical")
        self.skill = Skill.objects.create(id=22, name="Running", category=category)
        self.running = MovementType.objects.create(id=31, name="Running", slug="fixture-running", icon="🏃")
        MovementTypeSkillTag.objects.create(movement_type=self.running, skill=self.skill, xp_weight=1)
        self.catalog = QuestDefinition.objects.create(
            id=51, name="Two movement sessions", description="Log two movement sessions during this window.",
            quest_type="collection", target_value=2, duration_days=7,
            trigger_filter={"allowed_triggers": ["movement_session"]},
            coin_reward=5, xp_reward=10, is_system=True,
        )
        QuestSkillTag.objects.create(quest_definition=self.catalog, skill=self.skill, xp_weight=1)
        # Reset only fixture tables so endpoint-generated identities survive
        # PostgreSQL's nontransactional sequences and arbitrary suite order.
        from apps.quests.models import (
            ChallengeActivity, ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, DailyBonus,
            Quest, QuestParticipant,
        )
        ChallengeEnrollment.objects.create(user=self.child, starts_at=FIXED_NOW, timezone_name="America/Phoenix")
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [
                ChallengeGoal, ChallengeOccurrence, ChallengeActivity, DailyBonus, MovementSession,
                Quest, QuestParticipant,
            ]):
                cursor.execute(sql)
        self.tokens = {
            user.pk: Token.objects.create(user=user, key=key * 40)
            for user, key in [(self.parent, "p"), (self.child, "c"), (self.sibling, "s"), (self.other_parent, "o")]
        }
        self.authenticate(self.parent)
        self.goal_payload = {
            "request_id": "33333333-3333-4333-8333-333333333333",
            "user_id": self.child.pk, "name": "Run 2 miles this week",
            "trigger_type": "movement_session", "movement_type_id": self.running.pk,
            "metric": "distance", "target": "2", "unit": "mi",
            "period": "this_week", "repeat_weekly": True,
            "coin_reward": 7, "xp_reward": 15,
            "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
        }

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.tokens[user.pk].key}")

    def create_goal(self, **changes):
        return self.client.post("/api/challenges/goals/", {**self.goal_payload, **changes}, format="json")

    def state(self):
        return (
            list(CoinLedger.objects.order_by("pk").values_list("user_id", "amount", "reason")),
            list(SkillProgress.objects.order_by("pk").values_list("user_id", "skill_id", "xp_points")),
        )

    def log_run(self, distance):
        return self.client.post("/api/movement-sessions/", {
            "movement_type_id": self.running.pk, "duration_minutes": 20,
            "distance": distance, "distance_unit": "mi", "notes": "A fixture run.",
            "client_request_id": "11111111-1111-4111-8111-111111111111" if distance == "0.75" else "22222222-2222-4222-8222-222222222222",
        }, format="json")

    def test_parent_goal_pin_and_two_real_runs_preserve_automatic_rewards(self):
        created = self.assert_response_fixture(self.create_goal(), "challenge-goal-created.json", status=201)
        self.assertEqual(created["origin"], "parent")
        self.assertEqual((created["metric"], created["target"], created["unit"]), ("distance", "2", "mi"))
        self.assertTrue(created["repeat_weekly"])
        self.assertEqual(created["reward_receipt"]["status"], "pending")
        self.assertNotIn("items", created["reward_receipt"])
        self.assertEqual(CoinLedger.objects.count(), 0)
        replay = self.create_goal().json()
        for key in ("starts_at", "ends_at"):
            # A reloaded PostgreSQL/SQLite datetime may render in UTC rather
            # than the construction timezone; the saved window is identical.
            self.assertEqual(datetime.fromisoformat(replay.pop(key)), datetime.fromisoformat(created[key]))
        self.assertEqual(replay, {key: value for key, value in created.items() if key not in {"starts_at", "ends_at"}})
        self.assertEqual(self.create_goal(name="Conflicting retry").status_code, 409)
        self.authenticate(self.child)
        initial = self.assert_response_fixture(self.client.get("/api/challenges/"), "challenges-initial.json")
        self.assertEqual(len(initial["results"]), 2)
        self.assertEqual({goal["origin"] for goal in initial["results"]}, {"parent", "catalog"})
        self.assertIsNone(initial["pin"])
        before = self.state()
        pinned = self.assert_response_fixture(
            self.client.post(f"/api/challenges/{created['id']}/pin/", {}, format="json"), "challenge-pinned.json",
        )
        self.assertEqual(pinned, {"pin": created["id"]})
        selected = self.client.get("/api/challenges/").json()
        self.assertEqual(selected["pin"], created["id"])
        self.assertEqual([goal["id"] for goal in selected["results"] if goal["pinned"]], [created["id"]])
        self.assertEqual(self.state(), before)

        first = self.assert_response_fixture(self.log_run("0.75"), "challenge-run-first.json", status=201)
        self.assertEqual((first["distance"], first["distance_unit"]), ("0.75", "mi"))
        self.assertEqual(first["distance_meters"], "1207.008")
        self.assertEqual(len(first["challenge_receipts"][0]["goals"]), 2)
        saved = self.state()
        self.assertEqual(self.log_run("0.75").json(), first)
        self.assertEqual(self.state(), saved)
        partial = self.assert_response_fixture(self.client.get("/api/challenges/"), "challenges-partial.json")
        distance_goal = next(goal for goal in partial["results"] if goal["id"] == created["id"])
        other_goal = next(goal for goal in partial["results"] if goal["id"] != created["id"])
        self.assertEqual((distance_goal["progress"], other_goal["progress"]), ("0.75", "1"))
        self.assertEqual(partial["daily_bonus"]["awarded"], True)

        unpinned = self.assert_response_fixture(
            self.client.delete(f"/api/challenges/{created['id']}/pin/"), "challenge-unpinned.json",
        )
        self.assertEqual(unpinned, {"pin": None})
        second = self.assert_response_fixture(self.log_run("1.25"), "challenge-run-completed.json", status=201)
        self.assertEqual(second["distance"], "1.25")
        self.assertEqual(second["distance_meters"], "2011.680")
        self.assertTrue(all(goal["completed"] for goal in second["challenge_receipts"][0]["goals"]))
        completed = self.assert_response_fixture(self.client.get("/api/challenges/"), "challenges-completed.json")
        self.assertIsNone(completed["pin"])
        self.assertTrue(all(goal["status"] == "completed" for goal in completed["results"]))
        self.assertEqual(sorted(goal["reward_receipt"]["coins_awarded"] for goal in completed["results"]), [5, 7])
        self.assertEqual(sorted(goal["reward_receipt"]["xp_awarded"] for goal in completed["results"]), [10, 15])
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 65)
        paid = self.state()
        self.assertEqual(self.client.get("/api/challenges/").json(), completed)
        self.assertEqual(self.state(), paid)
        self.assertEqual(MovementSession.objects.filter(user=self.child).count(), 2)
        self.assertFalse(CoinLedger.objects.filter(user=self.sibling).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.other_child).exists())

    def test_goal_validation_and_family_scope_reject_without_rewards(self):
        invalid = self.assert_response_fixture(self.create_goal(target="0"), "challenge-goal-invalid.json", status=400)
        self.assertIn("target", invalid)
        before = self.state()
        foreign = self.create_goal(user_id=self.other_child.pk)
        unknown = self.create_goal(user_id=99999)
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(foreign.json(), unknown.json())
        self.assertEqual(self.state(), before)
        self.authenticate(self.child)
        self.assertEqual(self.create_goal().status_code, 403)
        self.client.credentials()
        self.assertEqual(self.client.get("/api/challenges/").status_code, 401)

    def test_goal_origin_uses_saved_authorship_instead_of_matching_names(self):
        spoofed = self.create_goal(name=self.catalog.name, origin="catalog")
        self.assertEqual(spoofed.status_code, 400, spoofed.content)
        self.assertIn("origin", spoofed.json())
        created = self.create_goal(name=self.catalog.name)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json().get("origin"), "parent")
        self.authenticate(self.child)
        listed = self.client.get("/api/challenges/").json()
        self.assertEqual({row["name"] for row in listed["results"]}, {self.catalog.name})
        self.assertEqual({row["id"]: row.get("origin") for row in listed["results"]}, {
            created.json()["id"]: "parent", "goal:2": "catalog",
        })
        self.assertEqual(self.state(), ([], []))

    def test_retired_catalog_and_saved_legacy_origins_preserve_goal_promises(self):
        from apps.quests.models import ChallengeGoal, Quest, QuestParticipant
        created = self.create_goal(name=self.catalog.name)
        self.assertEqual(created.status_code, 201, created.content)
        self.authenticate(self.child)
        initial = self.client.get("/api/challenges/").json()
        saved = {row["id"]: row for row in initial["results"]}
        catalog_goal = ChallengeGoal.objects.get(catalog_definition=self.catalog, user=self.child)
        self.catalog.delete()
        catalog_goal.refresh_from_db()
        self.assertIsNone(catalog_goal.catalog_definition_id)
        self.assertTrue(catalog_goal.is_catalog)
        legacy_definition = QuestDefinition.objects.create(
            id=52, name=catalog_goal.name, description="A saved family challenge.",
            quest_type="collection", target_value=3, duration_days=7,
            trigger_filter={"allowed_triggers": ["movement_session"]},
            coin_reward=4, xp_reward=0, is_system=False, created_by=self.parent,
        )
        legacy = Quest.objects.create(
            id=91, definition=legacy_definition, start_date=FIXED_NOW,
            end_date=FIXED_NOW + timedelta(days=7), current_progress=1,
        )
        QuestParticipant.objects.create(quest=legacy, user=self.child, contribution=1)
        response = self.client.get("/api/challenges/")
        body = response.json()
        self.assertEqual({row["name"] for row in body["results"]}, {catalog_goal.name})
        self.assertEqual({row["id"]: row.get("origin") for row in body["results"]}, {
            created.json()["id"]: "parent", "goal:2": "catalog", "legacy:91": "legacy",
        })
        for row in body["results"]:
            if row["id"] in saved:
                self.assertEqual(row, saved[row["id"]])
        self.assertEqual(self.state(), ([], []))
        self.assertEqual(self.client.get("/api/challenges/").json(), body)
        self.assert_response_fixture(response, "challenges-origins.json")

    def test_origin_metadata_preserves_child_and_family_scope(self):
        created = self.create_goal(name="A private family goal")
        self.assertEqual(created.status_code, 201, created.content)
        own = self.client.get("/api/challenges/", {"user_id": self.child.pk}).json()
        self.assertEqual(next(row for row in own["results"] if row["id"] == created.json()["id"]).get("origin"), "parent")
        foreign = self.client.get("/api/challenges/", {"user_id": self.other_child.pk})
        unknown = self.client.get("/api/challenges/", {"user_id": 99999})
        self.assertEqual((foreign.status_code, unknown.status_code), (404, 404))
        self.assertEqual(foreign.json(), unknown.json())
        self.authenticate(self.child)
        self.assertEqual(self.client.get("/api/challenges/", {"user_id": self.sibling.pk}).status_code, 404)
        self.authenticate(self.sibling)
        sibling = self.client.get("/api/challenges/").json()
        self.assertNotIn(created.json()["id"], [row["id"] for row in sibling["results"]])
        self.assertTrue(all(row.get("origin") == "catalog" for row in sibling["results"]))
        self.assertEqual(self.state(), ([], []))

    def add_second_movement_catalog_goal(self):
        return QuestDefinition.objects.create(
            id=52, name="Another two movement sessions", quest_type="collection", target_value=2,
            duration_days=7, trigger_filter={"allowed_triggers": ["movement_session"]},
            coin_reward=2, xp_reward=0, is_system=True,
        )

    def test_receipt_timestamps_tie_without_changing_newest_first_order_or_awards(self):
        from apps.quests.models import ChallengeActivity, ChallengeOccurrence
        self.add_second_movement_catalog_goal()
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        first = self.log_run("0.75").json()["challenge_receipts"][0]
        second = self.log_run("1.25").json()["challenge_receipts"][0]
        self.assertEqual(len(set(ChallengeActivity.objects.values_list("created_at", flat=True))), 1)
        self.assertEqual(len(set(ChallengeOccurrence.objects.values_list("awarded_at", flat=True))), 1)
        paid = self.state()
        body = self.client.get("/api/challenges/").json()
        # Confirm the complete recorded outcomes and balances before checking
        # ordering: a tie must not swap which activity earned the daily bonus.
        self.assertEqual(sorted(body["challenge_receipts"], key=lambda row: row["id"]), [first, second])
        self.assertEqual(self.state(), paid)
        self.assertEqual(body["challenge_receipts"], [second, first])
        ids = [row["id"] for row in body["recent_receipts"]]
        self.assertEqual(ids, sorted(ids, key=lambda key: int(key.split(":")[1]), reverse=True))
        self.assertEqual(self.client.get("/api/challenges/").json(), body)
        self.assertEqual(self.state(), paid)

    def test_parent_and_catalog_goal_deltas_have_stable_ascending_identities(self):
        self.assertEqual(self.create_goal().status_code, 201)
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        first = self.log_run("0.75").json()["challenge_receipts"][0]
        self.assertEqual([row["id"] for row in first["goals"]], ["goal:1", "goal:2"])
        second = self.log_run("1.25").json()["challenge_receipts"][0]
        self.assertEqual([row["id"] for row in second["goals"]], ["goal:1", "goal:2"])
        self.assertTrue(all(row["completed"] for row in second["goals"]))
        paid = self.state()
        self.assertEqual(self.log_run("1.25").json()["challenge_receipts"][0], second)
        self.assertEqual(self.state(), paid)

    def test_ended_windows_with_equal_deadlines_have_stable_newest_first_history(self):
        self.add_second_movement_catalog_goal()
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        with patch("django.utils.timezone.now", return_value=FIXED_NOW + timedelta(days=8)):
            body = self.client.get("/api/challenges/").json()
        self.assertEqual([row["status"] for row in body["results"]], ["expired", "expired"])
        ids = [row["id"] for row in body["results"]]
        self.assertEqual(ids, sorted(ids, key=lambda key: int(key.split(":")[1]), reverse=True))
        self.assertEqual(self.state(), ([], []))

    def test_daily_receipt_reports_lucky_coin_actual_amount_with_unchanged_goal_reward(self):
        created = self.create_goal(target="0.75", name="Run 0.75 miles this week")
        self.assertEqual(created.status_code, 201, created.content)
        profile = CharacterProfile.objects.get(user=self.child)
        profile.coin_boost_expires_at = FIXED_NOW + timedelta(hours=1)
        profile.save(update_fields=["coin_boost_expires_at"])
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        goals = self.assert_response_fixture(self.client.get("/api/challenges/"), "challenges-boosted.json")
        parent_goal = next(goal for goal in goals["results"] if goal["id"] == created.json()["id"])
        self.assertEqual(parent_goal["rewards"]["coins"], 7)
        self.assertEqual(parent_goal["reward_receipt"]["coins_awarded"], 7)
        self.assertEqual(goals["daily_bonus"]["coin_reward"], 10)
        self.assertEqual(goals["daily_bonus"]["coins_awarded"], 20)
        self.assertTrue(CoinLedger.objects.filter(user=self.child, reason="daily_challenge", amount=20).exists())

    def test_goal_xp_receipt_matches_actual_weighted_skill_credit(self):
        endurance = Skill.objects.create(id=23, name="Endurance", category=self.skill.category)
        created = self.create_goal(target="0.75", coin_reward=0, skill_tags=[
            {"skill_id": self.skill.pk, "xp_weight": 1}, {"skill_id": endurance.pk, "xp_weight": 1},
        ])
        self.assertEqual(created.status_code, 201, created.content)
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        goals = self.client.get("/api/challenges/").json()
        parent_goal = next(goal for goal in goals["results"] if goal["id"] == created.json()["id"])
        actual_total = sum(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True))
        # The single movement session awarded ten Running XP and the daily
        # bonus awarded twenty more. The remainder is this goal's real award,
        # including the existing weighted-distribution rounding behavior.
        self.assertEqual(parent_goal["rewards"]["xp"], 15)
        self.assertEqual(parent_goal["reward_receipt"]["xp_awarded"], actual_total - 30)

    def test_saved_future_goal_remains_visible_without_counting_early_work(self):
        created = self.create_goal(
            period="custom", start_date="2026-10-16", end_date="2026-10-18", repeat_weekly=False,
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.authenticate(self.child)
        listed = self.client.get("/api/challenges/").json()
        upcoming = next((goal for goal in listed["results"] if goal["id"] == created.json()["id"]), None)
        self.assertIsNotNone(upcoming, "A saved future goal must remain visible before its first day")
        self.assertEqual(upcoming["status"], "upcoming")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        later = self.client.get("/api/challenges/").json()
        future = next(goal for goal in later["results"] if goal["id"] == created.json()["id"])
        self.assertEqual(future["progress"], "0")
        self.assertEqual(future["reward_receipt"]["status"], "pending")

    def test_legacy_start_cannot_duplicate_an_automatically_tracking_catalog_reward(self):
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        # An old client or a direct authenticated request must not create a
        # second independently paying copy of an already tracking catalog goal.
        self.client.post("/api/quests/start/", {"definition_id": self.catalog.pk}, format="json")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        self.assertEqual(self.log_run("1.25").status_code, 201)
        payouts = CoinLedger.objects.filter(user=self.child, description__contains=self.catalog.name)
        self.assertEqual(payouts.count(), 1, "The legacy start route paid the same automatically tracked catalog goal twice")

    def test_goal_receipt_does_not_claim_xp_for_a_locked_skill(self):
        locked = Skill.objects.create(id=23, name="Locked endurance", category=self.skill.category, is_locked_by_default=True)
        created = self.create_goal(target="0.75", skill_tags=[{"skill_id": locked.pk, "xp_weight": 1}])
        self.assertEqual(created.status_code, 201, created.content)
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        listed = self.client.get("/api/challenges/").json()
        goal = next(row for row in listed["results"] if row["id"] == created.json()["id"])
        locked_progress = SkillProgress.objects.filter(user=self.child, skill=locked).first()
        actual = locked_progress.xp_points if locked_progress else 0
        self.assertEqual(actual, 0)
        self.assertEqual(goal["reward_receipt"]["xp_awarded"], actual)

    def test_daily_receipt_does_not_claim_xp_for_locked_source_tags(self):
        locked = Skill.objects.create(id=23, name="Locked endurance", category=self.skill.category, is_locked_by_default=True)
        self.running.skill_tags.all().delete()
        MovementTypeSkillTag.objects.create(movement_type=self.running, skill=locked, xp_weight=1)
        self.authenticate(self.child)
        self.client.get("/api/challenges/")
        self.assertEqual(self.log_run("0.75").status_code, 201)
        daily = self.client.get("/api/challenges/").json()["daily_bonus"]
        self.assertTrue(daily["awarded"])
        self.assertEqual(daily["xp_awarded"], 0)
        self.assertEqual(sum(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True)), 0)

    def test_catalog_preview_and_actual_grants_use_the_same_supported_art_policy(self):
        frame = ItemDefinition.objects.create(id=61, name="Fixture frame", slug="fixture-frame", item_type="cosmetic_frame")
        accessory = ItemDefinition.objects.create(
            id=62, name="Unavailable fixture accessory", slug="fixture-accessory", item_type="cosmetic_pet_accessory",
        )
        for item in (frame, accessory):
            QuestRewardItem.objects.create(quest_definition=self.catalog, item=item, quantity=1)
        self.authenticate(self.child)
        listed = self.client.get("/api/challenges/").json()
        preview = next(goal for goal in listed["results"] if goal["name"] == self.catalog.name)
        self.assertEqual(len(preview["rewards"]["items"]), 1)
        self.assertEqual(preview["rewards"]["items"][0]["item_name"], frame.name)
        self.assertEqual(self.log_run("0.75").status_code, 201)
        self.assertEqual(self.log_run("1.25").status_code, 201)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=accessory).exists())
        response = self.client.get("/api/challenges/")
        completed = response.json()
        goal = next(row for row in completed["results"] if row["id"] == preview["id"])
        self.assertEqual(goal["reward_receipt"]["coins_awarded"], 5)
        self.assertEqual(goal["reward_receipt"]["items"], [{"item_name": frame.name, "item_catalog_icon": None, "quantity": 1}])
        self.assert_response_fixture(response, "challenges-items-delivered.json")
        paid = self.state()
        self.assertEqual(self.log_run("1.25").status_code, 201)
        self.assertEqual(self.client.get("/api/challenges/").json(), completed)
        self.assertEqual(self.state(), paid)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=frame).quantity, 1)

    def add_synthetic_egg_reward(self):
        from apps.pets.models import PetSpecies, PotionType
        species = PetSpecies.objects.create(
            id=81, name="Fixture Wolf", slug="fixture-wolf", sprite_key="fixture-wolf", icon="🐺",
        )
        potion = PotionType.objects.create(id=82, name="Fixture Base", slug="base", sprite_key="potion-base")
        egg = ItemDefinition.objects.create(
            id=63, name="Fixture Wolf Egg", slug="fixture-wolf-egg", item_type="egg",
            pet_species=species, coin_value=25,
        )
        QuestRewardItem.objects.create(quest_definition=self.catalog, item=egg, quantity=1)
        policy = {
            "schema_version": 1, "potion_slugs": ["base"], "disabled_item_types": ["cosmetic_pet_accessory"],
            "pets": [{"species_slug": species.slug, "sprite_key": species.sprite_key, "potion_slugs": ["base"]}],
        }
        return species, potion, egg, policy

    def test_catalog_receipt_delivers_its_frozen_item_after_support_retirement(self):
        _, _, egg, policy = self.add_synthetic_egg_reward()
        self.authenticate(self.child)
        with self.settings(RPG_ASSET_SUPPORT_POLICY=policy):
            preview = self.client.get("/api/challenges/").json()["results"][0]
            self.assertEqual(preview["rewards"]["items"][0]["item_name"], egg.name)
        self.assertEqual(self.log_run("0.75").status_code, 201)
        self.assertEqual(self.log_run("1.25").status_code, 201)
        response = self.client.get("/api/challenges/")
        completed = response.json()
        self.assertEqual(completed["results"][0]["reward_receipt"]["items"], [{
            "item_name": egg.name, "item_catalog_icon": None, "quantity": 1,
        }])
        self.assert_response_fixture(response, "challenges-items-promised-retired.json")
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 1)
        paid = self.state()
        self.log_run("1.25")
        self.assertEqual(self.client.get("/api/challenges/").json(), completed)
        self.assertEqual(self.state(), paid)

    def test_new_catalog_snapshot_excludes_items_unavailable_before_acceptance(self):
        _, _, egg, _policy = self.add_synthetic_egg_reward()
        self.authenticate(self.child)
        preview = self.client.get("/api/challenges/").json()["results"][0]
        self.assertEqual(preview["rewards"]["items"], [])
        self.assertEqual(self.log_run("0.75").status_code, 201)
        self.assertEqual(self.log_run("1.25").status_code, 201)
        response = self.client.get("/api/challenges/")
        self.assertEqual(response.json()["results"][0]["reward_receipt"]["items"], [])
        self.assert_response_fixture(response, "challenges-items-skipped.json")
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=egg).exists())

    def test_accepted_legacy_quest_keeps_its_item_visible_and_pays_it_once_after_retirement(self):
        _, _, egg, policy = self.add_synthetic_egg_reward()
        definition = QuestDefinition.objects.create(
            id=91, name="Saved egg promise", description="A synthetic accepted family quest.",
            quest_type="collection", target_value=1, duration_days=7,
            trigger_filter={"allowed_triggers": ["movement_session"]},
            coin_reward=7, xp_reward=0, is_system=False, created_by=self.parent,
        )
        QuestRewardItem.objects.create(id=92, quest_definition=definition, item=egg, quantity=2)
        self.authenticate(self.child)
        with self.settings(RPG_ASSET_SUPPORT_POLICY=policy):
            started = self.client.post("/api/quests/start/", {"definition_id": definition.pk}, format="json")
            self.assertEqual(started.status_code, 201)
            accepted = started.json()
        active = self.client.get("/api/quests/active/")
        self.assertEqual(active.status_code, 200)
        promised = active.json()["definition"]["reward_items"]
        self.assertEqual([(row["item"], row["quantity"]) for row in promised], [(egg.pk, 2)])
        self.assertEqual(active.json(), accepted)
        self.assert_response_fixture(active, "quest-promised-item-active.json")
        goals_response = self.client.get("/api/challenges/")
        legacy = next(row for row in goals_response.json()["results"] if row["origin"] == "legacy")
        self.assertEqual([(row["item"], row["quantity"]) for row in legacy["rewards"]["items"]], [(egg.pk, 2)])
        self.assert_response_fixture(goals_response, "challenges-legacy-promised-item.json")

        self.assertEqual(self.log_run("0.75").status_code, 201)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 2)
        history = self.assert_response_fixture(self.client.get("/api/quests/history/"), "quest-promised-item-history.json")
        self.assertEqual(history[0]["status"], "completed")
        self.assertEqual(history[0]["definition"]["reward_items"], promised)
        self.assertEqual(self.log_run("1.25").status_code, 201)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 2)
        self.assertEqual(list(CoinLedger.objects.filter(
            user=self.child, description=f"Quest complete: {definition.name}",
        ).values_list("amount", flat=True)), [7])
        self.assertEqual(self.client.get("/api/quests/history/").json(), history)

    def test_catalog_receipt_reports_owned_egg_conversion_without_claiming_delivery(self):
        from apps.pets.models import UserMount
        species, potion, egg, policy = self.add_synthetic_egg_reward()
        UserMount.objects.create(user=self.child, species=species, potion=potion)
        self.authenticate(self.child)
        with self.settings(RPG_ASSET_SUPPORT_POLICY=policy):
            preview = self.client.get("/api/challenges/").json()["results"][0]
            self.assertEqual(preview["rewards"]["items"][0]["item_name"], egg.name)
            self.assertEqual(self.log_run("0.75").status_code, 201)
            self.assertEqual(self.log_run("1.25").status_code, 201)
            response = self.client.get("/api/challenges/")
            receipt = response.json()["results"][0]["reward_receipt"]
            self.assertEqual(receipt["coins_awarded"], 30)
            self.assertEqual(receipt["items"], [{"item_name": egg.name, "item_catalog_icon": None, "quantity": 1, "salvaged_to_coins": 25}])
            completed = self.assert_response_fixture(response, "challenges-items-converted.json")
            self.assertFalse(UserInventory.objects.filter(user=self.child, item=egg).exists())
            paid = self.state()
            self.log_run("1.25")
            self.assertEqual(self.client.get("/api/challenges/").json(), completed)
            self.assertEqual(self.state(), paid)


class RealChallengeMigrationTests(unittest.TestCase):
    """Exercise actual migration files outside the suite's syncdb shortcut."""

    def test_additive_upgrade_preserves_legacy_promises_and_awards_nothing(self):
        code = r'''
            from datetime import datetime, timedelta, timezone
            from unittest.mock import patch
            import django
            django.setup()
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            assert not getattr(settings, "MIGRATION_MODULES", {})
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] not in {"quests", "movement"}]
            targets += [("quests", "0004_dailychallenge"), ("movement", "0003_dailycountermodel_rebase")]
            executor.migrate(targets)
            old_apps = executor.loader.project_state(targets).apps
            models = {name: old_apps.get_model(app, name) for app, name in [
                ("families", "Family"), ("accounts", "User"),
                ("quests", "QuestDefinition"), ("quests", "Quest"),
                ("quests", "QuestParticipant"), ("quests", "DailyChallenge"),
                ("rewards", "CoinLedger"), ("rpg", "ItemDefinition"), ("rpg", "UserInventory"),
                ("movement", "MovementType"), ("movement", "MovementSession"), ("movement", "MovementDailyCounter"),
                ("achievements", "SkillCategory"), ("achievements", "Skill"), ("achievements", "SkillProgress"),
            ]}
            stamp = datetime(2026, 10, 14, 19, tzinfo=timezone.utc)
            with patch("django.utils.timezone.now", return_value=stamp):
                family = models["Family"].objects.create(id=41, name="Preserved household", slug="preserved-household")
                child = models["User"].objects.create(id=7, username="preserved-child", role="child", family=family)
                sibling = models["User"].objects.create(id=8, username="preserved-sibling", role="child", family=family)
                definition = models["QuestDefinition"].objects.create(
                    id=51, name="Preserved promise", description="Original challenge", quest_type="collection",
                    target_value=100, duration_days=7, coin_reward=17, xp_reward=23, is_system=True,
                )
                for pk, status, progress in [(91, "active", 3), (92, "completed", 100), (93, "active", 23)]:
                    quest = models["Quest"].objects.create(
                        id=pk, definition=definition, status=status, current_progress=progress, rage_shield=15,
                        start_date=stamp-timedelta(days=2), end_date=stamp+timedelta(days=5),
                    )
                    models["QuestParticipant"].objects.create(quest=quest, user=child, contribution=progress)
                    if pk == 93:
                        models["QuestParticipant"].objects.create(quest=quest, user=sibling, contribution=7)
                models["DailyChallenge"].objects.create(
                    id=71, user=child, date=stamp.date(), challenge_type="chores", target_value=2,
                    current_progress=2, completed_at=stamp, coin_reward=0, xp_reward=0,
                )
                models["DailyChallenge"].objects.create(
                    id=72, user=sibling, date=stamp.date(), challenge_type="chores", target_value=2,
                    current_progress=2, completed_at=stamp, coin_reward=10, xp_reward=20,
                )
                models["CoinLedger"].objects.create(user=child, amount=42, reason="adjustment", description="Original ledger")
                item = models["ItemDefinition"].objects.create(id=61, name="Saved frame", slug="preserved-frame", item_type="cosmetic_frame")
                models["UserInventory"].objects.create(user=child, item=item, quantity=2)
                movement_type = models["MovementType"].objects.create(id=31, name="Preserved Running", slug="preserved-running")
                models["MovementSession"].objects.create(
                    id=100, user=child, movement_type=movement_type, duration_minutes=30,
                    occurred_on=stamp.date(), xp_awarded=15, notes="Saved session without distance",
                )
                models["MovementDailyCounter"].objects.create(user=child, occurred_on=stamp.date(), count=3)
                category = models["SkillCategory"].objects.create(id=21, name="Preserved skills")
                skill = models["Skill"].objects.create(id=22, name="Preserved running", category=category)
                models["SkillProgress"].objects.create(user=child, skill=skill, xp_points=37)
            before = {name: list(model.objects.order_by("pk").values()) for name, model in models.items()}
            executor = MigrationExecutor(connection)
            latest = executor.loader.graph.leaf_nodes()
            executor.migrate(latest)
            new_apps = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                model = models[name]
                upgraded = new_apps.get_model(model._meta.app_label, name)
                columns = list(rows[0]) if rows else [field.attname for field in model._meta.concrete_fields]
                assert list(upgraded.objects.order_by("pk").values(*columns)) == rows, name
            for name in ["ChallengeGoal", "ChallengeOccurrence", "ChallengeActivity", "ChallengeContribution", "DailyBonus"]:
                assert new_apps.get_model("quests", name).objects.count() == 0, name
            saved_movement = new_apps.get_model("movement", "MovementSession").objects.get(pk=100)
            assert saved_movement.distance_meters is None and saved_movement.client_request_id is None
            # The first automatic list retains saved progress and creates only
            # presentation/enrollment state. It cannot pay historical work.
            from apps.accounts.models import User
            from apps.quests.goals import list_goals
            from apps.quests.models import Quest, ChallengePin
            with patch("django.utils.timezone.now", return_value=stamp):
                result = list_goals(User.objects.get(pk=7))
            assert any(goal["id"] == "legacy:91" and goal["progress"] == "3" for goal in result["results"])
            assert models["CoinLedger"].objects.count() == 1
            assert models["DailyChallenge"].objects.get(pk=71).coin_reward == 0
            assert models["DailyChallenge"].objects.get(pk=72).coin_reward == 10
            assert Quest.objects.get(pk=93).participants.count() == 2
            assert ChallengePin.objects.get(user_id=7).legacy_quest_id in {91, 93}
        '''
        self.assert_real_migration_process(code)

    def test_catalog_retirement_upgrade_preserves_saved_windows_and_parent_origin(self):
        code = r'''
            from datetime import datetime, timedelta, timezone
            import django
            django.setup()
            from django.conf import settings
            from django.db import connection
            from django.db.migrations.executor import MigrationExecutor
            assert not getattr(settings, "MIGRATION_MODULES", {})
            assert connection.vendor == "sqlite" and connection.settings_dict["NAME"] == ":memory:"
            executor = MigrationExecutor(connection)
            targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != "quests"]
            targets += [("quests", "0006_parent_goal_request_identity")]
            executor.migrate(targets)
            old_apps = executor.loader.project_state(targets).apps
            models = {name: old_apps.get_model(app, name) for app, name in [
                ("families", "Family"), ("accounts", "User"), ("quests", "QuestDefinition"),
                ("quests", "ChallengeGoal"), ("quests", "ChallengeOccurrence"),
                ("quests", "ChallengeActivity"), ("quests", "ChallengeContribution"),
                ("quests", "ChallengePin"), ("quests", "DailyBonus"),
                ("rewards", "CoinLedger"), ("rpg", "ItemDefinition"), ("rpg", "UserInventory"),
                ("achievements", "SkillCategory"), ("achievements", "Skill"), ("achievements", "SkillProgress"),
            ]}
            stamp = datetime(2026, 10, 14, 19, tzinfo=timezone.utc)
            family = models["Family"].objects.create(id=41, name="Upgrade household", slug="upgrade-household")
            parent = models["User"].objects.create(id=6, username="upgrade-parent", role="parent", family=family)
            child = models["User"].objects.create(id=7, username="upgrade-child", role="child", family=family)
            definition = models["QuestDefinition"].objects.create(
                id=51, name="Original catalog identity", quest_type="collection", is_system=True,
                target_value=2, duration_days=7, coin_reward=17, xp_reward=23, is_repeatable=True,
            )
            category = models["SkillCategory"].objects.create(id=21, name="Upgrade skills")
            skill = models["Skill"].objects.create(id=22, name="Upgrade skill", category=category)
            models["SkillProgress"].objects.create(user=child, skill=skill, xp_points=37)
            item = models["ItemDefinition"].objects.create(id=61, name="Saved frame", slug="upgrade-frame", item_type="cosmetic_frame")
            models["UserInventory"].objects.create(user=child, item=item, quantity=2)
            models["CoinLedger"].objects.create(user=child, amount=42, reason="adjustment", description="Existing reward ledger")
            fields = dict(
                user=child, family=family, name="Frozen visible challenge", metric="count", target=2,
                unit="actions", trigger_filter={"allowed_triggers": ["chore_complete"]},
                timezone_name="America/Phoenix", starts_at=stamp-timedelta(days=2),
                ends_at=stamp+timedelta(days=5), coin_reward=17, xp_reward=23,
                skill_tags=[{"skill_id": skill.pk, "xp_weight": 1}],
                reward_items=[{"item_id": item.pk, "quantity": 2}],
            )
            catalog_goal = models["ChallengeGoal"].objects.create(
                id=31, catalog_definition=definition, repeat_days=7, **fields,
            )
            # An identical display name and spoofed snapshot metadata cannot
            # turn a parent-authored goal into catalog history during upgrade.
            parent_goal = models["ChallengeGoal"].objects.create(
                id=32, created_by=parent, repeat_weekly=True,
                request_id="33333333-3333-4333-8333-333333333333", request_fingerprint="frozen-parent-request", **fields,
            )
            snapshot = {
                "name": fields["name"], "description": "Saved reward promise", "metric": "count",
                "target": "2", "unit": "actions", "filter": fields["trigger_filter"],
                "coins": 17, "xp": 23, "skill_tags": fields["skill_tags"], "items": fields["reward_items"],
            }
            paid = models["ChallengeOccurrence"].objects.create(
                id=44, goal=catalog_goal, starts_at=stamp-timedelta(days=9), ends_at=stamp-timedelta(days=2),
                snapshot=snapshot, progress=2, status="completed", completed_at=stamp-timedelta(days=3),
                awarded_at=stamp-timedelta(days=3),
                reward_receipt={"id": "goal:44", "status": "awarded", "coins_awarded": 17, "xp_awarded": 23},
            )
            active = models["ChallengeOccurrence"].objects.create(
                id=45, goal=catalog_goal, starts_at=fields["starts_at"], ends_at=fields["ends_at"],
                snapshot=snapshot, progress=1, status="active",
            )
            models["ChallengeOccurrence"].objects.create(
                id=46, goal=parent_goal, starts_at=fields["starts_at"], ends_at=fields["ends_at"],
                snapshot={**snapshot, "catalog_name": definition.name, "catalog_type": "boss"}, progress=1,
            )
            activity = models["ChallengeActivity"].objects.create(
                user=child, source_type="homework_created", source_id="synthetic-source-9",
                trigger_type="homework_created", occurred_at=stamp, occurred_on=stamp.date(),
                context={"assignment_id": 9, "catalog_eligible": True}, processed_at=stamp,
            )
            models["ChallengeContribution"].objects.create(occurrence=active, activity=activity, amount=1)
            models["ChallengeContribution"].objects.create(occurrence=paid, activity=activity, amount=2)
            models["ChallengePin"].objects.create(user=child, occurrence=active)
            models["DailyBonus"].objects.create(
                user=child, date=stamp.date(), completed_at=stamp, awarded_at=stamp,
                coins_awarded=10, xp_awarded=20,
            )
            before = {name: list(model.objects.order_by("pk").values()) for name, model in models.items()}
            executor = MigrationExecutor(connection)
            latest = executor.loader.graph.leaf_nodes()
            executor.migrate(latest)
            assert ("quests", "0007_catalog_goal_retirement") in MigrationExecutor(connection).loader.applied_migrations
            new_apps = executor.loader.project_state(latest).apps
            for name, rows in before.items():
                upgraded = new_apps.get_model(models[name]._meta.app_label, name)
                expected = rows
                if name == "ChallengeOccurrence":
                    expected = [
                        {**row, "snapshot": {**row["snapshot"], "catalog_name": definition.name,
                                              "catalog_type": definition.quest_type}}
                        if row["goal_id"] == catalog_goal.pk else row
                        for row in rows
                    ]
                assert list(upgraded.objects.order_by("pk").values(*rows[0].keys())) == expected, name
            Goal = new_apps.get_model("quests", "ChallengeGoal")
            assert Goal.objects.get(pk=31).is_catalog is True
            assert Goal.objects.get(pk=32).is_catalog is False
            new_apps.get_model("quests", "QuestDefinition").objects.get(pk=51).delete()
            detached = Goal.objects.get(pk=31)
            assert detached.catalog_definition_id is None and detached.is_catalog is True
            assert Goal.objects.get(pk=32).is_catalog is False
            Occurrence = new_apps.get_model("quests", "ChallengeOccurrence")
            assert Occurrence.objects.count() == 3
            assert Occurrence.objects.get(pk=44).reward_receipt == paid.reward_receipt
            assert Occurrence.objects.get(pk=45).snapshot["coins"] == 17
            assert Occurrence.objects.get(pk=45).progress == 1
            assert new_apps.get_model("rewards", "CoinLedger").objects.count() == 1
            assert new_apps.get_model("achievements", "SkillProgress").objects.get(user_id=7).xp_points == 37
        '''
        self.assert_real_migration_process(code)

    def assert_real_migration_process(self, code):
        bootstrap = ("PATH", "HOME", "LD_LIBRARY_PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
        env = {key: os.environ[key] for key in bootstrap if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test", "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "challenge-migration-test-only", "DEBUG": "True",
        })
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
