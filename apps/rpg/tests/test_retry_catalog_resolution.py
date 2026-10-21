"""Preloaded retry reference resolution keeps ordinary catalog safeguards."""
from types import SimpleNamespace

from django.test import TestCase, override_settings

from apps.pets.models import PetSpecies, PotionType
from apps.rpg.catalog_support import _legacy_reference, egg_species, item_is_available, potion_type_for_item, preload_legacy_references


class RetryCatalogResolutionTests(TestCase):
    def test_preloaded_legacy_resolution_matches_default_without_more_queries(self):
        fox = PetSpecies.objects.create(slug="legacy-fox", name="Friendly Fox", sprite_key="legacy-fox")
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        reserved = PetSpecies.objects.create(slug="meshtint-wolf", name="Reserved Wolf", sprite_key="forged")
        base = PotionType.objects.create(slug="base", name="Base")
        species = list(PetSpecies.objects.prefetch_related("available_potions"))
        potions = list(PotionType.objects.all())
        cases = [
            SimpleNamespace(item_type="egg", pet_species=fox, metadata={"species": "missing"}),
            SimpleNamespace(item_type="egg", metadata={"species": "fRIENDLY fOX"}),
            SimpleNamespace(item_type="egg", metadata={"species": "legacy-fox"}),
            SimpleNamespace(item_type="egg", slug="chick-egg", metadata={"species": "chick"}),
            SimpleNamespace(item_type="egg", slug="meshtint-wolf-egg", metadata={"species": reserved.slug}),
            SimpleNamespace(item_type="egg", pet_species=reserved, metadata={"species": reserved.slug}),
            SimpleNamespace(item_type="egg", pet_species=chick, slug="chick-egg", metadata={"species": "chick"}),
            SimpleNamespace(item_type="egg", metadata={"species": "absent"}),
            SimpleNamespace(item_type="egg", metadata={"species": [fox.slug]}),
            SimpleNamespace(item_type="potion", potion_type=base, metadata={"variant": "missing"}),
            SimpleNamespace(item_type="potion", metadata={"variant": "bASE"}),
            SimpleNamespace(item_type="potion", metadata={"variant": "absent"}),
        ]
        species_cache = preload_legacy_references(PetSpecies, species, [item.metadata.get("species") for item in cases])
        potion_cache = preload_legacy_references(PotionType, potions, [item.metadata.get("variant") for item in cases])
        policy = {"schema_version": 1, "pets": [{"species_slug": fox.slug, "sprite_key": fox.sprite_key,
                  "potion_slugs": ["base"]}], "potion_slugs": ["base"]}
        for supported in (None, policy):
            with self.subTest(production=supported is None), override_settings(RPG_ASSET_SUPPORT_POLICY=supported):
                expected = [(egg_species(item) if item.item_type == "egg" else potion_type_for_item(item),
                             item_is_available(item)) for item in cases]
                with self.assertNumQueries(0):
                    actual = [(egg_species(item, legacy_species=species_cache) if item.item_type == "egg" else
                               potion_type_for_item(item, legacy_potions=potion_cache),
                               item_is_available(item, legacy_species=species_cache, legacy_potions=potion_cache)) for item in cases]
                self.assertEqual(actual, expected)

    def test_name_precedes_slug_and_an_empty_preloaded_catalog_never_queries(self):
        by_name = PetSpecies.objects.create(slug="another-slug", name="legacy-key", sprite_key="one")
        PetSpecies.objects.create(slug="legacy-key", name="Other name", sprite_key="two")
        rows = list(PetSpecies.objects.all())
        item = SimpleNamespace(item_type="egg", metadata={"species": "legacy-key"})
        self.assertEqual(egg_species(item).pk, by_name.pk)
        cached = preload_legacy_references(PetSpecies, rows, ["legacy-key"])
        with self.assertNumQueries(0):
            self.assertEqual(egg_species(item, legacy_species=cached).pk, by_name.pk)
            self.assertIsNone(egg_species(item, legacy_species=[]))

    def test_preloaded_names_use_actual_database_identity_semantics(self):
        PetSpecies.objects.create(slug="unicode-pet", name="Straße", sprite_key="unicode")
        PetSpecies.objects.create(slug="unicode-other", name="Änne", sprite_key="unicode-other")
        rows = list(PetSpecies.objects.all())
        keys = ["STRASSE", "Straße", "straße", "Änne", "änne", "unicode-pet", "missing"]
        cached = preload_legacy_references(PetSpecies, rows, keys)
        for key in keys:
            with self.subTest(key=key):
                direct = _legacy_reference(PetSpecies, key)
                self.assertEqual(_legacy_reference(PetSpecies, key, rows=rows), direct)
                with self.assertNumQueries(0):
                    self.assertEqual(_legacy_reference(PetSpecies, key, rows=cached), direct)
