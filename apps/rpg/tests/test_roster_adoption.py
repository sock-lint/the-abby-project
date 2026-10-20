"""Prepared roster identity, additive loading and acquisition probabilities."""
from io import StringIO
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserPet
from apps.pets.services import PetService
from apps.rpg.catalog_support import item_is_available, pet_is_available, random_item_is_available
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.models import DropTable, ItemDefinition, UserInventory
from config.tests.factories import make_family


def _claim_test_incubation(user, egg_item_id, potion_item_id):
    incubation, _ = PetService.start_incubation(user, egg_item_id, potion_item_id, uuid4())
    # Only the disposable test row's deadline moves. The real explicit claim
    # remains responsible for materialization, badges and Chronicle hooks.
    PetIncubation.objects.filter(pk=incubation.pk).update(ready_at=timezone.now())
    _, pet, _ = PetService.hatch_incubation(user, incubation.pk)
    return pet


ROSTER = json.loads(Path("shared/catalog/companion-roster.json").read_text())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RosterLoadingTests(TestCase):
    def test_initial_load_keeps_legacy_definitions_and_exact_elemental_art_support(self):
        ContentPack("content/rpg/initial").load(stdout=StringIO())
        self.assertEqual(PetSpecies.objects.count(), 32)
        self.assertEqual(sum(pet_is_available(species) for species in PetSpecies.objects.all()), 15)
        for family in ROSTER["families"]:
            species = PetSpecies.objects.get(slug=family["species_slug"])
            self.assertEqual(species.sprite_key, family["sprite_key"])
            compatible = {"base", "fire", "ice"} if species.slug == "meshtint-wolf" else {"base"}
            self.assertEqual(set(species.available_potions.values_list("slug", flat=True)), compatible)
            for potion in PotionType.objects.all():
                self.assertEqual(pet_is_available(species, potion), potion.slug in compatible)
            egg = ItemDefinition.objects.get(slug=family["egg"]["item_slug"])
            self.assertEqual(egg.pet_species_id, species.pk)
            self.assertEqual(egg.metadata, {"species": species.slug})
            self.assertTrue(item_is_available(egg))
            self.assertEqual(egg.coin_value, 3)
            self.assertEqual(egg.rarity, species.rarity)
            self.assertEqual(species.food_preference, "")
            self.assertFalse(species.foods.exists())
        self.assertNotEqual(PetSpecies.objects.get(slug="wolf").pk, PetSpecies.objects.get(slug="meshtint-wolf").pk)
        self.assertFalse(PetSpecies.objects.filter(slug__icontains="dummy").exists())
        self.assertFalse(ItemDefinition.objects.filter(slug__icontains="dummy").exists())

    def test_namespaced_canonical_slugs_are_applied_once_and_metadata_is_canonical(self):
        PotionType.objects.create(slug="base", name="Base")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "pet_species.yaml").write_text(
                "species:\n  - slug: meshtint-bat\n    name: Bat\n    sprite_key: meshtint-bat\n    available_potions: [base]\n",
            )
            pack = ContentPack(path, namespace="meshtint-")
            pack.load()
            pack.load()
        species = PetSpecies.objects.get(slug="meshtint-bat")
        self.assertEqual(PetSpecies.objects.count(), 1)
        egg = ItemDefinition.objects.get(slug="meshtint-bat-egg")
        self.assertEqual(egg.metadata, {"species": "meshtint-bat"})
        self.assertEqual(egg.pet_species_id, species.pk)
        self.assertFalse(PotionType.objects.filter(slug="meshtint-base").exists())

    def test_existing_non_roster_pack_keeps_historical_namespace_semantics(self):
        base = PotionType.objects.create(slug="base", name="Base")
        species = PetSpecies.objects.create(slug="custom-custom-fox", name="Custom Fox", sprite_key="custom-fox")
        child = make_family(children=[{"username": "custom-pack-child"}]).children[0]
        pet = UserPet.objects.create(user=child, species=species, potion=base, name="Saved nickname", growth_points=76)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "pet_species.yaml").write_text(
                "species:\n  - slug: custom-fox\n    name: Custom Fox\n    sprite_key: custom-fox\n",
            )
            ContentPack(path, namespace="custom-").load()
        pet.refresh_from_db()
        self.assertEqual(PetSpecies.objects.get().slug, "custom-custom-fox")
        self.assertEqual(pet.species_id, species.pk)
        self.assertEqual((pet.name, pet.growth_points), ("Saved nickname", 76))
        self.assertEqual(ItemDefinition.objects.get().slug, "custom-custom-fox-egg")

    def test_arbitrary_base_alias_is_retained_but_excluded_from_new_acquisition(self):
        from apps.rewards.availability import reward_is_available
        from apps.rewards.models import CoinLedger, Reward, RewardRedemption
        from apps.rewards.services import CoinService, RewardService, RewardUnavailableError
        from apps.rpg.companion_catalog import reconcile_companion_offers
        from apps.rpg.serializers import ItemDefinitionSerializer
        from apps.rpg.services import DropService

        base = PotionType.objects.create(slug="base", name="Base")
        household = make_family(
            parents=[{"username": "base-alias-parent"}], children=[{"username": "base-alias-child"}],
        )
        user, parent = household.children[0], household.parents[0]
        alias = ItemDefinition.objects.create(
            slug="unregistered-base-potion", name="Saved Base alias", item_type="potion",
            potion_type=base, metadata={"variant": "base"},
        )
        UserInventory.objects.create(user=user, item=alias, quantity=3)
        offer = Reward.objects.create(
            family=user.family, name="Unknown Base offer", cost_coins=1,
            fulfillment_kind="digital_item", item_definition=alias,
        )
        DropTable.objects.create(trigger_type="clock_out", item=alias, weight=100)
        self.assertFalse(ItemDefinitionSerializer(alias).data["catalog_available"])
        self.assertFalse(reward_is_available(offer))
        with patch("apps.rpg.services.random.random", return_value=0):
            self.assertEqual(DropService.process_drops(user, "clock_out"), [])
        self.assertEqual(UserInventory.objects.get(user=user, item=alias).quantity, 3)
        with self.assertRaises(RewardUnavailableError):
            RewardService.request_redemption(user, offer)

        # An earlier paid promise retains its exact frozen item even after
        # that offer is retired. Simulate its existing persisted hold.
        promise = RewardRedemption.objects.create(user=user, reward=offer, coin_cost_snapshot=1)
        CoinLedger.objects.create(user=user, amount=9, reason="adjustment")
        CoinLedger.objects.create(user=user, amount=-1, reason="redemption", redemption=promise)
        held_balance = CoinService.get_balance(user)
        reconcile_companion_offers()
        RewardService.approve(promise, parent)
        RewardService.approve(promise, parent)
        promise.refresh_from_db()
        self.assertEqual(promise.item_definition_snapshot_id, alias.pk)
        self.assertEqual(promise.coin_cost_snapshot, 1)
        self.assertEqual(promise.status, "fulfilled")
        self.assertEqual(CoinService.get_balance(user), held_balance)
        self.assertEqual(UserInventory.objects.get(user=user, item=alias).quantity, 4)

    def test_display_name_collision_refuses_the_pack_without_crosswalking(self):
        PotionType.objects.create(slug="base", name="Base")
        old = PetSpecies.objects.create(slug="saved-bat", name="Bat", sprite_key="old-bat")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "pet_species.yaml").write_text(
                "species:\n  - slug: meshtint-bat\n    name: Bat\n    sprite_key: meshtint-bat\n    available_potions: [base]\n",
            )
            with self.assertRaisesRegex(ContentPackError, "collision"):
                ContentPack(path).load()
        self.assertEqual(PetSpecies.objects.count(), 1)
        self.assertEqual(PetSpecies.objects.get().pk, old.pk)
        self.assertFalse(ItemDefinition.objects.exists())

    def test_duplicate_normalized_species_and_non_base_prepared_variants_are_rejected(self):
        PotionType.objects.create(slug="base", name="Base")
        PotionType.objects.create(slug="fire", name="Fire")
        for entries, expected in [
            ("  - slug: bat\n    name: Bat\n    sprite_key: meshtint-bat\n    available_potions: [base]\n"
             "  - slug: meshtint-bat\n    name: Other Bat\n    sprite_key: meshtint-bat\n    available_potions: [base]\n", "duplicate"),
            ("  - slug: meshtint-bat\n    name: Bat\n    sprite_key: meshtint-bat\n    available_potions: [base, fire]\n", "Base"),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                (path / "pet_species.yaml").write_text("species:\n" + entries)
                with self.assertRaisesRegex(ContentPackError, expected):
                    ContentPack(path, namespace="meshtint-").load()
                self.assertFalse(PetSpecies.objects.exists())

    def test_egg_category_probability_is_preserved_when_distributing_fifteen_families(self):
        from apps.rpg.companion_catalog import companion_drop_weights

        ContentPack("content/rpg/initial").load(stdout=StringIO())
        entries = [entry for entry in DropTable.objects.filter(trigger_type="clock_out").select_related(
            "item", "item__pet_species", "item__potion_type",
        ) if random_item_is_available(entry.item)]
        weights = companion_drop_weights(entries)
        eggs = [(entry, weight) for entry, weight in zip(entries, weights) if entry.item.item_type == "egg"]
        self.assertEqual(len(eggs), 15)
        self.assertEqual(sum(entry.weight for entry, _weight in eggs), 83)
        self.assertAlmostEqual(sum(weight for _entry, weight in eggs), 10)
        other_total = sum(entry.weight for entry in entries if entry.item.item_type != "egg")
        self.assertEqual(other_total, 480)  # Base 10 + coin pouches 60 + food 410.
        self.assertAlmostEqual(sum(weights), other_total + 10)
        for entry, weight in zip(entries, weights):
            self.assertAlmostEqual(weight, entry.weight * 10 / 83 if entry.item.item_type == "egg" else entry.weight)
        self.assertAlmostEqual(sum(weight for _entry, weight in eggs) / sum(weights), 10 / (10 + other_total))
        for factor in [70, 50, 35]:
            biased = [entry.weight * factor for entry in entries]
            selected = companion_drop_weights(entries, biased)
            self.assertAlmostEqual(sum(weight for entry, weight in zip(entries, selected) if entry.item.item_type == "egg"), 10 * factor)
        with override_settings(RPG_ASSET_SUPPORT_POLICY={"schema_version": 1, "pets": [], "potion_slugs": []}):
            self.assertEqual(companion_drop_weights(entries), [entry.weight for entry in entries])
        custom = ItemDefinition.objects.create(
            slug="custom-chick-egg", name="Custom chick egg", item_type="egg",
            pet_species=PetSpecies.objects.get(slug="chick"),
        )
        custom_entry = DropTable.objects.create(trigger_type="clock_out", item=custom, weight=7)
        combined = companion_drop_weights([*entries, custom_entry])
        self.assertEqual(combined[-1], 7)

    def test_real_drop_and_expedition_rolls_keep_acquisition_tier_probabilities(self):
        from apps.pets.expeditions import ExpeditionService
        from apps.rpg.services import DropService

        ContentPack("content/rpg/initial").load(stdout=StringIO())
        user = make_family(children=[{"username": "drop-roster-child"}]).children[0]
        captures = []

        def select_food(entries, *, weights, k):
            captures.append((entries, weights))
            return [next(entry for entry in entries if entry.item.item_type == "food")]

        with patch("apps.rpg.services.random.random", return_value=0), patch(
            "apps.rpg.services.random.choices", side_effect=select_food,
        ):
            DropService.process_drops(user, "clock_out")
        entries, weights = captures.pop()
        self.assertTrue(all(entry.item.slug not in {"fire-potion", "ice-potion"} for entry in entries))
        for rarity, budget in {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}.items():
            self.assertAlmostEqual(sum(weight for entry, weight in zip(entries, weights) if entry.item.rarity == rarity), budget)
            egg_weights = [weight for entry, weight in zip(entries, weights) if entry.item.item_type == "egg" and entry.item.rarity == rarity]
            self.assertTrue(egg_weights)
            self.assertTrue(all(weight > 0 for weight in egg_weights))
            self.assertTrue(all(abs(weight - egg_weights[0]) < 1e-8 for weight in egg_weights))
        with patch("apps.pets.expeditions.random.choices", side_effect=select_food):
            ExpeditionService._roll_loot(user, "short")
        entries, weights = captures.pop()
        self.assertTrue(all(entry.item.slug not in {"fire-potion", "ice-potion"} for entry in entries))
        for rarity, budget in {"common": 70, "uncommon": 25, "rare": 5, "epic": 0, "legendary": 0}.items():
            self.assertAlmostEqual(sum(weight for entry, weight in zip(entries, weights) if entry.item.rarity == rarity), budget)
        # Every egg in a positive tier shares that tier's egg allocation; new
        # families cannot multiply either the overall tier or egg odds.
        common_eggs = [weight for entry, weight in zip(entries, weights) if entry.item.item_type == "egg" and entry.item.rarity == "common"]
        self.assertEqual(len(common_eggs), 10)  # Five families in two fallback triggers.
        self.assertTrue(all(weight > 0 and abs(weight - common_eggs[0]) < 1e-8 for weight in common_eggs))

    def test_mystery_box_keeps_egg_category_bounded_with_mixed_acquisition_rarities(self):
        from apps.rpg.services import ConsumableService

        ContentPack("content/rpg/initial").load(stdout=StringIO())
        user = make_family(children=[{"username": "mystery-roster-child"}]).children[0]
        box = ItemDefinition.objects.get(slug="mystery-box")
        UserInventory.objects.create(user=user, item=box)
        captured = []

        def select_food(items, *, weights, k):
            captured.append((items, weights))
            return [next(item for item in items if item.item_type == "food")]

        with patch("apps.rpg.services.random.choices", side_effect=select_food):
            ConsumableService.use(user, box.pk)
        items, weights = captured[0]
        self.assertTrue(all(item.slug not in {"fire-potion", "ice-potion"} for item in items))
        for rarity, budget in {"common": 70, "uncommon": 30}.items():
            self.assertAlmostEqual(sum(weight for item, weight in zip(items, weights) if item.rarity == rarity), budget)
            egg_weights = [weight for item, weight in zip(items, weights) if item.item_type == "egg" and item.rarity == rarity]
            self.assertEqual(len(egg_weights), 5)
            self.assertTrue(all(weight > 0 and abs(weight - egg_weights[0]) < 1e-8 for weight in egg_weights))
            self.assertLess(sum(egg_weights), budget)

    def test_all_prepared_families_use_explicit_server_growth_rules(self):
        from apps.pets.lifecycle import companion_lifecycle_stage, growth_thresholds

        ContentPack("content/rpg/initial").load(stdout=StringIO())
        base = PotionType.objects.get(slug="base")
        for family in ROSTER["families"]:
            with self.subTest(family=family["species_slug"]):
                species = PetSpecies.objects.get(slug=family["species_slug"])
                pet = UserPet(species=species, potion=base, growth_points=49)
                self.assertEqual(growth_thresholds(pet), (50, 100))
                self.assertEqual(companion_lifecycle_stage(pet), "baby")
                pet.growth_points = 50
                self.assertEqual(companion_lifecycle_stage(pet), "middle")
                pet.growth_points = 100
                self.assertEqual(companion_lifecycle_stage(pet), "middle")
                pet.evolved_to_mount = True
                self.assertEqual(companion_lifecycle_stage(pet), "grown")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PreparedEggIdentityTests(TestCase):
    def setUp(self):
        self.user = make_family(children=[{"username": "roster-kid"}]).children[0]
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.fire = PotionType.objects.create(slug="fire", name="Fire")
        self.species = PetSpecies.objects.create(slug="meshtint-bat", name="Bat", sprite_key="meshtint-bat")
        self.species.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(
            slug="meshtint-bat-egg", name="Bat Egg", item_type="egg",
            pet_species=self.species, metadata={"species": self.species.slug},
        )
        self.potion = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion",
            potion_type=self.base, metadata={"variant": "base"},
        )
        UserInventory.objects.create(user=self.user, item=self.egg)
        UserInventory.objects.create(user=self.user, item=self.potion)

    def test_exact_typed_canonical_egg_hatches_without_consuming_legacy_ownership(self):
        self.assertTrue(item_is_available(self.egg))
        pet = _claim_test_incubation(self.user, self.egg.pk, self.potion.pk)
        self.assertEqual(pet.species_id, self.species.pk)
        self.assertEqual(pet.potion_id, self.base.pk)
        self.assertEqual(pet.growth_points, 0)
        self.assertFalse(pet.evolved_to_mount)

    def test_portrait_identities_require_exact_prepared_species_and_egg_bindings(self):
        from apps.rpg.catalog_icons import item_catalog_icon, species_catalog_icon

        self.assertEqual(item_catalog_icon(self.egg), "bat-egg-portrait")
        self.assertEqual(species_catalog_icon(self.species), "bat-baby-portrait")
        self.assertEqual(species_catalog_icon(self.species, grown=True), "bat-grown-portrait")
        self.egg.metadata = {"species": "bat"}
        self.assertIsNone(item_catalog_icon(self.egg))
        self.species.sprite_key = "bat"
        self.assertIsNone(species_catalog_icon(self.species))

    def test_missing_conflicting_and_aliased_namespaced_eggs_fail_before_writes(self):
        old = PetSpecies.objects.create(slug="bat", name="Legacy Bat", sprite_key="bat")
        for slug, typed, metadata in [
            ("meshtint-bat-egg", None, {"species": "meshtint-bat"}),
            ("meshtint-bat-egg", self.species, {"species": "Bat"}),
            ("meshtint-bat-egg", self.species, {"species": "bat"}),
            ("meshtint-bat-egg", self.species, {}),
            ("meshtint-bat-egg", old, {"species": "meshtint-bat"}),
            ("bat-egg", self.species, {"species": "meshtint-bat"}),
        ]:
            with self.subTest(slug=slug, typed=typed, metadata=metadata):
                self.egg.slug, self.egg.pet_species, self.egg.metadata = slug, typed, metadata
                self.egg.save()
                self.assertFalse(item_is_available(self.egg))
                with self.assertRaises(ValueError):
                    PetService.start_incubation(self.user, self.egg.pk, self.potion.pk, uuid4())
                self.assertEqual(UserInventory.objects.get(user=self.user, item=self.egg).quantity, 1)
                self.assertFalse(UserPet.objects.filter(user=self.user).exists())

    def test_display_name_fallback_cannot_hatch_a_prepared_family_without_typed_binding(self):
        self.egg.slug = "legacy-bat-egg"
        self.egg.pet_species = None
        self.egg.metadata = {"species": "Bat"}
        self.egg.save()
        with self.assertRaises(ValueError):
            PetService.start_incubation(self.user, self.egg.pk, self.potion.pk, uuid4())
        self.assertFalse(item_is_available(self.egg))
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.egg).quantity, 1)
        self.assertEqual(UserInventory.objects.get(user=self.user, item=self.potion).quantity, 1)
        self.assertFalse(UserPet.objects.filter(user=self.user).exists())

    def test_non_base_or_aliased_base_ingredients_do_not_hatch_prepared_family(self):
        for slug, potion, metadata in [
            ("fire-potion", self.fire, {"variant": "fire"}),
            ("meshtint-base-potion", self.base, {"variant": "base"}),
            ("base-potion", self.base, {"variant": "fire"}),
        ]:
            with self.subTest(slug=slug, potion=potion.slug, metadata=metadata):
                self.potion.slug, self.potion.potion_type, self.potion.metadata = slug, potion, metadata
                self.potion.save()
                with self.assertRaises(ValueError):
                    PetService.start_incubation(self.user, self.egg.pk, self.potion.pk, uuid4())
                self.assertEqual(UserInventory.objects.get(user=self.user, item=self.potion).quantity, 1)
                self.assertEqual(UserInventory.objects.get(user=self.user, item=self.egg).quantity, 1)
                self.assertFalse(UserPet.objects.filter(user=self.user).exists())

    def test_dry_run_and_load_report_conflicting_receiving_ids_without_rebinding(self):
        from apps.rpg.companion_catalog import CompanionCatalogCollision, reconcile_companion_offers

        legacy = PetSpecies.objects.create(slug="saved-bat", name="Saved Bat", sprite_key="saved-bat")
        for item_type, species, metadata in [
            ("egg", self.species, {"species": "bat"}),
            ("egg", legacy, {"species": "meshtint-bat"}),
            ("food", self.species, {"species": "meshtint-bat"}),
        ]:
            with self.subTest(item_type=item_type, species=species.pk, metadata=metadata):
                self.egg.item_type, self.egg.pet_species, self.egg.metadata = item_type, species, metadata
                self.egg.save()
                before = ItemDefinition.objects.values().get(pk=self.egg.pk)
                with self.assertRaisesRegex(CompanionCatalogCollision, f"egg id={self.egg.pk}"):
                    reconcile_companion_offers(dry_run=True)
                with self.assertRaisesRegex(ContentPackError, f"egg id={self.egg.pk}"):
                    ContentPack("content/rpg/initial").load(stdout=StringIO(), dry_run=True)
                self.assertEqual(ItemDefinition.objects.values().get(pk=self.egg.pk), before)
                self.assertEqual(PetSpecies.objects.count(), 2)
                self.assertEqual(UserInventory.objects.get(user=self.user, item=self.egg).quantity, 1)

@override_settings(RPG_ASSET_SUPPORT_POLICY=None, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CanonicalChickEggTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "canonical-chick-child"}]).children[0]
        self.base = PotionType.objects.create(slug="base", name="Base")
        self.chick = PetSpecies.objects.create(slug="chick", sprite_key="cute-chick", name="Chick")
        self.chick.available_potions.add(self.base)
        self.egg = ItemDefinition.objects.create(
            slug="chick-egg", name="Chick Egg", item_type="egg", pet_species=self.chick,
            metadata={"species": "chick"},
        )
        self.potion = ItemDefinition.objects.create(
            slug="base-potion", name="Base Potion", item_type="potion", potion_type=self.base,
            metadata={"variant": "base"},
        )
        UserInventory.objects.create(user=self.child, item=self.egg, quantity=2)
        UserInventory.objects.create(user=self.child, item=self.potion, quantity=2)

    def test_untyped_display_name_alias_cannot_hatch_chick(self):
        self.egg.slug = "saved-chick-alias"
        self.egg.pet_species = None
        self.egg.metadata = {"species": "Chick"}
        self.egg.save()
        with self.assertRaises(ValueError):
            PetService.start_incubation(self.child, self.egg.pk, self.potion.pk, uuid4())
        self.assertFalse(item_is_available(self.egg))
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 2)
        self.assertFalse(UserPet.objects.filter(user=self.child).exists())

    def test_chick_requires_canonical_item_typed_identity_and_matching_metadata(self):
        for slug, metadata in [("chick-egg", {}), ("chick-egg", {"species": "wolf"}),
                               ("chick-egg", {"species": "Chick"}), ("alias-egg", {"species": "chick"})]:
            with self.subTest(slug=slug, metadata=metadata):
                self.egg.slug, self.egg.metadata = slug, metadata
                self.egg.save()
                self.assertFalse(item_is_available(self.egg))
                with self.assertRaises(ValueError):
                    PetService.start_incubation(self.child, self.egg.pk, self.potion.pk, uuid4())
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.egg).quantity, 2)

    def test_exact_retained_chick_still_hatches(self):
        self.assertTrue(item_is_available(self.egg))
        pet = _claim_test_incubation(self.child, self.egg.pk, self.potion.pk)
        self.assertEqual((pet.species_id, pet.potion_id, pet.growth_points), (self.chick.pk, self.base.pk, 0))
