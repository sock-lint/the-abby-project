"""Unregistered receiving content cannot activate unsupported acquisitions."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
import yaml

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


PACK = "content/rpg/prepared/elemental-ghost-potted-plant"
PRIVATE_RELEASE_FAMILY = "abby-elemental-ghost-potted-plant"
PRIVATE_MANIFEST_SHA256 = "6e1f2cb2f67503c63e3ab8a27135b6f7579f894e0d62b814bfa89df3a45ae9e9"
PRIVATE_REVIEW_INDEX_SHA256 = "12e87df4f4066b008767d3b281b1c8b12a8e965f227d39aaeec5735aaeffbb76"
SPECIES = {"meshtint-ghost", "meshtint-potted-plant"}
PATHS = {
    "Ember Wisp": ("meshtint-ghost", "fire", "review-ghost-fire-acquisition-icon"),
    "Frost Wisp": ("meshtint-ghost", "ice", "review-ghost-ice-acquisition-icon"),
    "Ember Sprout": ("meshtint-potted-plant", "fire", "review-potted-plant-fire-acquisition-icon"),
    "Frost Sprout": ("meshtint-potted-plant", "ice", "review-potted-plant-ice-acquisition-icon"),
}
TARGETS = {"meshtint-ghost": 20, "meshtint-potted-plant": 5}
RARITIES = {"meshtint-ghost": "rare", "meshtint-potted-plant": "common"}
TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete",
    "creation_logged", "reading_logged",
}


def future_policy(*pairs):
    """Synthetic positive support only; no new runtime release is implied."""
    policy = deepcopy(json.loads(POLICY_PATH.read_text()))
    for row in policy["pets"]:
        if row["species_slug"] in SPECIES:
            row["potion_slugs"] = ["base"]
    for species, potion in pairs:
        row = next(row for row in policy["pets"] if row["species_slug"] == species)
        if potion not in row["potion_slugs"]:
            row["potion_slugs"].append(potion)
    return policy


FUTURE_POLICY = future_policy(*[(species, potion) for species in sorted(SPECIES) for potion in ("fire", "ice")])


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GhostPlantPreparationBoundaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())

    def test_default_load_retains_current_policy_and_natural_base_only_identities(self):
        self.assertEqual(len(available_pet_pairs()), 31)
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())
        for slug in SPECIES:
            species = PetSpecies.objects.get(slug=slug)
            egg = ItemDefinition.objects.get(slug=f"{slug}-egg")
            self.assertEqual((species.sprite_key, species.rarity, egg.rarity, egg.coin_value),
                             (slug, RARITIES[slug], RARITIES[slug], 3))
            self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base"})
            self.assertEqual((egg.pet_species_id, egg.metadata), (species.pk, {"species": slug}))
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_explicit_prepared_load_under_current_policy_fails_atomically(self):
        before_species = list(PetSpecies.objects.order_by("pk").values())
        before_items = list(ItemDefinition.objects.order_by("pk").values())
        before_potions = list(PetSpecies.available_potions.through.objects.order_by("pk").values())
        before_quests = list(QuestDefinition.objects.order_by("pk").values())
        with self.assertRaisesRegex(CommandError, "compatibility"):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertEqual(list(PetSpecies.objects.order_by("pk").values()), before_species)
        self.assertEqual(list(ItemDefinition.objects.order_by("pk").values()), before_items)
        self.assertEqual(list(PetSpecies.available_potions.through.objects.order_by("pk").values()), before_potions)
        self.assertEqual(list(QuestDefinition.objects.order_by("pk").values()), before_quests)

    @override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY)
    def test_scoped_future_policy_loads_four_paths_idempotently_without_registration(self):
        eggs = dict(ItemDefinition.objects.filter(slug__in=[f"{slug}-egg" for slug in SPECIES]).values_list("slug", "pk"))
        for _ in range(2):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertEqual(len(available_pet_pairs()), 35)
        self.assertEqual(set(QuestDefinition.objects.filter(name__in=PATHS).values_list("name", flat=True)), set(PATHS))
        self.assertEqual(dict(ItemDefinition.objects.filter(slug__in=eggs).values_list("slug", "pk")), eggs)
        self.assertFalse(ChallengeGoal.objects.exists())

    @override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY)
    def test_forged_partial_and_unregistered_species_fail_without_writes(self):
        source = yaml.safe_load((settings.BASE_DIR / PACK / "pet_species.yaml").read_text())["species"][0]
        candidates = [
            {**source, "available_potions": ["base", "fire"]},
            {**source, "sprite_key": "meshtint-potted-plant"},
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
        with override_settings(RPG_ASSET_SUPPORT_POLICY=future_policy(("meshtint-ghost", "fire"))):
            with self.assertRaisesRegex(CommandError, "compatibility"):
                call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())

    def test_descriptor_receiving_handles_require_system_collection_identity(self):
        descriptor = json.loads(POLICY_PATH.with_name("elemental-ghost-potted-plant.json").read_text())
        self.assertEqual(descriptor["preparation"]["state"], "private_review_pending")
        self.assertTrue(descriptor["preparation"]["candidate_verified"])
        self.assertFalse(descriptor["preparation"]["acquisition_active"])
        self.assertFalse(descriptor["preparation"]["artwork_accepted"])
        self.assertEqual(descriptor["release"], {
            "family_id": PRIVATE_RELEASE_FAMILY,
            "release_version": "1.0.0",
            "manifest_sha256": PRIVATE_MANIFEST_SHA256,
        })
        self.assertEqual(descriptor["private_review"]["index_sha256"], PRIVATE_REVIEW_INDEX_SHA256)
        self.assertEqual(descriptor["private_review"]["index_bytes"], 4994)
        self.assertEqual(descriptor["private_review"]["canonical_publication"], "not_performed")
        for name, (_species, _potion, icon) in PATHS.items():
            with self.subTest(name=name):
                definition = QuestDefinition(name=name, quest_type="collection", is_system=True)
                self.assertEqual(challenge_catalog_icon(definition), icon)
                definition.is_system = False
                self.assertIsNone(challenge_catalog_icon(definition))
                definition.is_system, definition.quest_type = True, "boss"
                self.assertIsNone(challenge_catalog_icon(definition))

    def test_verified_private_pin_leaves_default_catalog_and_prepared_loading_inactive(self):
        active = json.loads((settings.BASE_DIR / "frontend/assets.lock.json").read_text())["releases"]
        evaluation = json.loads((settings.BASE_DIR / "frontend/assets.ghost-potted-plant.evaluation.lock.json").read_text())
        self.assertEqual(len(active), 14)
        self.assertNotIn(PRIVATE_RELEASE_FAMILY, {release["family_id"] for release in active})
        self.assertEqual(evaluation, {"schema_version": 1, "releases": [{
            "family_id": PRIVATE_RELEASE_FAMILY,
            "release_version": "1.0.0",
            "manifest_sha256": PRIVATE_MANIFEST_SHA256,
            "directory": f"{PRIVATE_RELEASE_FAMILY}/1.0.0/{PRIVATE_MANIFEST_SHA256}",
        }]})
        policy = json.loads(POLICY_PATH.read_text())
        self.assertNotIn(PRIVATE_RELEASE_FAMILY, {source["id"] for source in policy["sources"]})

        # A verified receiving candidate is presentation evidence, not authority
        # to publish offers, change default content, or grant rewards.
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(len(available_pet_pairs()), 31)
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())
        self.assertEqual(QuestDefinition.objects.filter(
            is_system=True, reward_items__item__item_type="potion",
            reward_items__item__potion_type__slug__in=("fire", "ice"),
        ).distinct().count(), 16)
        child = make_family("Private candidate reader", children=[{"username": "private-candidate-reader"}]).children[0]
        client = APIClient()
        client.force_authenticate(child)
        inventory = list(UserInventory.objects.order_by("pk").values())
        response = client.get("/api/pets/codex/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["mounts_possible"], 31)
        for species in response.data["species"]:
            if species["slug"] in SPECIES:
                self.assertEqual({potion["slug"] for potion in species["available_potions"]}, {"base"})
        with self.assertRaisesRegex(CommandError, "compatibility"):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        self.assertFalse(QuestDefinition.objects.filter(name__in=PATHS).exists())
        self.assertEqual(len(available_pet_pairs()), 31)
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), inventory)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_previous_facts_do_not_replay_into_future_prepared_goals(self):
        child = make_family("Before Ghost preparation", children=[{"username": "before-ghost"}]).children[0]
        ingest_activity(child, "chore_complete", "before-ghost-pack", "chore_complete")
        with override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
            rows = [row for row in list_goals(child)["results"] if row["name"] in PATHS]
        self.assertEqual({row["name"] for row in rows}, set(PATHS))
        self.assertEqual({row["progress"] for row in rows}, {"0"})

    def test_ordinary_reload_keeps_staged_offers_hidden_and_existing_eggs_intact(self):
        eggs = dict(ItemDefinition.objects.filter(slug__in=[f"{slug}-egg" for slug in SPECIES]).values_list("slug", "pk"))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY):
            call_command("loadrpgcontent", pack=PACK, stdout=StringIO())
        call_command("loadrpgcontent", stdout=StringIO())
        self.assertEqual(len(available_pet_pairs()), 31)
        self.assertEqual(dict(ItemDefinition.objects.filter(slug__in=eggs).values_list("slug", "pk")), eggs)
        for species in PetSpecies.objects.filter(slug__in=SPECIES):
            self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base"})
        staged = QuestDefinition.objects.filter(name__in=PATHS)
        self.assertEqual(staged.count(), 4)
        self.assertFalse(any(definition_is_available(row) for row in staged))
        self.assertFalse(ChallengeGoal.objects.exists())


@override_settings(RPG_ASSET_SUPPORT_POLICY=FUTURE_POLICY,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FutureGhostPlantPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())
        cls.original_eggs = dict(ItemDefinition.objects.filter(
            slug__in=[f"{species}-egg" for species in SPECIES]).values_list("slug", "pk"))
        call_command("loadrpgcontent", pack=PACK, stdout=StringIO())

    def setUp(self):
        household = make_family("Prepared Ghost/Plant", parents=[{"username": "prepared-parent"}],
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
        self.assertEqual(len(available_pet_pairs()), 35)
        definitions = self.definitions()
        for name, (species_slug, potion, image) in PATHS.items():
            with self.subTest(name=name):
                definition = definitions[name]
                species = PetSpecies.objects.get(slug=species_slug)
                egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
                ingredient = ItemDefinition.objects.get(slug=f"{potion}-potion")
                self.assertEqual(egg.pk, self.original_eggs[egg.slug])
                self.assertEqual((species.sprite_key, species.rarity, egg.rarity), (species_slug, RARITIES[species_slug], RARITIES[species_slug]))
                self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
                self.assertEqual((egg.item_type, egg.pet_species_id, egg.metadata), ("egg", species.pk, {"species": species_slug}))
                self.assertEqual((ingredient.item_type, ingredient.potion_type.slug), ("potion", potion))
                self.assertFalse(random_item_is_available(ingredient))
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days), ("collection", TARGETS[species_slug], 180))
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

    def test_twenty_shared_facts_award_all_four_exact_bundles_once_without_other_children(self):
        self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, set(PATHS))
        for index in range(20):
            trigger = ("chore_complete", "homework_complete", "milestone_complete", "project_complete")[index % 4]
            ingest_activity(self.child, trigger, f"prepared-action-{index}", trigger)
            if index == 3:
                self.assertFalse(ChallengeOccurrence.objects.filter(status="completed").exists())
            if index == 4:
                self.assertEqual(set(ChallengeOccurrence.objects.filter(status="completed").values_list("snapshot__name", flat=True)), {"Ember Sprout", "Frost Sprout"})
            if index == 18:
                self.assertFalse(ChallengeOccurrence.objects.filter(snapshot__name="Ember Wisp", status="completed").exists())
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
        self.assertEqual(inventory, {"meshtint-ghost-egg": 2, "meshtint-potted-plant-egg": 2, "fire-potion": 2, "ice-potion": 2})
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
            for slug in ("meshtint-ghost-egg", "meshtint-potted-plant-egg", "fire-potion", "ice-potion"):
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
            for index in range(20):
                ingest_activity(self.child, "chore_complete", f"saved-preparation-{index}", "chore_complete")
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual({row.pk: row.snapshot for row in occurrences}, accepted)
        for occurrence in occurrences:
            self.assertEqual(occurrence.status, "completed")
            self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
            self.assertTrue(all("salvaged_to_coins" not in row for row in occurrence.reward_receipt["items"]))
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), {
            "meshtint-ghost-egg": 2, "meshtint-potted-plant-egg": 2, "fire-potion": 2, "ice-potion": 2})
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 2)

    def test_child_selector_does_not_read_sibling_or_foreign_challenge_progress(self):
        for user, count in ((self.child, 2), (self.sibling, 1), (self.foreign, 3)):
            list_goals(user)
            for index in range(count):
                ingest_activity(user, "chore_complete", f"scoped-{user.pk}-{index}", "chore_complete")
        expected = ChallengeOccurrence.objects.get(goal__user=self.child, goal__catalog_definition__name="Ember Wisp")
        for selector in (self.sibling.pk, self.foreign.pk):
            response = self.client.get("/api/pets/codex/", {"user_id": selector})
            family = next(row for row in response.data["species"] if row["slug"] == "meshtint-ghost")
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
