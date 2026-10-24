"""Bee/Bat elemental discovery uses exact offers and frozen earned promises."""
from copy import deepcopy
from decimal import Decimal
from io import StringIO
import json
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.pets.serializers import PetCodexEntrySerializer, PetSpeciesCatalogSerializer
from apps.quests.availability import definition_is_available
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.quests.services import QuestService
from apps.rpg.catalog_icons import challenge_catalog_icon
from apps.rpg.catalog_support import POLICY_PATH, available_pet_pairs, pet_is_available, random_item_is_available
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


PATHS = {
    "Ember Hive": ("meshtint-bee", "fire", 5, 180, "review-bee-fire-acquisition-icon"),
    "Frost Hive": ("meshtint-bee", "ice", 5, 180, "review-bee-ice-acquisition-icon"),
    "Ember Cave": ("meshtint-bat", "fire", 10, 180, "review-bat-fire-acquisition-icon"),
    "Frost Cave": ("meshtint-bat", "ice", 10, 180, "review-bat-ice-acquisition-icon"),
}
NEW_SPECIES = {"meshtint-bee", "meshtint-bat"}
PREVIOUS_ELEMENTAL_SPECIES = {"chick", "meshtint-wolf", "meshtint-dragon", "meshtint-mushroom"}
TRIGGERS = {
    "chore_complete", "homework_complete", "milestone_complete", "project_complete",
    "creation_logged", "reading_logged",
}


def bee_bat_policy(*pairs):
    """Retain all previous production pairs, selectively adopting this batch."""
    policy = deepcopy(json.loads(POLICY_PATH.read_text()))
    for row in policy["pets"]:
        if row["species_slug"] in NEW_SPECIES:
            row["potion_slugs"] = ["base"]
    for species, potion in pairs:
        next(row for row in policy["pets"] if row["species_slug"] == species)["potion_slugs"].append(potion)
    return policy


@override_settings(RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalBeeBatPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())

    def setUp(self):
        household = make_family(
            "Elemental Bee/Bat", parents=[{"username": "bee-bat-parent"}],
            children=[{"username": "bee-bat-child"}, {"username": "bee-bat-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        foreign = make_family(
            "Other elemental Bee/Bat", parents=[{"username": "bee-bat-foreign-parent"}],
            children=[{"username": "bee-bat-foreign-child"}],
        )
        self.foreign_parent, self.foreign = foreign.parents[0], foreign.children[0]
        self.client = APIClient()
        self.client.force_authenticate(self.child)
        drops = patch("apps.rpg.services.DropService.process_drops", return_value=[])
        drops.start()
        self.addCleanup(drops.stop)

    def definitions(self):
        definitions = {row.name: row for row in QuestDefinition.objects.filter(name__in=PATHS)}
        self.assertEqual(set(definitions), set(PATHS))
        return definitions

    def isolate_paths(self):
        QuestDefinition.objects.exclude(name__in=PATHS).update(is_system=False)
        return self.definitions()

    def codex(self, **params):
        response = self.client.get("/api/pets/codex/", params)
        self.assertEqual(response.status_code, 200)
        return response.data

    def paths(self, body, species, potion):
        family = next(row for row in body["species"] if row["slug"] == species)
        variant = next((row for row in family["available_potions"] if row["slug"] == potion), None)
        self.assertIsNotNone(variant, f"Missing exact supported pair {species}/{potion}")
        return variant["acquisition_challenges"]

    def test_production_adds_only_four_pairs_and_records_the_exact_elemental_source(self):
        policy = json.loads(POLICY_PATH.read_text())
        species = {row["species_slug"] for row in policy["pets"]}
        pairs = {(row["species_slug"], potion) for row in policy["pets"] for potion in row["potion_slugs"]}
        self.assertEqual(len(species), 15)
        self.assertEqual(pairs, {(slug, "base") for slug in species} | {
            (slug, potion) for slug in PREVIOUS_ELEMENTAL_SPECIES | NEW_SPECIES for potion in ("fire", "ice")
        })
        self.assertEqual(len(available_pet_pairs()), 27)
        descriptor = json.loads(POLICY_PATH.with_name("elemental-bee-bat.json").read_text())["release"]
        source = next(row for row in policy["sources"] if row["id"] == descriptor["family_id"])
        self.assertEqual((source["release_version"], source["manifest_sha256"]), (
            "1.0.0", "7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5",
        ))
        self.assertEqual((source["release_version"], source["manifest_sha256"]),
                         (descriptor["release_version"], descriptor["manifest_sha256"]))
        self.assertEqual(source["appearance_bindings_version"], 1)
        self.assertEqual(set(source["prepared_species"]), NEW_SPECIES)
        self.assertEqual(set(source["prepared_potion_variants"]), {"fire", "ice"})
        for row in policy["pets"]:
            if row["species_slug"] in NEW_SPECIES:
                self.assertEqual(row["sprite_key"], row["species_slug"])
                self.assertEqual(row["source"], "meshtint-companion-roster")
                self.assertEqual(row["potion_sources"], {"fire": source["id"], "ice": source["id"]})

    def test_authored_paths_keep_typed_eggs_global_potions_and_approved_image_ids(self):
        descriptor = json.loads(POLICY_PATH.with_name("elemental-bee-bat.json").read_text())
        self.assertEqual({
            challenge["name"]: (family["species_slug"], challenge["potion_slug"],
                                challenge["target_count"], challenge["window_days"], challenge["catalog_icon"])
            for family in descriptor["families"] for challenge in family["challenges"]
        }, PATHS)
        definitions = self.definitions()
        for name, (species_slug, potion, target, days, image_id) in PATHS.items():
            with self.subTest(name=name):
                definition = definitions[name]
                species = PetSpecies.objects.get(slug=species_slug)
                egg = ItemDefinition.objects.get(slug=f"{species_slug}-egg")
                ingredient = ItemDefinition.objects.get(slug=f"{potion}-potion")
                self.assertEqual(species.sprite_key, species_slug)
                self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), {"base", "fire", "ice"})
                self.assertEqual((egg.item_type, egg.pet_species_id, egg.metadata),
                                 ("egg", species.pk, {"species": species_slug}))
                self.assertEqual((ingredient.item_type, ingredient.potion_type.slug, ingredient.metadata.get("variant")),
                                 ("potion", potion, potion))
                self.assertFalse(random_item_is_available(ingredient))
                self.assertEqual((definition.quest_type, definition.target_value, definition.duration_days),
                                 ("collection", target, days))
                self.assertTrue(definition.is_system)
                self.assertFalse(definition.is_repeatable)
                self.assertFalse(definition.is_cooperative)
                self.assertIsNone(definition.created_by_id)
                self.assertIsNone(definition.required_badge_id)
                self.assertEqual((definition.coin_reward, definition.xp_reward), (0, 0))
                self.assertEqual(set(definition.trigger_filter["allowed_triggers"]), TRIGGERS)
                self.assertEqual({row.item_id: row.quantity for row in definition.reward_items.all()},
                                 {egg.pk: 1, ingredient.pk: 1})
                self.assertEqual(challenge_catalog_icon(definition), image_id)
        self.assertEqual(set(PotionType.objects.values_list("slug", flat=True)), {"base", "fire", "ice"})
        self.assertFalse(ItemDefinition.objects.filter(item_type="egg", slug__in=[
            f"{species}-{potion}-egg" for species in NEW_SPECIES for potion in ("fire", "ice")
        ]).exists())

    def test_codex_reads_all_twelve_guarantees_by_exact_pair_without_materializing_or_awarding(self):
        expected_families = {
            "chick": "Nest", "meshtint-wolf": "Trail", "meshtint-mushroom": "Grove",
            "meshtint-dragon": "Summit", "meshtint-bee": "Hive", "meshtint-bat": "Cave",
        }
        with CaptureQueriesContext(connection) as queries:
            body = self.codex()
        self.assertEqual(len(body["species"]), 15)
        self.assertEqual(sum(len(row["available_potions"]) for row in body["species"]), 27)
        guarantees = []
        for species, suffix in expected_families.items():
            for potion, prefix in (("fire", "Ember"), ("ice", "Frost")):
                with self.subTest(species=species, potion=potion):
                    rows = self.paths(body, species, potion)
                    self.assertEqual([row["name"] for row in rows], [f"{prefix} {suffix}"])
                    self.assertTrue(rows[0]["offer_available"])
                    self.assertIsNone(rows[0]["attempt"])
                    self.assertEqual(rows[0]["path"], "/quests?tab=trials")
                    guarantees.extend(rows)
        self.assertEqual(len(guarantees), 12)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
                             for query in queries))
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(ChallengeOccurrence.objects.exists())
        self.assertFalse(UserInventory.objects.exists())

    def test_new_whole_offers_are_visible_in_native_and_mcp_catalogs(self):
        from apps.mcp_server.catalog import catalog_row

        definitions = self.isolate_paths()
        self.assertEqual({row["name"] for row in self.client.get("/api/quests/available/").data}, set(PATHS))
        for definition in definitions.values():
            self.assertTrue(definition_is_available(definition))
            self.assertTrue(catalog_row("quests", definition)["available_for_new_user"])
        self.client.force_authenticate(self.parent)
        self.assertEqual({row["name"] for row in self.client.get("/api/quests/catalog/").data}, set(PATHS))
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(UserInventory.objects.exists())

    def test_inventory_reads_preserve_exact_pair_hints_without_granting_items(self):
        self.isolate_paths()
        expected = {
            "fire-potion": {"Ember Hive", "Ember Cave"},
            "ice-potion": {"Frost Hive", "Frost Cave"},
            "meshtint-bee-egg": {"Ember Hive", "Frost Hive"},
            "meshtint-bat-egg": {"Ember Cave", "Frost Cave"},
        }
        for slug in expected:
            UserInventory.objects.create(user=self.child, item=ItemDefinition.objects.get(slug=slug), quantity=2)
        before = list(UserInventory.objects.order_by("pk").values())
        response = self.client.get("/api/inventory/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["item"]["slug"] for row in response.data}, set(expected))
        for row in response.data:
            self.assertEqual({source["name"] for source in row["item"]["acquisition_sources"]
                              if source["kind"] == "challenge"}, expected[row["item"]["slug"]])
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), before)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_codex_saved_progress_stays_self_scoped_for_sibling_and_foreign_selectors(self):
        definitions = self.isolate_paths()
        private = QuestDefinition.objects.create(
            name="Private foreign Bee progress", quest_type="collection", target_value=2,
            is_system=False, created_by=self.foreign_parent,
        )
        for slug in ("meshtint-bee-egg", "fire-potion"):
            QuestRewardItem.objects.create(quest_definition=private, item=ItemDefinition.objects.get(slug=slug))
        for user, count in ((self.child, 2), (self.sibling, 1), (self.foreign, 3)):
            list_goals(user)
            for index in range(count):
                ingest_activity(user, "chore_complete", f"own-progress-{user.pk}-{index}", "chore_complete")
        expected = ChallengeOccurrence.objects.get(goal__user=self.child,
                                                   goal__catalog_definition=definitions["Ember Hive"])
        before = list(ChallengeOccurrence.objects.order_by("pk").values())
        for selector in (self.sibling.pk, self.foreign.pk):
            with self.subTest(selector=selector), CaptureQueriesContext(connection) as queries:
                rows = self.paths(self.codex(user_id=selector), "meshtint-bee", "fire")
            self.assertEqual([row["definition_id"] for row in rows], [definitions["Ember Hive"].pk])
            self.assertEqual(rows[0]["attempt"]["id"], f"goal:{expected.pk}")
            self.assertEqual(rows[0]["attempt"]["progress"], "2")
            self.assertEqual(Decimal(rows[0]["attempt"]["target"]), Decimal(5))
            self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                                 for query in queries))
        self.assertEqual(list(ChallengeOccurrence.objects.order_by("pk").values()), before)
        self.assertFalse(UserInventory.objects.exists())

    def test_each_exact_pair_enables_only_its_matching_discovery(self):
        definitions = self.isolate_paths()
        for name, (species, potion, _target, _days, _image) in PATHS.items():
            with self.subTest(name=name), override_settings(RPG_ASSET_SUPPORT_POLICY=bee_bat_policy((species, potion))):
                self.assertEqual({row.name for row in definitions.values() if definition_is_available(row)}, {name})

    def test_withdrawn_pairs_hide_whole_offers_and_never_consume_ingredients(self):
        from apps.mcp_server.catalog import catalog_row

        definitions = self.isolate_paths()
        with override_settings(RPG_ASSET_SUPPORT_POLICY=bee_bat_policy()):
            self.assertEqual(len(available_pet_pairs()), 23)
            self.assertEqual(list_goals(self.child)["results"], [])
            self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
            self.assertEqual(self.client.get("/api/quests/available/").data, [])
            for name, definition in definitions.items():
                species_slug, potion_slug, _target, _days, _image = PATHS[name]
                with self.subTest(name=name):
                    self.assertFalse(definition_is_available(definition))
                    self.assertFalse(catalog_row("quests", definition)["available_for_new_user"])
                    for start in (lambda: QuestService.start_quest(self.child, definition.pk),
                                  lambda: QuestService.start_co_op_quest(definition.pk, [self.child, self.sibling])):
                        with self.assertRaisesRegex(ValueError, "artwork|available|not found"):
                            start()
                    species = PetSpecies.objects.get(slug=species_slug)
                    potion = PotionType.objects.get(slug=potion_slug)
                    self.assertFalse(pet_is_available(species, potion))
                    for serializer in (PetCodexEntrySerializer, PetSpeciesCatalogSerializer):
                        self.assertEqual([row["slug"] for row in serializer(species).data["available_potions"]], ["base"])
                    ingredients = [ItemDefinition.objects.get(slug=slug) for slug in (
                        f"{species_slug}-egg", f"{potion_slug}-potion",
                    )]
                    for item in ingredients:
                        UserInventory.objects.update_or_create(user=self.child, item=item, defaults={"quantity": 3})
                    response = self.client.post("/api/pets/incubations/", {
                        "egg_item_id": ingredients[0].pk, "potion_item_id": ingredients[1].pk,
                        "request_id": str(uuid4()),
                    }, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertTrue(all(UserInventory.objects.get(user=self.child, item=item).quantity == 3
                                        for item in ingredients))
            self.client.force_authenticate(self.parent)
            self.assertEqual(self.client.get("/api/quests/catalog/").data, [])
        self.assertFalse(PetIncubation.objects.filter(user=self.child).exists())
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())

    def test_shipped_paths_share_facts_and_pay_each_complete_bundle_exactly_once(self):
        self.isolate_paths()
        self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, set(PATHS))
        for index in range(10):
            trigger = ("chore_complete", "homework_complete", "milestone_complete", "project_complete")[index % 4]
            ingest_activity(self.child, trigger, f"bee-bat-action-{index}", trigger)
            if index == 4:
                self.assertEqual(set(ChallengeOccurrence.objects.filter(goal__user=self.child, status="completed")
                                     .values_list("snapshot__name", flat=True)), {"Ember Hive", "Frost Hive"})
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual(len(occurrences), 4)
        for occurrence in occurrences:
            species, potion, _target, _days, _image = PATHS[occurrence.snapshot["name"]]
            self.assertEqual(occurrence.status, "completed")
            self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
            self.assertEqual({row["item_id"]: row["quantity"] for row in occurrence.reward_receipt["items"]}, {
                ItemDefinition.objects.get(slug=f"{species}-egg").pk: 1,
                ItemDefinition.objects.get(slug=f"{potion}-potion").pk: 1,
            })
        receipts = {row.pk: row.reward_receipt for row in occurrences}
        inventory = dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity"))
        self.assertEqual(inventory, {
            "meshtint-bee-egg": 2, "meshtint-bat-egg": 2, "fire-potion": 2, "ice-potion": 2,
        })
        ingest_activity(self.child, "chore_complete", "bee-bat-action-0", "chore_complete")
        ingest_activity(self.child, "chore_complete", "bee-bat-after-completion", "chore_complete")
        list_goals(self.child)
        self.assertEqual({row.pk: row.reward_receipt for row in ChallengeOccurrence.objects.filter(goal__user=self.child)},
                         receipts)
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), inventory)
        self.assertFalse(UserInventory.objects.exclude(user=self.child).exists())

    def test_saved_promises_keep_snapshot_rewards_after_retirement_and_base_ownership(self):
        definitions = self.isolate_paths()
        for species in NEW_SPECIES:
            UserMount.objects.create(user=self.child, species=PetSpecies.objects.get(slug=species),
                                     potion=PotionType.objects.get(slug="base"))
        self.assertEqual({row["name"] for row in list_goals(self.child)["results"]}, set(PATHS))
        accepted = {row.pk: deepcopy(row.snapshot) for row in ChallengeOccurrence.objects.filter(goal__user=self.child)}
        QuestDefinition.objects.filter(pk__in=[row.pk for row in definitions.values()]).update(
            target_value=99, duration_days=3, coin_reward=7, xp_reward=11,
        )
        QuestRewardItem.objects.filter(quest_definition__in=definitions.values()).delete()
        with override_settings(RPG_ASSET_SUPPORT_POLICY=bee_bat_policy()):
            for index in range(10):
                ingest_activity(self.child, "chore_complete", f"saved-bee-bat-action-{index}", "chore_complete")
        occurrences = list(ChallengeOccurrence.objects.filter(goal__user=self.child))
        self.assertEqual({row.pk: row.snapshot for row in occurrences}, accepted)
        for occurrence in occurrences:
            self.assertEqual(occurrence.status, "completed")
            self.assertEqual((occurrence.reward_receipt["coins"], occurrence.reward_receipt["xp"]), (0, 0))
            self.assertTrue(all("salvaged_to_coins" not in row for row in occurrence.reward_receipt["items"]))
        self.assertEqual(dict(UserInventory.objects.filter(user=self.child).values_list("item__slug", "quantity")), {
            "meshtint-bee-egg": 2, "meshtint-bat-egg": 2, "fire-potion": 2, "ice-potion": 2,
        })
        self.assertEqual(UserMount.objects.filter(user=self.child).count(), 2)
