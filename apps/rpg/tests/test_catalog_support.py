"""Art policy restricts new offers without destroying existing catalog rows."""
from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies, PotionType
from apps.rpg.catalog_support import (
    available_items, available_pet_pairs, available_pet_variants,
    item_is_available, item_unavailable_reason, pet_is_available,
    potion_is_available, species_is_available,
)
from apps.rpg.models import ItemDefinition


SYNTHETIC_POLICY = {
    "schema_version": 1,
    "pets": [{"species_slug": "fox", "sprite_key": "fox", "potion_slugs": ["base", "fire"]}],
    "potion_slugs": ["base", "fire"], "disabled_item_types": [],
}


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class OwnedArtCatalogPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick", icon="🐤")
        cls.fox = PetSpecies.objects.create(slug="fox", name="Fox", sprite_key="fox", icon="🦊")
        cls.base = PotionType.objects.create(slug="base", name="Base")
        cls.fire = PotionType.objects.create(slug="fire", name="Fire")

    def test_positive_identity_requires_exact_species_and_sprite(self):
        self.assertTrue(species_is_available(self.chick))
        self.assertTrue(pet_is_available(self.chick, self.base))
        self.assertFalse(pet_is_available(self.chick, self.fire))
        self.assertFalse(pet_is_available(self.fox, self.base))
        self.assertFalse(pet_is_available(SimpleNamespace(slug="fox", sprite_key="cute-chick"), self.base))
        self.assertFalse(pet_is_available(SimpleNamespace(slug="chick", sprite_key="dragon"), self.base))
        self.assertFalse(pet_is_available(None))

    def test_only_base_potion_is_available(self):
        self.assertTrue(potion_is_available(self.base))
        self.assertFalse(potion_is_available(self.fire))
        self.assertFalse(potion_is_available(None))

    def test_unrestricted_legacy_relation_still_returns_only_approved_variants(self):
        self.assertQuerySetEqual(available_pet_variants(self.chick), [self.base])
        self.assertQuerySetEqual(available_pet_variants(self.fox), [])

    def test_authored_compatibility_is_intersected_not_replaced(self):
        self.chick.available_potions.set([self.base, self.fire])
        self.assertQuerySetEqual(available_pet_variants(self.chick), [self.base])
        self.chick.available_potions.set([self.fire])
        self.assertQuerySetEqual(available_pet_variants(self.chick), [])

    def test_batch_pet_pairs_match_single_species_querysets(self):
        # Empty legacy compatibility and a nonempty incompatible relation must
        # retain the same meaning in batch and individual reads.
        for authored in ([], [self.base, self.fire], [self.fire]):
            with self.subTest(authored=[potion.slug for potion in authored]):
                self.chick.available_potions.set(authored)
                expected = {
                    (species.pk, potion.pk)
                    for species in PetSpecies.objects.all()
                    for potion in available_pet_variants(species)
                }
                with self.assertNumQueries(3):
                    self.assertEqual(available_pet_pairs(), expected)

    def test_typed_item_identity_precedes_conflicting_legacy_metadata(self):
        egg = ItemDefinition.objects.create(slug="chick-egg", name="Conflicting Chick egg", item_type="egg", pet_species=self.fox, metadata={"species": "chick"})
        potion = ItemDefinition.objects.create(slug="base-potion", name="Conflicting Base potion", item_type="potion", potion_type=self.fire, metadata={"variant": "base"})
        self.assertFalse(item_is_available(egg))
        self.assertFalse(item_is_available(potion))
        egg.pet_species = self.chick
        potion.potion_type = self.base
        self.assertTrue(item_is_available(egg))
        self.assertTrue(item_is_available(potion))

    def test_legitimate_legacy_names_and_slugs_resolve_real_supported_rows(self):
        for name in ("Chick", "chick"):
            self.assertFalse(item_is_available(SimpleNamespace(item_type="egg", metadata={"species": name})))
            with override_settings(RPG_ASSET_SUPPORT_POLICY={
                "schema_version": 1, "pets": [{"species_slug": "chick", "sprite_key": "cute-chick", "potion_slugs": ["base"]}],
                "potion_slugs": ["base"],
            }):
                self.assertTrue(item_is_available(SimpleNamespace(item_type="egg", metadata={"species": name})))
        for name in ("Base", "base"):
            # Retain old metadata-only ingredients, without advertising them
            # as the canonical global Base offer for the prepared roster.
            self.assertFalse(item_is_available(SimpleNamespace(item_type="potion", metadata={"variant": name})))
            with override_settings(RPG_ASSET_SUPPORT_POLICY=SYNTHETIC_POLICY):
                self.assertTrue(item_is_available(SimpleNamespace(item_type="potion", metadata={"variant": name})))

    def test_missing_or_unrecognized_legacy_identity_cannot_unlock_art(self):
        for metadata in ({}, {"species": "wolf"}, {"species": ["chick"]}):
            self.assertFalse(item_is_available(SimpleNamespace(item_type="egg", metadata=metadata)))
        for metadata in ({}, {"variant": "Cosmic"}, {"variant": {"slug": "base"}}):
            self.assertFalse(item_is_available(SimpleNamespace(item_type="potion", metadata=metadata)))

    def test_accessories_are_blocked_but_existing_dom_and_utility_items_remain_usable(self):
        accessory = SimpleNamespace(item_type="cosmetic_pet_accessory")
        self.assertFalse(item_is_available(accessory))
        self.assertIn("Pet accessories", item_unavailable_reason(accessory))
        for kind in ("cosmetic_frame", "cosmetic_title", "cosmetic_theme", "food", "coin_pouch", "quest_scroll", "consumable"):
            item = SimpleNamespace(item_type=kind)
            self.assertTrue(item_is_available(item))
            self.assertIsNone(item_unavailable_reason(item))

    def test_filtered_items_preserve_order_and_all_saved_catalog_rows(self):
        keep = ItemDefinition.objects.create(slug="chick-egg", name="Supported egg", item_type="egg", pet_species=self.chick, metadata={"species": "chick"})
        reject = ItemDefinition.objects.create(name="Unsupported egg", item_type="egg", pet_species=self.fox)
        frame = ItemDefinition.objects.create(name="DOM frame", item_type="cosmetic_frame")
        rows = ItemDefinition.objects.filter(pk__in=[keep.pk, reject.pk, frame.pk]).order_by("-pk")
        self.assertEqual(available_items(rows), [frame, keep])
        self.assertEqual(ItemDefinition.objects.count(), 3)

    def test_synthetic_policy_override_is_explicit_and_scoped(self):
        self.assertFalse(pet_is_available(self.fox, self.fire))
        with override_settings(RPG_ASSET_SUPPORT_POLICY=SYNTHETIC_POLICY):
            self.assertTrue(pet_is_available(self.fox, self.fire))
            self.assertFalse(species_is_available(self.chick))
            self.assertTrue(item_is_available(SimpleNamespace(item_type="cosmetic_pet_accessory")))
        self.assertFalse(pet_is_available(self.fox, self.fire))
        self.assertFalse(item_is_available(SimpleNamespace(item_type="cosmetic_pet_accessory")))

    def test_invalid_override_fails_closed(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY={"schema_version": 2}):
            with self.assertRaises(ImproperlyConfigured):
                pet_is_available(self.chick, self.base)
