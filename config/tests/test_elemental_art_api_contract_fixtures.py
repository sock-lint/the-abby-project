"""Real elemental image wire IDs do not authorize acquisition or grant items."""
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.pets.models import PetSpecies, PotionType
from apps.quests.models import ChallengeGoal, Quest, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


# Synthetic support is scoped to the catalog fixture's receiving check only.
# The checked-in production registry remains Base-only and is tested separately.
ELEMENTAL_FIXTURE_POLICY = {
    "schema_version": 1,
    "potion_slugs": ["base", "fire", "ice"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
    "pets": [
        {"species_slug": species, "sprite_key": sprite, "potion_slugs": ["base", "fire", "ice"]}
        for species, sprite in (("chick", "cute-chick"), ("meshtint-wolf", "meshtint-wolf"))
    ],
}


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None,
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ElementalArtApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family("Synthetic elemental image household", family_id=81,
                             parents=[{"id": 6, "username": "elemental-art-parent"}],
                             children=[{"id": 7, "username": "elemental-art-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.fire = PotionType.objects.create(id=41, slug="fire", name="Fire", rarity="uncommon")
        self.ice = PotionType.objects.create(id=42, slug="ice", name="Ice", rarity="uncommon")
        self.potions = {}
        for item_id, potion in ((51, self.fire), (52, self.ice)):
            self.potions[potion.slug] = ItemDefinition.objects.create(
                id=item_id, slug=f"{potion.slug}-potion", name=f"{potion.name} Potion", item_type="potion",
                potion_type=potion, metadata={"variant": potion.slug}, rarity="uncommon", icon="P",
            )
        self.spoof = ItemDefinition.objects.create(
            id=53, slug="custom-fire-potion", name="Fire Potion", item_type="potion", potion_type=self.fire,
            metadata={"variant": "fire"}, rarity="uncommon", icon="CUSTOM",
        )
        self.mismatch = ItemDefinition.objects.create(
            id=54, slug="custom-ice-potion", name="Ice Potion", item_type="potion", potion_type=self.ice,
            metadata={"variant": "fire"}, rarity="uncommon", icon="MISMATCH",
        )
        for inventory_id, item in enumerate((*self.potions.values(), self.spoof, self.mismatch), 101):
            UserInventory.objects.create(id=inventory_id, user=self.child, item=item, quantity=2)
        outsider = make_family("Other synthetic elemental household", family_id=82,
                               children=[{"id": 8, "username": "elemental-art-outsider"}]).children[0]
        UserInventory.objects.create(id=111, user=outsider, item=self.potions["fire"], quantity=9)

    def test_owned_elemental_potion_images_preserve_identity_without_enabling_new_acquisition(self):
        before = list(UserInventory.objects.order_by("pk").values())
        self.client.force_authenticate(self.child)
        rows = self.assert_response_fixture(self.client.get("/api/inventory/"), "catalog-icons-elemental-inventory.json")
        self.assertEqual({row["item"]["id"]: row["item"]["catalog_icon"] for row in rows}, {
            51: "item-fire-potion", 52: "item-ice-potion", 53: None, 54: None,
        })
        self.assertEqual({row["id"] for row in rows}, {101, 102, 103, 104})
        for row in rows:
            self.assertEqual(row["quantity"], 2)
            self.assertFalse(row["item"]["catalog_available"])
            self.assertEqual(row["available_actions"], [])
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), before)
        self.assertFalse(CoinLedger.objects.exists())

    def test_exact_system_challenge_images_and_whole_reward_pairs_use_explicit_synthetic_support(self):
        eggs = {}
        for species_id, slug, sprite, name, egg_id in (
            (61, "chick", "cute-chick", "Chick", 71),
            (62, "meshtint-wolf", "meshtint-wolf", "Wolf", 72),
        ):
            species = PetSpecies.objects.create(id=species_id, slug=slug, name=name, sprite_key=sprite, icon="S")
            species.available_potions.add(self.fire, self.ice)
            eggs[slug] = ItemDefinition.objects.create(
                id=egg_id, slug=f"{slug}-egg", name="Chick Egg" if slug == "chick" else "Wolf Pup Egg",
                item_type="egg", pet_species=species, metadata={"species": slug}, icon="E",
            )
        paths = (
            (91, "Ember Nest", "chick", "fire", 5, "challenge-ember-nest"),
            (92, "Frost Nest", "chick", "ice", 5, "challenge-frost-nest"),
            (93, "Ember Trail", "meshtint-wolf", "fire", 20, "challenge-ember-trail"),
            (94, "Frost Trail", "meshtint-wolf", "ice", 20, "challenge-frost-trail"),
        )
        for definition_id, name, species, potion, target, _ in paths:
            definition = QuestDefinition.objects.create(
                id=definition_id, name=name, quest_type="collection", target_value=target, duration_days=180,
                is_system=True, is_repeatable=False, coin_reward=0, xp_reward=0,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            for reward_id, item in ((definition_id * 2, eggs[species]), (definition_id * 2 + 1, self.potions[potion])):
                QuestRewardItem.objects.create(id=reward_id, quest_definition=definition, item=item, quantity=1)
        QuestDefinition.objects.create(id=95, name="Ember Nest", quest_type="collection", target_value=5,
                                       is_system=False, created_by=self.parent)
        self.client.force_authenticate(self.parent)
        # A valid image ID cannot expose an unapproved whole acquisition bundle.
        production = self.client.get("/api/quests/catalog/")
        self.assertEqual(production.status_code, 200)
        self.assertEqual([row["id"] for row in production.json()], [95])
        before = list(UserInventory.objects.order_by("pk").values())
        with override_settings(RPG_ASSET_SUPPORT_POLICY=ELEMENTAL_FIXTURE_POLICY):
            rows = self.assert_response_fixture(self.client.get("/api/quests/catalog/"), "catalog-icons-elemental-challenges.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in rows}, {
            **{definition_id: asset_id for definition_id, _, _, _, _, asset_id in paths}, 95: None,
        })
        by_id = {row["id"]: row for row in rows}
        for definition_id, _, species, potion, _, _ in paths:
            rewards = by_id[definition_id]["reward_items"]
            self.assertEqual({reward["item"] for reward in rewards}, {eggs[species].pk, self.potions[potion].pk})
            self.assertEqual(len(rewards), 2)
            self.assertTrue(all(reward["item_catalog_available"] and reward["quantity"] == 1 for reward in rewards))
            self.assertEqual(next(reward["item_catalog_icon"] for reward in rewards if reward["item_type"] == "potion"), f"item-{potion}-potion")
        self.assertEqual(list(UserInventory.objects.order_by("pk").values()), before)
        self.assertFalse(Quest.objects.exists())
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(CoinLedger.objects.exists())
