"""Availability reads scale with requests, while preserving saved collections."""

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.achievements.models import Badge, UserBadge
from apps.pets.models import PetSpecies, PotionType, UserMount, UserPet
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests.factories import make_family


def catalog_policy(species):
    return {
        "schema_version": 1,
        "pets": [
            {"species_slug": row.slug, "sprite_key": row.sprite_key, "potion_slugs": ["base"]}
            for row in species
        ],
        "potion_slugs": ["base"],
        "disabled_item_types": ["cosmetic_pet_accessory"],
    }


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BadgeAvailabilityQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        family = make_family(
            "Badge readers",
            parents=[{"username": "badge-parent"}, {"username": "badge-staff", "is_staff": True}],
            children=[{"username": "badge-child"}, {"username": "badge-sibling"}],
        )
        cls.child, cls.sibling = family.children
        cls.parent, cls.staff = family.parents
        cls.other = make_family("Other badge readers", children=[{"username": "badge-other"}]).children[0]
        cls.base = PotionType.objects.create(slug="base", name="Base")
        cls.fire = PotionType.objects.create(slug="fire", name="Fire")
        cls.supported = PetSpecies.objects.create(slug="supported", name="Supported", sprite_key="supported")
        cls.supported.available_potions.add(cls.base)
        cls.legacy = PetSpecies.objects.create(slug="legacy", name="Legacy", sprite_key="legacy")
        cls.frame = ItemDefinition.objects.create(slug="frame", name="Frame", item_type="cosmetic_frame")
        cls.accessory = ItemDefinition.objects.create(slug="accessory", name="Accessory", item_type="cosmetic_pet_accessory")
        cls.fire_item = ItemDefinition.objects.create(slug="fire-potion", name="Fire potion", item_type="potion", potion_type=cls.fire)

    def setUp(self):
        self.client = APIClient()
        self.policy = self.settings(RPG_ASSET_SUPPORT_POLICY=catalog_policy([self.supported]))
        self.policy.enable()
        self.addCleanup(self.policy.disable)
        self.client.force_authenticate(self.child)

    def badge(self, kind, criteria=None, name=None):
        return Badge.objects.create(
            name=name or f"{kind}-{Badge.objects.count()}", criteria_type=kind,
            criteria_value=criteria if criteria is not None else {"count": 1},
        )

    def catalog(self, user=None):
        if user is not None:
            self.client.force_authenticate(user)
        response = self.client.get("/api/badges/")
        self.assertEqual(response.status_code, 200)
        return {row["id"]: row for row in response.json()["results"]}

    def count_catalog_queries(self, user):
        self.client.force_authenticate(user)
        with CaptureQueriesContext(connection) as queries:
            self.catalog()
        return len(queries)

    def add_goal_ladder(self):
        for kind in ("pets_hatched", "pet_species_owned", "mounts_evolved", "full_potion_shelf", "cosmetic_full_set"):
            self.badge(kind)
        self.badge("cosmetic_set_owned", {"slugs": [self.frame.slug, self.accessory.slug]})

    def test_catalog_queries_do_not_grow_with_collectible_badge_ladders(self):
        self.add_goal_ladder()
        small = {user.pk: self.count_catalog_queries(user) for user in (self.child, self.staff)}
        self.add_goal_ladder()
        self.add_goal_ladder()
        for user in (self.child, self.staff):
            with self.subTest(role=user.role, staff=user.is_staff):
                large = self.count_catalog_queries(user)
                self.assertLessEqual(large, small[user.pk] + 1, f"Badge growth: {small[user.pk]} -> {large} queries")

    def test_catalog_queries_do_not_grow_with_supported_species(self):
        self.badge("pets_hatched")
        small = self.count_catalog_queries(self.child)
        extra = [PetSpecies.objects.create(slug=f"extra-{i}", name=f"Extra {i}", sprite_key=f"extra-{i}") for i in range(6)]
        for species in extra:
            species.available_potions.add(self.base)
        with override_settings(RPG_ASSET_SUPPORT_POLICY=catalog_policy([self.supported, *extra])):
            large = self.count_catalog_queries(self.child)
        self.assertLessEqual(large, small + 1, f"Species growth: {small} -> {large} queries")

    def test_earned_summary_queries_do_not_grow_with_collectible_badges(self):
        badge = self.badge("pet_species_owned")
        UserBadge.objects.create(user=self.child, badge=badge)
        with CaptureQueriesContext(connection) as queries:
            first = self.client.get("/api/achievements/summary/")
        self.assertEqual(first.status_code, 200)
        small = len(queries)
        for _ in range(6):
            UserBadge.objects.create(user=self.child, badge=self.badge("pet_species_owned"))
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/achievements/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["badges_earned"]), 7)
        self.assertLessEqual(len(queries), small + 1, f"Earned growth: {small} -> {len(queries)} queries")

    def test_saved_progress_and_earned_badges_remain_user_scoped(self):
        pets = self.badge("pets_hatched", {"count": 2})
        species = self.badge("pet_species_owned", {"count": 2})
        mounts = self.badge("mounts_evolved", {"count": 3})
        unreachable = self.badge("pets_hatched", {"count": 20})
        UserPet.objects.create(user=self.child, species=self.legacy, potion=self.fire)
        UserMount.objects.create(user=self.child, species=self.legacy, potion=self.base)
        UserBadge.objects.create(user=self.child, badge=unreachable)
        mine = self.catalog()
        self.assertTrue(all(mine[badge.pk]["catalog_available"] for badge in (pets, species, mounts)))
        self.assertFalse(mine[unreachable.pk]["catalog_available"])
        for user in (self.sibling, self.parent, self.other):
            with self.subTest(user=user.username):
                self.assertTrue({pets.pk, species.pk, mounts.pk, unreachable.pk}.isdisjoint(self.catalog(user)))
        staff = self.catalog(self.staff)
        self.assertTrue(all(badge.pk in staff for badge in (pets, species, mounts, unreachable)))
        self.assertTrue(all(not staff[badge.pk]["catalog_available"] for badge in (pets, species, mounts, unreachable)))

    def test_inventory_and_accessory_changes_are_fresh_on_next_request(self):
        shelf = self.badge("full_potion_shelf")
        full_set = self.badge("cosmetic_full_set")
        named_set = self.badge("cosmetic_set_owned", {"slugs": [self.frame.slug, self.accessory.slug]})
        empty_set = self.badge("cosmetic_set_owned", {"slugs": []})
        missing_set = self.badge("cosmetic_set_owned", {"slugs": ["missing"]})
        self.assertEqual(self.catalog(), {})
        fire_owned = UserInventory.objects.create(user=self.child, item=self.fire_item, quantity=1)
        accessory_owned = UserInventory.objects.create(user=self.child, item=self.accessory, quantity=1)
        CharacterProfile.objects.filter(user=self.child).update(active_pet_accessory=self.accessory)
        updated = self.catalog()
        self.assertEqual(set(updated), {shelf.pk, full_set.pk, named_set.pk})
        self.assertTrue(all(row["catalog_available"] for row in updated.values()))
        self.assertEqual(self.catalog(self.sibling), {})
        fire_owned.quantity = accessory_owned.quantity = 0
        fire_owned.save(update_fields=["quantity"])
        accessory_owned.save(update_fields=["quantity"])
        CharacterProfile.objects.filter(user=self.child).update(active_pet_accessory=None)
        self.assertEqual(self.catalog(self.child), {})
        self.assertTrue({empty_set.pk, missing_set.pk}.isdisjoint(updated))

    def test_compatibility_empty_legacy_and_disjoint_relations_keep_distinct_capacities(self):
        unrestricted = PetSpecies.objects.create(slug="unrestricted", name="Unrestricted", sprite_key="unrestricted")
        incompatible = PetSpecies.objects.create(slug="incompatible", name="Incompatible", sprite_key="incompatible")
        incompatible.available_potions.add(self.fire)
        two = self.badge("pets_hatched", {"count": 2})
        three = self.badge("pets_hatched", {"count": 3})
        with override_settings(RPG_ASSET_SUPPORT_POLICY=catalog_policy([self.supported, unrestricted, incompatible])):
            rows = self.catalog()
        self.assertIn(two.pk, rows)
        self.assertNotIn(three.pk, rows)

    def test_later_pet_catalog_and_ownership_changes_are_not_cached_on_user(self):
        from apps.achievements.availability import badge_goal_is_available

        badge = self.badge("pets_hatched", {"count": 2})
        self.assertFalse(badge_goal_is_available(badge, self.child))
        self.assertNotIn(badge.pk, self.catalog())
        saved = UserPet.objects.create(user=self.child, species=self.legacy, potion=self.fire)
        self.assertTrue(badge_goal_is_available(badge, self.child))
        self.assertTrue(self.catalog()[badge.pk]["catalog_available"])
        saved.delete()
        self.assertFalse(badge_goal_is_available(badge, self.child))
        self.assertNotIn(badge.pk, self.catalog())
        with override_settings(RPG_ASSET_SUPPORT_POLICY=catalog_policy([self.supported, self.legacy])):
            self.assertTrue(badge_goal_is_available(badge, self.child))
            self.assertTrue(self.catalog()[badge.pk]["catalog_available"])
        self.assertFalse(badge_goal_is_available(badge, self.child))

    def test_typed_collectible_items_in_named_sets_keep_policy_and_ownership(self):
        supported_egg = ItemDefinition.objects.create(
            slug="supported-egg", name="Supported egg", item_type="egg", pet_species=self.supported,
        )
        legacy_egg = ItemDefinition.objects.create(
            slug="legacy-egg", name="Legacy egg", item_type="egg", pet_species=self.legacy,
        )
        supported = self.badge("cosmetic_set_owned", {"slugs": [supported_egg.slug, self.frame.slug]})
        blocked = self.badge("cosmetic_set_owned", {"slugs": [legacy_egg.slug, self.fire_item.slug]})
        self.assertEqual(set(self.catalog()), {supported.pk})
        UserInventory.objects.create(user=self.child, item=legacy_egg, quantity=1)
        UserInventory.objects.create(user=self.child, item=self.fire_item, quantity=1)
        self.assertEqual(set(self.catalog()), {supported.pk, blocked.pk})
        self.assertEqual(set(self.catalog(self.sibling)), {supported.pk})
