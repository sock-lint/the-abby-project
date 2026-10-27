"""Real current-policy responses, including preserved unsupported ownership."""
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import yaml

from django.conf import settings
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, UserBadge, XP_THRESHOLDS
from apps.achievements.services import BadgeService, SkillService
from apps.pets.models import MountExpedition, PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, ItemDefinition, UserInventory
from config.tests.factories import make_family
from config.tests import test_api_contract_fixtures as shared


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class CatalogApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture
    pin_next_mount_identity = shared.SharedApiResponseFixtureTests.pin_next_mount_identity
    pin_next_hatched_pet_identity = shared.SharedApiResponseFixtureTests.pin_next_hatched_pet_identity
    pin_next_incubation_identity = shared.SharedApiResponseFixtureTests.pin_next_incubation_identity

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.child = make_family("Supported catalog", family_id=31, children=[{"id": 7, "username": "fixture-catalog-child"}]).children[0]
        self.client.force_authenticate(self.child)
        self.base = PotionType.objects.create(id=41, slug="base", name="Base", color_hex="#8B7355")
        self.chick = PetSpecies.objects.create(id=42, slug="chick", name="Chick", icon="C", sprite_key="cute-chick")
        self.chick.available_potions.add(self.base)
        self.cat = PetSpecies.objects.create(id=43, slug="cat", name="Cat", icon="K", sprite_key="cat")
        self.cat.available_potions.add(self.base)
        # The production codex contains 15 species identities, independently of
        # their 45 Base post-hatch artwork forms. This fixture explicitly authors
        # only Base compatibility; elemental-policy fixtures cover Fire/Ice.
        roster = json.loads((Path(settings.BASE_DIR) / "shared/catalog/companion-roster.json").read_text())
        species_content = yaml.safe_load((Path(settings.BASE_DIR) / "content/rpg/initial/pet_species.yaml").read_text())
        rarities = {entry["slug"]: entry.get("egg_rarity", "common") for entry in species_content["species"]}
        self.roster_species = []
        for index, family in enumerate(roster["families"]):
            species = PetSpecies.objects.create(
                id=142 + index, slug=family["species_slug"], name=family["name"],
                icon="🐾", sprite_key=family["sprite_key"], rarity=rarities[family["species_slug"]],
            )
            species.available_potions.add(self.base)
            self.roster_species.append(species)
        self.egg = ItemDefinition.objects.create(id=51, slug="cat-egg", name="Cat Egg", icon="E", item_type="egg", pet_species=self.cat)
        self.potion = ItemDefinition.objects.create(id=52, slug="base-potion", name="Base Potion", icon="P", item_type="potion", potion_type=self.base, metadata={"variant": "base"})
        self.accessory = ItemDefinition.objects.create(id=53, slug="accessory-crown", name="Crown", icon="A", item_type="cosmetic_pet_accessory")
        self.frame = ItemDefinition.objects.create(id=54, slug="frame-gold", name="Gold Frame", icon="G", item_type="cosmetic_frame", metadata={"border_color": "#abcdef"})
        UserPet.objects.create(id=61, user=self.child, species=self.chick, potion=self.base, name="Peep", is_active=True)
        UserPet.objects.create(id=62, user=self.child, species=self.cat, potion=self.base, name="Kit", growth_points=30)
        for pk, item in enumerate((self.egg, self.potion, self.accessory, self.frame), 71):
            UserInventory.objects.create(id=pk, user=self.child, item=item, quantity=1)

    def test_earned_badge_history_survives_unreachable_legacy_level(self):
        category = SkillCategory.objects.create(id=931, name="Fixture runtime levels")
        skill = Skill.objects.create(id=932, category=category, name="Fixture mastery practice")
        earned = Badge.objects.create(id=951, name="Retained earned level badge", description="Previously earned recognition",
            criteria_type="skill_level_reached", criteria_value={"level": max(XP_THRESHOLDS), "count": 1},
            xp_bonus=0, award_coins=False)
        self.assertEqual(SkillService.award_xp(self.child, skill, 1000000).level, max(XP_THRESHOLDS))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [earned])
        marker = UserBadge.objects.get(user=self.child, badge=earned)
        saved_marker = UserBadge.objects.values().get(pk=marker.pk)
        before = {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory,
        )}
        # Historical raw imports/edits may contain an invalid level. Reads retain
        # earned recognition without offering that unreachable goal to a child.
        Badge.objects.filter(pk=earned.pk).update(criteria_value={"level": max(XP_THRESHOLDS) + 1, "count": 1})
        Badge.objects.create(id=952, name="Hidden unearned level badge", description="Unreachable legacy goal",
            criteria_type="skill_level_reached", criteria_value={"level": max(XP_THRESHOLDS) + 1, "count": 1},
            xp_bonus=0, award_coins=False)
        Badge.objects.create(id=953, name="Reachable next level badge", description="Supported maximum-level goal",
            criteria_type="skill_level_reached", criteria_value={"level": max(XP_THRESHOLDS), "count": 1},
            xp_bonus=0, award_coins=False)
        self.assertEqual(UserBadge.objects.values().get(pk=marker.pk), saved_marker)
        self.assertEqual({model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory,
        )}, before)
        response = self.client.get("/api/badges/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()["results"]}
        self.assertEqual(set(rows), {951, 953})
        self.assertFalse(rows[951]["catalog_available"])
        self.assertTrue(rows[953]["catalog_available"])
        history = self.client.get("/api/badges/earned/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["results"][0]["badge"]["id"], earned.pk)
        self.assertFalse(history.json()["results"][0]["badge"]["catalog_available"])
        self.assertEqual(UserBadge.objects.values().get(pk=marker.pk), saved_marker)
        self.assertEqual({model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in (
            UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory,
        )}, before)
        self.assert_response_fixture(response, "badges-retained-unreachable-level.json")

    def test_native_reachable_legacy_level_goals_remain_visible_without_read_awards(self):
        from apps.achievements import criteria

        category = SkillCategory.objects.create(id=931, name="Fixture legacy levels")
        skill = Skill.objects.create(id=932, category=category, name="Fixture legacy practice")
        self.assertEqual(SkillService.award_xp(self.child, skill, 1000000).level, max(XP_THRESHOLDS))
        badges = []
        for pk, threshold in ((954, "2"), (955, 1.5), (956, 0), (958, False)):
            badge = Badge.objects.create(id=pk, name=f"Reachable legacy goal {pk}",
                description="Preserved native level conversion", criteria_type="skill_level_reached",
                criteria_value={"level": threshold, "count": 1}, xp_bonus=0, award_coins=False)
            self.assertTrue(criteria.check(self.child, badge))
            badges.append(badge)
        unreachable = Badge.objects.create(id=960, name="Unreachable legacy control",
            criteria_type="skill_level_reached", criteria_value={"level": max(XP_THRESHOLDS) + 0.9, "count": 1},
            xp_bonus=0, award_coins=False)
        self.assertFalse(criteria.check(self.child, unreachable))
        models = (UserBadge, SkillProgress, CoinLedger, DropLog, UserInventory)
        before = {model._meta.label_lower: list(model.objects.order_by("pk").values()) for model in models}
        response = self.client.get("/api/badges/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()["results"]}
        self.assertEqual(set(rows), {badge.pk for badge in badges})
        self.assertTrue(all(row["catalog_available"] for row in rows.values()))
        for badge in badges:
            self.assertEqual(rows[badge.pk]["criteria_value"], badge.criteria_value)
        self.assertEqual({model._meta.label_lower: list(model.objects.order_by("pk").values())
                          for model in models}, before)
        self.assert_response_fixture(response, "badges-reachable-legacy-levels.json")
        self.assertEqual(set(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"})), set(badges))
        self.assertEqual(BadgeService.evaluate_badges(self.child, scopes={"skill_xp"}), [])
        self.assertEqual(UserBadge.objects.filter(user=self.child).count(), len(badges))
        self.assertEqual(list(SkillProgress.objects.order_by("pk").values()), before["achievements.skillprogress"])
        self.assertEqual(list(CoinLedger.objects.order_by("pk").values()), before["rewards.coinledger"])

    def test_current_catalog_response(self):
        catalog = self.assert_response_fixture(self.client.get("/api/pets/codex/"), "pets-supported-catalog.json")
        self.assertEqual(len(catalog["species"]), 15)
        self.assertEqual({species["slug"] for species in catalog["species"]},
                         {"chick", *(species.slug for species in self.roster_species)})
        self.assertEqual([potion["slug"] for potion in catalog["potions"]], ["base"])
        for species in catalog["species"]:
            self.assertEqual(species["lifecycle_stages"], ["egg", "baby", "middle", "grown"])
            self.assertEqual([potion["slug"] for potion in species["available_potions"]], ["base"])
            self.assertEqual(species["available_potions"][0]["acquisition_challenges"], [])
        self.assertEqual({rarity: sum(species["rarity"] == rarity for species in catalog["species"])
                          for rarity in ("common", "uncommon", "rare", "epic", "legendary")},
                         {"common": 5, "uncommon": 5, "rare": 3, "epic": 1, "legendary": 1})

    def test_preserved_collection_responses(self):
        self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-preserved-collection.json")
        self.assert_response_fixture(self.client.get("/api/cosmetics/catalog/"), "cosmetics-supported-catalog.json")
        self.assert_response_fixture(self.client.get("/api/inventory/"), "items-preserved-inventory.json")

    def test_saved_elemental_mounts_share_species_launch_allowance(self):
        UserPet.objects.filter(pk=61).update(growth_points=100, evolved_to_mount=True)
        mounts = [UserMount.objects.create(id=81, user=self.child, species=self.chick, potion=self.base)]
        for potion_id, pet_id, mount_id, slug in ((44, 63, 82, "fire"), (45, 64, 83, "ice")):
            potion = PotionType.objects.create(id=potion_id, slug=slug, name=slug.title(), rarity="uncommon")
            UserPet.objects.create(id=pet_id, user=self.child, species=self.chick, potion=potion,
                                   growth_points=100, evolved_to_mount=True)
            mounts.append(UserMount.objects.create(id=mount_id, user=self.child, species=self.chick, potion=potion))
        MountExpedition.objects.create(
            id=91, mount=mounts[0], tier="short", status="claimed",
            started_at=shared.FIXED_NOW - timedelta(minutes=120), returns_at=shared.FIXED_NOW,
            claimed_at=shared.FIXED_NOW, loot={"coins": 0, "items": []},
        )
        body = self.assert_response_fixture(self.client.get("/api/pets/stable/"), "pets-shared-expedition-allowance.json")
        self.assertEqual(len(body["mounts"]), 3)
        mount_response = self.client.get("/api/mounts/")
        self.assertEqual(mount_response.status_code, 200)
        self.assertEqual([mount["id"] for mount in mount_response.json()], [81, 82, 83])
        self.assertEqual(mount_response.json(), body["mounts"])
        for mount in body["mounts"]:
            self.assertFalse(mount["expedition_available"])
            self.assertIsNotNone(mount["expedition_available_at"])
            self.assertGreater(mount["expedition_available_in_seconds"], 0)
        self.assertEqual({m["potion"]["slug"] for m in body["mounts"]}, {"base", "fire", "ice"})
        self.assertEqual(self.client.post("/api/mounts/82/expedition/", {"tier": "short"}, format="json").status_code, 400)

    def test_namespaced_roster_egg_hatches_one_base_baby_with_exact_family_identity(self):
        species = next(species for species in self.roster_species if species.slug == "meshtint-bat")
        egg = ItemDefinition.objects.create(
            id=91, slug="meshtint-bat-egg", name="Bat Egg", icon="🥚", item_type="egg",
            pet_species=species, rarity=species.rarity, metadata={"species": species.slug},
        )
        UserInventory.objects.create(id=91, user=self.child, item=egg, quantity=2)
        inventory = self.client.get("/api/inventory/")
        self.assertEqual(inventory.status_code, 200)
        owned_egg = next(entry["item"] for entry in inventory.json() if entry["item"]["id"] == egg.pk)
        self.assertTrue(owned_egg["catalog_available"])
        self.assertEqual(owned_egg["pet_species_slug"], species.slug)
        self.assertEqual(owned_egg["catalog_icon"], "bat-egg-portrait")
        self.assert_response_fixture(inventory, "inventory-roster-hatching.json")
        self.pin_next_hatched_pet_identity()
        self.pin_next_incubation_identity()
        incubation = self.assert_response_fixture(self.client.post(
            "/api/pets/incubations/", {"egg_item_id": egg.pk, "potion_item_id": self.potion.pk,
                                       "request_id": shared.INCUBATION_REQUEST_ID}, format="json",
        ), "pet-incubation-roster-start.json", status=201)["incubation"]
        saved_incubation = PetIncubation.objects.get(pk=incubation["id"])
        self.assertEqual((saved_incubation.ready_at - saved_incubation.started_at).total_seconds(), 86400)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 2)
        with patch("django.utils.timezone.now", return_value=saved_incubation.ready_at):
            body = self.assert_response_fixture(self.client.post(
                f"/api/pets/incubations/{incubation['id']}/hatch/", {}, format="json",
            ), "pet-incubation-roster-hatched.json", status=201)["pet"]
        self.assertEqual(body["species"]["slug"], "meshtint-bat")
        self.assertEqual(body["species"]["catalog_icon"], "bat-baby-portrait")
        self.assertEqual(body["potion"]["slug"], "base")
        self.assertEqual((body["rarity"], body["species"]["rarity"], body["potion"]["rarity"]),
                         ("uncommon", "uncommon", "common"))
        self.assertEqual((body["lifecycle_stage"], body["growth_points"], body["evolved_to_mount"]), ("baby", 0, False))
        self.assertTrue(body["catalog_available"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=egg).quantity, 1)
        self.assertFalse(UserInventory.objects.filter(user=self.child, item=self.potion).exists())
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 3)

    def test_bird_stages_retain_saved_species_inventory_and_legacy_collection(self):
        UserPet.objects.filter(pk=61).update(growth_points=35)
        # The older Cat mount stays owned and rendered by its own family.
        UserMount.objects.create(id=61, user=self.child, species=self.cat, potion=self.base)
        self.pin_next_mount_identity()
        food = ItemDefinition.objects.create(
            id=55, slug="food-birdseed", name="Birdseed", item_type="food", food_species=self.chick,
        )
        inventory = UserInventory.objects.create(id=81, user=self.child, item=food, quantity=5)
        fledgling = self.assert_response_fixture(self.client.post(
            "/api/pets/61/feed/", {"food_item_id": food.pk}, format="json",
        ), "pet-feed-fledgling.json")
        self.assertEqual(fledgling["evolution_stage"], "fledgling")
        self.assertFalse(fledgling["evolved"])
        self.assert_response_fixture(
            self.client.get("/api/pets/stable/"), "pets-stable-fledgling.json",
        )
        for _ in range(4):
            grown = self.client.post("/api/pets/61/feed/", {"food_item_id": food.pk}, format="json")
            self.assertEqual(grown.status_code, 200)
        bird = self.assert_response_fixture(grown, "pet-feed-bird.json")
        self.assertEqual(bird["evolution_stage"], "bird")
        self.assertTrue(bird["evolved"])
        stable = self.assert_response_fixture(
            self.client.get("/api/pets/stable/"), "pets-stable-bird.json",
        )
        self.assertEqual({row["id"] for row in stable["pets"]}, {61, 62})
        self.assertEqual({row["id"] for row in stable["mounts"]}, {61, bird["mount_id"]})
        self.assertFalse(UserInventory.objects.filter(pk=inventory.pk).exists())
        # Loading and repeated reads retain the confirmed stage; rendering has no writes.
        before = list(UserPet.objects.filter(user=self.child).values())
        self.assertEqual(self.client.get("/api/pets/stable/").json(), stable)
        self.assertEqual(list(UserPet.objects.filter(user=self.child).values()), before)

    def test_namespaced_roster_mounts_cannot_breed_or_change_owned_inventory(self):
        bat = next(species for species in self.roster_species if species.slug == "meshtint-bat")
        bee = next(species for species in self.roster_species if species.slug == "meshtint-bee")
        ItemDefinition.objects.create(
            id=91, slug="meshtint-bat-egg", name="Bat Egg", icon="🥚", item_type="egg",
            pet_species=bat, rarity=bat.rarity, metadata={"species": bat.slug},
        )
        mounts = [UserMount.objects.create(id=81 + index, user=self.child, species=species, potion=self.base)
                  for index, species in enumerate((bat, bee))]
        before = (
            list(UserInventory.objects.order_by("pk").values()),
            list(UserMount.objects.order_by("pk").values()),
            list(UserPet.objects.order_by("pk").values()),
        )
        response = self.client.post("/api/mounts/breed/", {
            "mount_a_id": mounts[0].pk, "mount_b_id": mounts[1].pk,
        }, format="json")
        self.assert_response_fixture(response, "mount-breed-retired.json", status=410)
        stable = self.client.get("/api/pets/stable/").json()
        self.assertFalse(stable["breeding_available"])
        self.assertEqual({row["id"] for row in stable["mounts"]}, {81, 82})
        for mount in stable["mounts"]:
            self.assertTrue(mount["catalog_available"])
            self.assertEqual((mount["can_breed"], mount["breeding_cooldown_seconds"]), (False, 0))
        self.assertEqual(before, (
            list(UserInventory.objects.order_by("pk").values()),
            list(UserMount.objects.order_by("pk").values()),
            list(UserPet.objects.order_by("pk").values()),
        ))

    def test_owned_appearance_inventory_routes_to_each_features_editor(self):
        cover = ItemDefinition.objects.create(
            id=55, slug="cover-vigil", name="Night Vigil", icon="T",
            item_type="cosmetic_theme", metadata={"theme": "vigil"},
        )
        UserInventory.objects.filter(user=self.child).exclude(item=self.frame).delete()
        UserInventory.objects.create(id=75, user=self.child, item=cover, quantity=1)
        body = self.assert_response_fixture(self.client.get("/api/inventory/"), "inventory-appearance.json")
        by_type = {row["item"]["item_type"]: row for row in body}
        self.assertEqual(by_type["cosmetic_theme"]["item"]["name"], "Twilight Meadow")
        self.assertEqual(by_type["cosmetic_theme"]["item"]["type_display"], "Color theme")
        cover.refresh_from_db()
        self.assertEqual(cover.name, "Night Vigil")
        self.assertEqual(by_type["cosmetic_frame"]["available_actions"][0]["to"], "/sigil")
        self.assertEqual(by_type["cosmetic_theme"]["available_actions"], [{
            "id": "equip", "label": "Change color theme", "to": "/settings#appearance",
        }])

    def test_unavailable_mutations_have_no_consumption_or_loss(self):
        self.assert_response_fixture(self.client.post("/api/pets/incubations/", {"egg_item_id": self.egg.pk, "potion_item_id": self.potion.pk, "request_id": shared.INCUBATION_REQUEST_ID}, format="json"), "pet-hatch-unavailable.json", status=400)
        self.assert_response_fixture(self.client.post("/api/character/equip/", {"item_id": self.accessory.pk}, format="json"), "cosmetic-equip-unavailable.json", status=400)
        self.assertEqual(UserPet.objects.filter(user=self.child).count(), 2)
        self.assertEqual(list(UserInventory.objects.filter(user=self.child).values_list("quantity", flat=True)), [1, 1, 1, 1])
