"""Approved Dragon/Mushroom acquisition and preserved withdrawn promises."""
from copy import deepcopy
from io import StringIO
import json
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import PetCodexEntrySerializer, PetSpeciesCatalogSerializer
from apps.quests.availability import definition_is_available
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.quests.services import QuestService
from apps.rpg.catalog_support import POLICY_PATH, available_pet_pairs, pet_is_available, random_item_is_available
from apps.rpg.catalog_icons import challenge_catalog_icon
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


PATHS = {
    "Ember Grove": ("meshtint-mushroom", "fire", 10, 180),
    "Frost Grove": ("meshtint-mushroom", "ice", 10, 180),
    "Ember Summit": ("meshtint-dragon", "fire", 50, 365),
    "Frost Summit": ("meshtint-dragon", "ice", 50, 365),
}
TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete",
    "creation_logged", "reading_logged",
}


def approved_policy(*pairs):
    policy = deepcopy(json.loads(POLICY_PATH.read_text()))
    # Start from the previous 19-pair release even after production activation.
    # A selective test must not inherit the other three expansion pairs or
    # elemental pairs introduced by later batches.
    for row in policy["pets"]:
        if row["species_slug"] in {"meshtint-dragon", "meshtint-mushroom", "meshtint-bee", "meshtint-bat"}:
            row["potion_slugs"] = ["base"]
    for species, potion in pairs:
        row = next(row for row in policy["pets"] if row["species_slug"] == species)
        if potion not in row["potion_slugs"]:
            row["potion_slugs"].append(potion)
    return policy


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalExpansionPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())

    def setUp(self):
        household = make_family("Elemental expansion", parents=[{"username": "expansion-parent"}],
                                children=[{"username": "expansion-child"}, {"username": "expansion-sibling"}])
        self.child, self.sibling = household.children
        self.parent = household.parents[0]
        self.client = APIClient()
        QuestDefinition.objects.exclude(name__in=PATHS).update(is_system=False)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def test_shipped_policy_retains_the_expansion_pairs_and_exact_source(self):
        policy = json.loads(POLICY_PATH.read_text())
        pairs = {(row["species_slug"], potion) for row in policy["pets"] for potion in row["potion_slugs"]}
        base_species = {row["species_slug"] for row in policy["pets"]}
        elemental_species = {"chick", "meshtint-wolf", "meshtint-dragon", "meshtint-mushroom", "meshtint-bee", "meshtint-bat"}
        self.assertEqual(pairs, {(species, "base") for species in base_species} | {
            (species, potion) for species in elemental_species for potion in ("fire", "ice")
        })
        self.assertEqual(len(base_species), 15)
        self.assertEqual(len(available_pet_pairs()), 27)
        descriptor = json.loads(POLICY_PATH.with_name("elemental-expansion.json").read_text())["release"]
        source = next(row for row in policy["sources"] if row["id"] == descriptor["family_id"])
        self.assertEqual((source["release_version"], source["manifest_sha256"]),
                         (descriptor["release_version"], descriptor["manifest_sha256"]))
        self.assertEqual(source["appearance_bindings_version"], 1)
        self.assertEqual(set(source["prepared_species"]), {"meshtint-dragon", "meshtint-mushroom"})
        self.assertEqual(set(source["prepared_potion_variants"]), {"fire", "ice"})
        for row in policy["pets"]:
            if row["species_slug"] in {"meshtint-dragon", "meshtint-mushroom"}:
                self.assertEqual(row["potion_sources"], {"fire": source["id"], "ice": source["id"]})

    def test_shipped_policy_exposes_whole_offers_and_exact_inventory_hints(self):
        from apps.mcp_server.catalog import catalog_row

        self.client.force_authenticate(self.child)
        for slug in ("fire-potion", "ice-potion", "meshtint-mushroom-egg", "meshtint-dragon-egg"):
            UserInventory.objects.create(user=self.child, item=ItemDefinition.objects.get(slug=slug))
        inventory = self.client.get("/api/inventory/")
        self.assertEqual(inventory.status_code, 200)
        expected = {
            "fire-potion": {"Ember Grove", "Ember Summit"},
            "ice-potion": {"Frost Grove", "Frost Summit"},
            "meshtint-mushroom-egg": {"Ember Grove", "Frost Grove"},
            "meshtint-dragon-egg": {"Ember Summit", "Frost Summit"},
        }
        self.assertEqual({row["item"]["slug"] for row in inventory.data}, set(expected))
        for row in inventory.data:
            self.assertEqual({source["name"] for source in row["item"]["acquisition_sources"]
                              if source["kind"] == "challenge"}, expected[row["item"]["slug"]])
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
        self.assertEqual({row["name"] for row in self.client.get("/api/quests/available/").data}, set(PATHS))
        for definition in QuestDefinition.objects.filter(name__in=PATHS):
            self.assertTrue(definition_is_available(definition))
            self.assertTrue(catalog_row("quests", definition)["available_for_new_user"])
        self.client.force_authenticate(self.parent)
        self.assertEqual({row["name"] for row in self.client.get("/api/quests/catalog/").data}, set(PATHS))

    def test_authored_paths_preserve_exact_eggs_and_deliberate_progression(self):
        receiving = json.loads(POLICY_PATH.with_name("elemental-expansion.json").read_text())
        self.assertEqual({
            challenge["name"]: (family["species_slug"], challenge["potion_slug"],
                                challenge["target_count"], challenge["window_days"])
            for family in receiving["families"] for challenge in family["challenges"]
        }, PATHS)
        for family in receiving["families"]:
            species = PetSpecies.objects.get(slug=family["species_slug"])
            self.assertEqual(species.sprite_key, family["sprite_key"])
            self.assertEqual(ItemDefinition.objects.get(slug=family["egg_item_slug"]).pet_species_id, species.pk)
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=PATHS)}
        self.assertEqual(set(definitions), set(PATHS))
        for name, (species_slug, potion, target, days) in PATHS.items():
            with self.subTest(name=name):
                definition = definitions[name]
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days),
                                 ("collection", target, days))
                self.assertTrue(definition.is_system)
                self.assertFalse(definition.is_repeatable)
                self.assertIsNone(definition.required_badge_id)
                self.assertEqual((definition.coin_reward, definition.xp_reward), (0, 0))
                self.assertEqual(challenge_catalog_icon(definition), f"challenge-{name.lower().replace(' ', '-')}")
                self.assertEqual(set(definition.trigger_filter["allowed_triggers"]), TRIGGERS)
                self.assertEqual({row.item.slug: row.quantity for row in definition.reward_items.select_related("item")},
                                 {f"{species_slug}-egg": 1, f"{potion}-potion": 1})
                species = PetSpecies.objects.get(slug=species_slug)
                self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
                egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
                self.assertEqual((egg.pet_species_id, egg.metadata), (species.pk, {"species": species_slug}))
        self.assertFalse(ItemDefinition.objects.filter(item_type="egg", slug__in=[
            f"{species}-{potion}-egg" for species, potion, _target, _days in PATHS.values()
        ]).exists())

    @override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy())
    def test_withdrawn_art_policy_hides_offers_across_catalogs_and_starts(self):
        from apps.mcp_server.catalog import catalog_row

        self.assertEqual(QuestDefinition.objects.filter(name__in=PATHS).count(), 4)
        self.assertEqual(list_goals(self.child)["results"], [])
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/quests/available/").data, [])
        self.assertEqual(self.client.get("/api/challenges/").data["locked_catalog"], [])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get("/api/quests/catalog/").data, [])
        for definition in QuestDefinition.objects.filter(name__in=PATHS):
            with self.subTest(name=definition.name):
                self.assertFalse(definition_is_available(definition))
                self.assertFalse(catalog_row("quests", definition)["available_for_new_user"])
                with self.assertRaisesRegex(ValueError, "artwork|available|not found"):
                    QuestService.start_quest(self.child, definition.pk)
                with self.assertRaisesRegex(ValueError, "artwork|available|not found"):
                    QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])
        ingest_activity(self.child, "chore_complete", "dormant-offer-action", "chore_complete")
        self.assertFalse(UserInventory.objects.filter(user=self.child).exists())

    @override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy())
    def test_withdrawn_pairs_cannot_enable_potion_choices_or_consume_ingredients(self):
        self.client.force_authenticate(self.child)
        self.assertEqual(len(available_pet_pairs()), 19)
        for species_slug, potion_slug, _target, _days in PATHS.values():
            with self.subTest(species=species_slug, potion=potion_slug):
                species = PetSpecies.objects.get(slug=species_slug)
                potion = PotionType.objects.get(slug=potion_slug)
                self.assertFalse(pet_is_available(species, potion))
                for serializer_class in (PetSpeciesCatalogSerializer, PetCodexEntrySerializer):
                    self.assertEqual([row["slug"] for row in serializer_class(species).data["available_potions"]], ["base"])
                egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
                ingredient = ItemDefinition.objects.get(slug=f"{potion_slug}-potion")
                for item in (egg, ingredient):
                    UserInventory.objects.update_or_create(user=self.child, item=item, defaults={"quantity": 3})
                response = self.client.post("/api/pets/incubations/", {
                    "egg_item_id": egg.pk, "potion_item_id": ingredient.pk, "request_id": str(uuid4()),
                }, format="json")
                self.assertEqual(response.status_code, 400)
                for item in (egg, ingredient):
                    self.assertEqual(UserInventory.objects.get(user=self.child, item=item).quantity, 3)
        self.assertFalse(PetIncubation.objects.filter(user=self.child).exists())
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())

    def test_each_exact_art_pair_enables_only_its_matching_offer(self):
        definitions = list(QuestDefinition.objects.filter(name__in=PATHS))
        self.assertEqual(len(definitions), 4)
        for name, (species, potion, _target, _days) in PATHS.items():
            with self.subTest(name=name), override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy((species, potion))):
                self.assertEqual({row.name for row in definitions if definition_is_available(row)}, {name})
        with override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy(("meshtint-mushroom", "fire"))):
            self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, {"Ember Grove"})

    @override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy())
    def test_withdrawn_definitions_do_not_leak_into_earned_potion_or_egg_hints(self):
        for slug in ("fire-potion", "ice-potion", "meshtint-mushroom-egg", "meshtint-dragon-egg"):
            UserInventory.objects.create(user=self.child, item=ItemDefinition.objects.get(slug=slug))
        self.client.force_authenticate(self.child)
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        for row in response.data:
            self.assertTrue(all(source["kind"] != "challenge" for source in row["item"]["acquisition_sources"]))
            if row["item"]["item_type"] == "potion":
                self.assertEqual(row["item"]["acquisition_sources"], [])
                self.assertFalse(random_item_is_available(ItemDefinition.objects.get(pk=row["item"]["id"])))

    def test_shipped_paths_share_facts_and_award_each_whole_bundle_once(self):
        # No synthetic art-policy override: this must exercise shipped support.
        self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, set(PATHS))
        for index in range(50):
            trigger = ("chore_complete", "homework_complete", "milestone_complete", "project_complete")[index % 4]
            ingest_activity(self.child, trigger, f"expansion-action-{index}", trigger)
            if index == 9:
                self.assertEqual(set(ChallengeOccurrence.objects.filter(goal__user=self.child, status="completed")
                                     .values_list("snapshot__name", flat=True)), {"Ember Grove", "Frost Grove"})
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual(len(occurrences), 4)
        for occurrence in occurrences:
            species, potion, _target, _days = PATHS[occurrence.snapshot["name"]]
            self.assertEqual(occurrence.status, "completed")
            self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
            self.assertEqual({row["item_id"]: row["quantity"] for row in occurrence.reward_receipt["items"]}, {
                ItemDefinition.objects.get(slug=f"{species}-egg").pk: 1,
                ItemDefinition.objects.get(slug=f"{potion}-potion").pk: 1,
            })
        before = {row.pk: row.reward_receipt for row in occurrences}
        ingest_activity(self.child, "chore_complete", "expansion-action-0", "chore_complete")
        ingest_activity(self.child, "chore_complete", "expansion-after-completion", "chore_complete")
        list_goals(self.child)
        self.assertEqual({row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}, before)
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), {
            "meshtint-mushroom-egg": 2, "meshtint-dragon-egg": 2, "fire-potion": 2, "ice-potion": 2,
        })

    @override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy())
    def test_saved_expansion_promise_survives_policy_retirement_and_base_ownership(self):
        species = PetSpecies.objects.get(slug="meshtint-mushroom")
        UserMount.objects.create(user=self.child, species=species, potion=PotionType.objects.get(slug="base"))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=approved_policy((species.slug, "fire"))):
            self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, {"Ember Grove"})
        for index in range(10):
            ingest_activity(self.child, "chore_complete", f"saved-expansion-{index}", "chore_complete")
        receipt = ChallengeOccurrence.objects.get(goal__user=self.child).reward_receipt
        self.assertEqual((receipt["coins"], receipt["xp"]), (0, 0))
        self.assertTrue(all("salvaged_to_coins" not in row for row in receipt["items"]))
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="meshtint-mushroom-egg").quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item__slug="fire-potion").quantity, 1)
