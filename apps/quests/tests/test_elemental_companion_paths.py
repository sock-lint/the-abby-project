"""Elemental discoveries promise usable pairs, and never an egg-only fallback."""
from copy import deepcopy
from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.quests.activity import record_activity
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.achievements.models import Skill
from apps.creations.services import CreationService
from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.reading.models import ReadingDailyReward
from apps.rpg.catalog_support import POLICY_PATH
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


PATHS = {
    "Ember Nest": ("chick", "fire", 5),
    "Frost Nest": ("chick", "ice", 5),
    "Ember Trail": ("meshtint-wolf", "fire", 20),
    "Frost Trail": ("meshtint-wolf", "ice", 20),
}
TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete",
    "creation_logged", "reading_logged",
}


def art_policy(*pairs):
    policy = deepcopy(json.loads(POLICY_PATH.read_text()))
    # Explicit retired/partial policies keep these availability scenarios
    # independent from the four pairs enabled in the shipped registry.
    policy["potion_slugs"] = ["base"]
    for row in policy["pets"]:
        row["potion_slugs"] = ["base"]
    for species, potion in pairs:
        if potion not in policy["potion_slugs"]:
            policy["potion_slugs"].append(potion)
        next(row for row in policy["pets"] if row["species_slug"] == species)["potion_slugs"].append(potion)
    return policy


@override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(),
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())

    def setUp(self):
        family = make_family("Elemental discovery", parents=[{"username": "element-parent"}],
                             children=[{"username": "element-child"}, {"username": "element-sibling"}])
        self.child, self.sibling = family.children
        self.parent = family.parents[0]
        self.definition = QuestDefinition.objects.create(
            name="Synthetic elemental discovery", description="A usable Fire Chick pair",
            quest_type="collection", target_value=1, duration_days=180, is_system=True,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        for slug in ("chick-egg", "fire-potion"):
            QuestRewardItem.objects.create(quest_definition=self.definition,
                                          item=ItemDefinition.objects.get(slug=slug))
        QuestDefinition.objects.exclude(pk=self.definition.pk).update(is_system=False)
        self.client = APIClient()

    def test_unprepared_bundle_is_hidden_and_cannot_start_or_grant_just_egg(self):
        self.assertEqual(list_goals(self.child)["results"], [])
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/quests/available/").data, [])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/quests/catalog/").data, [])
        for start in (lambda: QuestService.start_quest(self.child, self.definition.pk),
                      lambda: QuestService.start_co_op_quest(self.definition.pk, [self.child, self.sibling])):
            with self.assertRaisesRegex(ValueError, "artwork|available|not found"):
                start()
        ingest_activity(self.child, "chore_complete", "future-pair", "chore_complete")
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_milestone_metadata_requires_both_whole_pair_art_and_a_reachable_prerequisite(self):
        from apps.mcp_server.catalog import catalog_row
        from apps.quests.controls import control_context, retry_state
        from apps.quests.milestone_eligibility import prerequisite_unavailable
        from apps.rewards.models import CoinLedger

        prior = QuestDefinition.objects.create(
            name="Synthetic elemental reading prerequisite", description="A separate accepted reading window",
            quest_type="collection", target_value=3, duration_days=14, is_system=True,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        self.definition.prerequisite_quest = prior
        self.definition.trigger_filter = {"allowed_triggers": ["reading_logged"]}
        self.definition.save(update_fields=["prerequisite_quest", "trigger_filter", "updated_at"])
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.definition.pk, [row["id"] for row in response.data["locked_catalog"]])
        self.assertNotIn(self.definition.pk, [row["id"] for row in self.client.get("/api/quests/available/").data])
        self.client.force_authenticate(self.parent)
        self.assertNotIn(self.definition.pk, [row["id"] for row in self.client.get("/api/quests/catalog/").data])
        self.assertFalse(catalog_row("quests", self.definition)["available_for_new_user"])
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            self.client.force_authenticate(self.child)
            response = self.client.get("/api/challenges/")
            locked = next(row for row in response.data["locked_catalog"] if row["id"] == self.definition.pk)
            self.assertEqual(locked["prerequisite_quest"], prior.pk)
            self.assertFalse(locked["milestone_eligibility"]["unlocked"])
            self.assertEqual(len(locked["reward_items"]), 2)
            self.assertTrue(all(row["item_catalog_available"] for row in locked["reward_items"]))
            self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.definition).exists())
            self.assertIn(self.definition.pk, [row["id"] for row in self.client.get("/api/quests/available/").data])
            self.client.force_authenticate(self.parent)
            self.assertIn(self.definition.pk, [row["id"] for row in self.client.get("/api/quests/catalog/").data])
            projection = catalog_row("quests", self.definition)
            self.assertTrue(projection["available_for_new_user"])
            self.assertEqual(projection["prerequisite_quest"], prior.pk)
            self.client.force_authenticate(self.child)
            # Native explicit retries keep this accepted starter reachable;
            # reading metadata neither starts the successor nor retries it.
            accepted_count = ChallengeOccurrence.objects.count()
            with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=31)):
                response = self.client.get("/api/challenges/")
                self.assertEqual(response.status_code, 200)
                original = ChallengeOccurrence.objects.get(goal__user=self.child, goal__catalog_definition=prior)
                self.assertTrue(retry_state(original, control_context(self.child))["allowed"])
                saved = next(row for row in response.data["results"] if row["id"] == f"goal:{original.pk}")
                self.assertTrue(saved["retry"]["allowed"])
                self.assertFalse(prerequisite_unavailable(self.child, prior.pk))
                locked = next(row for row in response.data["locked_catalog"] if row["id"] == self.definition.pk)
                self.assertFalse(locked["milestone_eligibility"]["unlocked"])
                self.assertEqual(ChallengeOccurrence.objects.count(), accepted_count)
                # Approved artwork cannot revive an ambiguous prerequisite
                # identity, for which the current offer has no retry path.
                QuestDefinition.objects.create(name=prior.name, quest_type="collection", target_value=3,
                    duration_days=14, is_system=True, trigger_filter=prior.trigger_filter)
                response = self.client.get("/api/challenges/")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(retry_state(original, control_context(self.child))["allowed"])
                self.assertTrue(prerequisite_unavailable(self.child, prior.pk))
                self.assertNotIn(self.definition.pk, [row["id"] for row in response.data["locked_catalog"]])
                self.assertEqual(ChallengeOccurrence.objects.count(), accepted_count)
            self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.definition).exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    def test_globally_available_fire_does_not_enable_an_unprepared_species_pair(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("meshtint-wolf", "fire"))):
            self.assertEqual(list_goals(self.child)["results"], [])

    def test_authored_catalog_audit_marks_unprepared_pair_unavailable(self):
        from apps.mcp_server.catalog import catalog_row
        self.assertFalse(catalog_row("quests", self.definition)["available_for_new_user"])
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            self.assertTrue(catalog_row("quests", self.definition)["available_for_new_user"])

    def test_unprepared_bundle_does_not_advertise_inventory_acquisition_hints(self):
        for slug in ("chick-egg", "fire-potion"):
            UserInventory.objects.create(user=self.child, item=ItemDefinition.objects.get(slug=slug))
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        for row in response.data:
            self.assertFalse(any(source["kind"] == "challenge"
                                 for source in row["item"]["acquisition_sources"]))

    def test_saved_bundle_keeps_its_inventory_hint_after_art_retirement(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            list_goals(self.child)
        item = ItemDefinition.objects.get(slug="fire-potion")
        UserInventory.objects.create(user=self.child, item=item)
        self.client.force_authenticate(self.child)
        # The shared ingredient remains supported by Wolf, while the accepted
        # Chick appearance no longer has new-offer artwork support.
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("meshtint-wolf", "fire"))):
            response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["item"]["acquisition_sources"], [
            {"kind": "challenge", "name": self.definition.name, "path": "/quests?tab=trials"},
        ])

    def test_quest_reroll_cannot_consume_item_when_only_unprepared_pair_exists(self):
        from apps.rpg.services import ConsumableService
        item = ItemDefinition.objects.get(slug="quest-reroll")
        UserInventory.objects.create(user=self.child, item=item, quantity=1)
        with self.assertRaisesRegex(ValueError, "No eligible quests"):
            ConsumableService.use(self.child, item.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 1)

    def test_processed_facts_from_before_the_pair_release_are_not_replayed(self):
        ingest_activity(self.child, "chore_complete", "before-art-release", "chore_complete")
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            rows = list_goals(self.child)["results"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["progress"], "0")

    @patch("apps.rpg.services.DropService.process_drops", return_value=[])
    def test_accepted_legacy_pair_retains_ingredients_after_retirement_and_base_ownership(self, _drops):
        UserMount.objects.create(user=self.child, species=PetSpecies.objects.get(slug="chick"),
                                 potion=PotionType.objects.get(slug="base"))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            quest = QuestService.start_quest(self.child, self.definition.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertTrue(result["completed"])
        self.assertEqual(result["rewards"]["coins"], 0)
        self.assertEqual({row["item_id"] for row in result["rewards"]["items"]},
                         {row["item_id"] for row in quest.reward_items_snapshot})
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="chick-egg").quantity, 1)
        # Completing the retained legacy campaign cannot enroll a second
        # automatic copy or start the same nonrepeatable bundle again.
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            self.assertEqual([row["id"] for row in list_goals(self.child)["results"]], [f"legacy:{quest.pk}"])
            self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
            with self.assertRaisesRegex(ValueError, "already completed"):
                QuestService.start_quest(self.child, self.definition.pk)


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalCompanionPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())

    def setUp(self):
        family = make_family("Elemental paths", children=[{"username": "element-trails-child"}])
        self.child = family.children[0]
        QuestDefinition.objects.exclude(name__in=PATHS).update(is_system=False)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def test_authored_paths_are_one_time_zero_currency_exact_ingredient_promises(self):
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=PATHS)}
        self.assertEqual(set(definitions), set(PATHS))
        for name, (species, potion, target) in PATHS.items():
            with self.subTest(name=name):
                definition = definitions[name]
                self.assertEqual((definition.target_value, definition.duration_days), (target, 180))
                self.assertEqual((definition.quest_type, definition.xp_reward, definition.coin_reward),
                                 ("collection", 0, 0))
                self.assertFalse(definition.is_repeatable)
                self.assertIsNone(definition.required_badge_id)
                self.assertEqual(set(definition.trigger_filter["allowed_triggers"]), TRIGGERS)
                self.assertEqual({row.item.slug: row.quantity for row in definition.reward_items.select_related("item")},
                                 {f"{species}-egg": 1, f"{potion}-potion": 1})
                self.assertEqual(set(PetSpecies.objects.get(slug=species).available_potions.values_list("slug", flat=True)),
                                 {"base", "fire", "ice"})

    def test_releasing_one_exact_pair_enables_only_its_goal(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()):
            self.assertEqual(list_goals(self.child)["results"], [])
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, {"Ember Nest"})

    def test_both_elements_count_same_facts_and_pay_exact_bundles_only_once(self):
        self.assertEqual(len(list_goals(self.child)["results"]), 4)
        for index in range(20):
            trigger = ["chore_complete", "homework_complete", "milestone_complete", "project_complete"][index % 4]
            ingest_activity(self.child, trigger, f"elemental-fact-{index}", trigger)
            if index == 4:
                completed = ChallengeOccurrence.objects.filter(goal__user=self.child, status="completed")
                self.assertEqual({row.snapshot["name"] for row in completed}, {"Ember Nest", "Frost Nest"})
        receipts = {row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}
        self.assertEqual(len(receipts), 4)
        for receipt in receipts.values():
            self.assertEqual((receipt["coins"], receipt["xp"]), (0, 0))
            self.assertEqual(len(receipt["items"]), 2)
        ingest_activity(self.child, "chore_complete", "elemental-fact-0", "chore_complete")
        ingest_activity(self.child, "chore_complete", "extra-elemental", "chore_complete")
        list_goals(self.child)
        self.assertEqual({row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, receipts)
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")),
                         {"chick-egg": 2, "meshtint-wolf-egg": 2, "fire-potion": 2, "ice-potion": 2})

    def test_reading_uses_earned_daily_receipt_once_and_excludes_micro_actions(self):
        self.assertEqual(len(list_goals(self.child)["results"]), 4)
        receipt = ReadingDailyReward.objects.create(user=self.child, day=timezone.localdate(),
                                                   minutes_credited=10, awarded_at=timezone.now())
        for _ in range(2):
            record_activity(self.child, "reading_logged", {"reading_reward_id": receipt.pk})
        for trigger in ("habit_log", "clock_out", "homework_created", "expedition_returned", "reading_logged"):
            # An invalid reading session/quantity cannot manufacture another receipt.
            record_activity(self.child, trigger, {"duration_minutes": 1000, "reading_session_id": 999})
        self.assertEqual({row.progress for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, {1})

    def test_creation_daily_cap_applies_to_every_elemental_path(self):
        self.assertEqual(len(list_goals(self.child)["results"]), 4)
        skill = Skill.objects.filter(category__name="Art & Crafts").first()
        with patch("apps.rpg.services.safe_game_loop_call"):
            creations = [CreationService.log_creation(self.child, image="synthetic-element.jpg", primary_skill_id=skill.pk)
                         for _ in range(3)]
        record_activity(self.child, "creation_logged", {"creation_id": creations[-1].pk, "catalog_eligible": True})
        self.assertEqual({row.progress for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, {2})

    def test_saved_pair_promise_still_pays_after_art_policy_retirement(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            list_goals(self.child)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy()):
            for index in range(5):
                ingest_activity(self.child, "chore_complete", f"retired-element-{index}", "chore_complete")
        receipt = ChallengeOccurrence.objects.get(goal__user=self.child).reward_receipt
        self.assertEqual({row["item_id"] for row in receipt["items"]},
                         set(ItemDefinition.objects.filter(slug__in=["chick-egg", "fire-potion"]).values_list("pk", flat=True)))

    def test_grown_base_does_not_salvage_the_egg_needed_for_an_elemental_pet(self):
        UserMount.objects.create(user=self.child, species=PetSpecies.objects.get(slug="chick"),
                                 potion=PotionType.objects.get(slug="base"))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            list_goals(self.child)
            for index in range(5):
                ingest_activity(self.child, "chore_complete", f"owned-base-{index}", "chore_complete")
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="chick-egg").quantity, 1)
        receipt = ChallengeOccurrence.objects.get(goal__user=self.child).reward_receipt
        self.assertEqual(receipt["coins"], 0)
        self.assertTrue(all("salvaged_to_coins" not in row for row in receipt["items"]))

    def test_exact_grown_element_salvages_duplicate_egg_but_preserves_potion(self):
        UserMount.objects.create(user=self.child, species=PetSpecies.objects.get(slug="chick"),
                                 potion=PotionType.objects.get(slug="fire"))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=art_policy(("chick", "fire"))):
            list_goals(self.child)
            for index in range(5):
                ingest_activity(self.child, "chore_complete", f"owned-fire-{index}", "chore_complete")
        self.assertFalse(UserInventory.objects.filter(user=self.child, item__slug="chick-egg").exists())
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="fire-potion").quantity, 1)
        receipt = ChallengeOccurrence.objects.get(goal__user=self.child).reward_receipt
        self.assertEqual(receipt["coins"], ItemDefinition.objects.get(slug="chick-egg").coin_value)
