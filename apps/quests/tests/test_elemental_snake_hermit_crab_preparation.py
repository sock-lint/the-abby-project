"""Unregistered elemental preparation never activates unaccepted artwork."""
from copy import deepcopy
from io import StringIO
import json
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill
from apps.creations.services import CreationService
from apps.pets.models import PetSpecies, PotionType, UserMount
from apps.quests.activity import record_activity
from apps.quests.availability import definition_is_available
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.reading.models import ReadingDailyReward
from apps.rpg.catalog_icons import challenge_catalog_icon
from apps.rpg.catalog_support import POLICY_PATH, available_pet_pairs, random_item_is_available
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


PACK = "content/rpg/prepared/elemental-snake-hermit-crab"
SPECIES = {"meshtint-snake", "meshtint-hermit-crab"}
PATHS = {
    "Ember Coil": ("meshtint-snake", "fire", "review-snake-fire-acquisition-icon"),
    "Frost Coil": ("meshtint-snake", "ice", "review-snake-ice-acquisition-icon"),
    "Ember Shore": ("meshtint-hermit-crab", "fire", "review-hermit-crab-fire-acquisition-icon"),
    "Frost Shore": ("meshtint-hermit-crab", "ice", "review-hermit-crab-ice-acquisition-icon"),
}
TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete",
    "creation_logged", "reading_logged",
}


def future_policy(*pairs):
    """Synthetic exact art support, never a production manifest or release pin."""
    policy = deepcopy(json.loads(POLICY_PATH.read_text()))
    for species, potion in pairs:
        row = next(row for row in policy["pets"] if row["species_slug"] == species)
        if potion not in row["potion_slugs"]:
            row["potion_slugs"].append(potion)
    return policy


FUTURE_POLICY = future_policy(*[(species, potion) for species in SPECIES for potion in ("fire", "ice")])


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SnakeHermitCrabPreparationBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())

    def test_default_load_keeps_existing_pairs_offers_and_natural_egg_identities(self):
        self.assertEqual(len(available_pet_pairs()), 27)
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())
        self.assertTrue((settings.BASE_DIR / PACK).is_dir())
        before = list(ItemDefinition.objects.order_by("pk").values("pk", "slug", "name", "item_type", "pet_species_id", "potion_type_id", "rarity", "metadata"))
        for species_slug in SPECIES:
            species = PetSpecies.objects.get(slug=species_slug)
            egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
            self.assertEqual((species.sprite_key, species.rarity), (species_slug, "uncommon"))
            self.assertEqual(list(species.available_potions.values_list("slug", flat=True)), ["base"])
            self.assertEqual((egg.pet_species_id, egg.metadata), (species.pk, {"species": species_slug}))
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values("pk", "slug", "name", "item_type", "pet_species_id", "potion_type_id", "rarity", "metadata")), before)
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())
        child = make_family("Preparation boundary", children=[{"username": "preparation-child"}]).children[0]
        client = APIClient()
        client.force_authenticate(child)
        for endpoint in ("/api/quests/available/", "/api/quests/catalog/"):
            response = client.get(endpoint)
            if response.status_code == 200:
                self.assertFalse(set(PATHS) & {row["name"] for row in response.data})
        codex = client.get("/api/pets/codex/").data
        for species in codex["species"]:
            if species["slug"] in SPECIES:
                self.assertEqual([row["slug"] for row in species["available_potions"]], ["base"])
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_explicit_prepared_pack_is_rejected_atomically_under_production_policy(self):
        species_before = list(PetSpecies.objects.order_by("pk").values())
        compatibility_before = list(PetSpecies.available_potions.through.objects.order_by("pk").values())
        items_before = list(ItemDefinition.objects.order_by("pk").values())
        quests_before = list(QuestDefinition.objects.order_by("pk").values())
        with self.assertRaisesRegex(CommandError, "compatibility|artwork|Fire and Ice"):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertEqual(list(PetSpecies.objects.order_by("pk").values()), species_before)
        self.assertEqual(list(PetSpecies.available_potions.through.objects.order_by("pk").values()), compatibility_before)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), items_before)
        self.assertEqual(list(QuestDefinition.objects.order_by("pk").values()), quests_before)
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())

    @override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY)
    def test_scoped_full_policy_allows_explicit_pack_without_registering_it(self):
        call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertEqual(len(available_pet_pairs()), 31)
        self.assertEqual(set(QuestDefinition.objects.filter(name__in=PATHS).values_list("name", flat=True)), set(PATHS))

    @override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY)
    def test_prepared_authoring_rejects_partial_potions_forged_sprite_and_other_family(self):
        source = yaml.safe_load((settings.BASE_DIR / PACK / "pet_species.yaml").read_text())["species"][0]
        candidates = [
            {**source, "available_potions": ["base", "fire"]},
            {**source, "sprite_key": "meshtint-hermit-crab"},
            {**source, "slug": "meshtint-blossom", "name": "Bud", "sprite_key": "meshtint-blossom"},
            {**source, "slug": "meshtint-forged", "sprite_key": "meshtint-forged"},
        ]
        before = list(PetSpecies.available_potions.through.objects.order_by("pk").values())
        for candidate in candidates:
            with self.subTest(candidate=candidate), TemporaryDirectory() as directory:
                (Path(directory) / "pet_species.yaml").write_text(yaml.safe_dump({"species": [candidate]}))
                with self.assertRaisesRegex(CommandError, "compatibility|collision|Unknown prepared"):
                    call_command("loadrpgcontent", pack=directory, stdout=StringIO())
                self.assertEqual(list(PetSpecies.available_potions.through.objects.order_by("pk").values()), before)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=future_policy(("meshtint-snake", "fire"))):
            with self.assertRaisesRegex(CommandError, "compatibility"):
                call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())

    def test_descriptor_handles_bind_only_system_collection_definitions(self):
        descriptor = json.loads(POLICY_PATH.with_name("elemental-snake-hermit-crab.json").read_text())
        self.assertFalse(descriptor["preparation"]["acquisition_active"])
        self.assertFalse(descriptor["preparation"]["artwork_accepted"])
        self.assertEqual(descriptor["preparation"]["state"], "private_evaluation")
        self.assertEqual(descriptor["release"]["manifest_sha256"],
                         "2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3")
        for name, (_species, _potion, icon) in PATHS.items():
            with self.subTest(name=name):
                definition = QuestDefinition(name=name, quest_type="collection", is_system=True)
                self.assertEqual(challenge_catalog_icon(definition), icon)
                definition.is_system = False
                self.assertIsNone(challenge_catalog_icon(definition))
                definition.is_system, definition.quest_type = True, "boss"
                self.assertIsNone(challenge_catalog_icon(definition))

    def test_previously_processed_facts_are_not_replayed_into_future_prepared_goals(self):
        child = make_family("Before elemental preparation", children=[{"username": "before-preparation"}]).children[0]
        ingest_activity(child, "chore_complete", "before-prepared-pack", "chore_complete")
        with override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
            rows = [row for row in list_goals(child)["results"] if row["name"] in PATHS]
        self.assertEqual({row["name"] for row in rows}, set(PATHS))
        self.assertEqual({row["progress"] for row in rows}, {"0"})


@override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PreparedSnakeHermitCrabPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.original_eggs = dict(ItemDefinition.objects.filter(
            slug__in=[f"{species}-egg" for species in SPECIES]).values_list("slug", "pk"))
        call_command("loadrpgcontent", pack=PACK, stdout=StringIO())

    def setUp(self):
        household = make_family("Prepared Snake/Crab", parents=[{"username": "prepared-parent"}],
            children=[{"username": "prepared-child"}, {"username": "prepared-sibling"}])
        self.parent, (self.child, self.sibling) = household.parents[0], household.children
        foreign = make_family("Foreign preparation", children=[{"username": "prepared-foreign"}])
        self.foreign = foreign.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        QuestDefinition.objects.exclude(name__in=PATHS).update(is_system=False)
        for target in ("apps.rpg.services.DropService.process_drops", "apps.rpg.services.DropService.award_accomplishment"):
            mocked = patch(target, return_value=[])
            mocked.start()
            self.addCleanup(mocked.stop)

    def definitions(self):
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=PATHS)}
        self.assertEqual(set(definitions), set(PATHS))
        return definitions

    def test_prepared_authored_rules_preserve_typed_existing_ingredients_and_rarity(self):
        self.assertEqual(len(available_pet_pairs()), 31)
        definitions = self.definitions()
        for name, (species_slug, potion, image) in PATHS.items():
            with self.subTest(name=name):
                definition = definitions[name]
                species = PetSpecies.objects.get(slug=species_slug)
                egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
                ingredient = ItemDefinition.objects.get(slug=f"{potion}-potion")
                self.assertEqual(egg.pk, self.original_eggs[egg.slug])
                self.assertEqual((species.sprite_key, species.rarity, egg.rarity), (species_slug, "uncommon", "uncommon"))
                self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
                self.assertEqual((egg.item_type, egg.pet_species_id, egg.metadata), ("egg", species.pk, {"species": species_slug}))
                self.assertEqual((ingredient.item_type, ingredient.potion_type.slug), ("potion", potion))
                self.assertFalse(random_item_is_available(ingredient))
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days), ("collection", 10, 180))
                self.assertEqual((definition.coin_reward, definition.xp_reward), (0, 0))
                self.assertTrue(definition.is_system)
                self.assertFalse(definition.is_repeatable)
                self.assertFalse(definition.is_cooperative)
                self.assertIsNone(definition.created_by_id)
                self.assertIsNone(definition.required_badge_id)
                self.assertEqual(set(definition.trigger_filter["allowed_triggers"]), TRIGGERS)
                self.assertEqual({row.item_id: row.quantity for row in definition.reward_items.all()}, {egg.pk: 1, ingredient.pk: 1})
                self.assertEqual(challenge_catalog_icon(definition), image)
        self.assertEqual(set(PotionType.objects.values_list("slug", flat=True)), {"base", "fire", "ice"})
        self.assertFalse(ItemDefinition.objects.filter(item_type="egg", slug__in=[
            f"{species}-{potion}-egg" for species in SPECIES for potion in ("fire", "ice")]).exists())

    def test_ten_shared_facts_award_all_four_exact_bundles_once_without_other_children(self):
        self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, set(PATHS))
        for index in range(10):
            trigger = ("chore_complete", "homework_complete", "milestone_complete", "project_complete")[index % 4]
            ingest_activity(self.child, trigger, f"prepared-action-{index}", trigger)
            if index == 8:
                self.assertFalse(ChallengeOccurrence.objects.filter(status="completed").exists())
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual(len(occurrences), 4)
        for occurrence in occurrences:
            species, potion, _image = PATHS[occurrence.snapshot["name"]]
            self.assertEqual(occurrence.status, "completed")
            receipt = occurrence.reward_receipt
            self.assertEqual((receipt["coins"], receipt["xp"]), (0, 0))
            self.assertEqual({row["item_id"]: row["quantity"] for row in receipt["items"]}, {
                ItemDefinition.objects.get(slug=f"{species}-egg").pk: 1,
                ItemDefinition.objects.get(slug=f"{potion}-potion").pk: 1,
            })
        receipts = {row.pk: row.reward_receipt for row in occurrences}
        inventory = dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity"))
        self.assertEqual(inventory, {"meshtint-snake-egg": 2, "meshtint-hermit-crab-egg": 2, "fire-potion": 2, "ice-potion": 2})
        ingest_activity(self.child, "chore_complete", "prepared-action-0", "chore_complete")
        ingest_activity(self.child, "chore_complete", "prepared-completed-extra", "chore_complete")
        list_goals(self.child)
        self.assertEqual({row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, receipts)
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), inventory)
        self.assertFalse(UserInventory.objects.filter(user__in=[self.sibling, self.foreign]).exists())

    def test_future_exact_pair_policy_controls_whole_offer_reads_and_hints(self):
        from apps.mcp_server.catalog import catalog_row
        definitions = self.definitions()
        for name, (species, potion, _icon) in PATHS.items():
            with self.subTest(name=name), override_settings(RPG_ASSET_SUPPORT_POLICY=future_policy((species, potion))):
                self.assertEqual({row.name for row in definitions.values() if definition_is_available(row)}, {name})
        with override_settings(RPG_ASSET_SUPPORT_POLICY=None):
            self.assertEqual(list_goals(self.child)["results"], [])
            self.assertEqual(self.client.get("/api/quests/available/").data, [])
            for definition in definitions.values():
                self.assertFalse(catalog_row("quests", definition)["available_for_new_user"])
            for slug in ("meshtint-snake-egg", "meshtint-hermit-crab-egg", "fire-potion", "ice-potion"):
                UserInventory.objects.create(user=self.child, item=ItemDefinition.objects.get(slug=slug))
            for row in self.client.get("/api/inventory/").data:
                self.assertFalse(any(source["name"] in PATHS for source in row["item"]["acquisition_sources"]))
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_frozen_promises_survive_definition_and_policy_changes_without_salvaging_base_ownership(self):
        definitions = self.definitions()
        for species in SPECIES:
            UserMount.objects.create(user=self.child, species=PetSpecies.objects.get(slug=species), potion=PotionType.objects.get(slug="base"))
        list_goals(self.child)
        accepted = {row.pk: deepcopy(row.snapshot) for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}
        QuestDefinition.objects.filter(pk__in=[row.pk for row in definitions.values()]).update(target_value=99, duration_days=3, coin_reward=7, xp_reward=11)
        QuestRewardItem.objects.filter(quest_definition__in=definitions.values()).delete()
        with override_settings(RPG_ASSET_SUPPORT_POLICY=None):
            for index in range(10):
                ingest_activity(self.child, "chore_complete", f"saved-preparation-{index}", "chore_complete")
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual({row.pk: row.snapshot for row in occurrences}, accepted)
        for occurrence in occurrences:
            self.assertEqual(occurrence.status, "completed")
            self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
            self.assertTrue(all("salvaged_to_coins" not in row for row in occurrence.reward_receipt["items"]))
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), {
            "meshtint-snake-egg": 2, "meshtint-hermit-crab-egg": 2, "fire-potion": 2, "ice-potion": 2})
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 2)

    def test_child_selector_does_not_read_sibling_or_foreign_challenge_progress(self):
        for user, count in ((self.child, 2), (self.sibling, 1), (self.foreign, 3)):
            list_goals(user)
            for index in range(count):
                ingest_activity(user, "chore_complete", f"scoped-{user.pk}-{index}", "chore_complete")
        expected = ChallengeOccurrence.objects.get(goal__user=self.child, goal__catalog_definition__name="Ember Coil")
        for selector in (self.sibling.pk, self.foreign.pk):
            response = self.client.get("/api/pets/codex/", {"user_id": selector})
            family = next(row for row in response.data["species"] if row["slug"] == "meshtint-snake")
            variant = next(row for row in family["available_potions"] if row["slug"] == "fire")
            self.assertEqual([row["attempt"]["id"] for row in variant["acquisition_challenges"]], [f"goal:{expected.pk}"])
            self.assertEqual(variant["acquisition_challenges"][0]["attempt"]["progress"], "2")

    def test_daily_reading_receipt_and_first_two_creations_count_but_micro_actions_do_not(self):
        from django.utils import timezone
        list_goals(self.child)
        for trigger in ("clock_out", "habit_log", "journal_entry", "movement_session", "homework_created"):
            ingest_activity(self.child, trigger, f"unrelated-{trigger}", trigger)
        record_activity(self.child, "reading_logged", {"minutes": 600, "session_id": 999})
        receipt = ReadingDailyReward.objects.create(user=self.child, day=timezone.localdate(), minutes_credited=10, awarded_at=timezone.now())
        for _ in range(2):
            record_activity(self.child, "reading_logged", {"reading_reward_id": receipt.pk})
        skill = Skill.objects.filter(category__name="Art & Crafts").first()
        with patch("apps.rpg.services.safe_game_loop_call"):
            creations = [CreationService.log_creation(self.child, image="synthetic-preparation.jpg", primary_skill_id=skill.pk) for _ in range(3)]
        record_activity(self.child, "creation_logged", {"creation_id": creations[-1].pk, "catalog_eligible": True})
        self.assertEqual({row.progress for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, {3})
