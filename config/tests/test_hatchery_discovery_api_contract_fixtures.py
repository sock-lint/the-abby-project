"""Real codex discovery responses separate current offers from saved attempts."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.achievements.models import SkillProgress
from apps.egg_discoveries.models import DiscoveryActivityCredit, DiscoveryRequest, DiscoverySearch, EggDiscovery, PracticeSession
from apps.pets.models import PetIncubation, PetSpecies, PotionType, UserMount, UserPet
from apps.quests.goals import _snapshot
from apps.quests.models import (
    ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence,
    ChallengePin, Quest, QuestDefinition, QuestParticipant, QuestRewardItem,
)
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition, UserInventory
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


PATHS = (
    (91, "Ember Nest", "chick", "fire", 5, 180),
    (92, "Frost Nest", "chick", "ice", 5, 180),
    (93, "Ember Trail", "meshtint-wolf", "fire", 20, 180),
    (94, "Frost Trail", "meshtint-wolf", "ice", 20, 180),
    (95, "Ember Grove", "meshtint-mushroom", "fire", 10, 180),
    (96, "Frost Grove", "meshtint-mushroom", "ice", 10, 180),
    (97, "Ember Summit", "meshtint-dragon", "fire", 50, 365),
    (98, "Frost Summit", "meshtint-dragon", "ice", 50, 365),
)


@override_settings(
    ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None, EGG_DISCOVERY_ENABLED=False,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class HatcheryDiscoveryApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        cache.clear()
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        household = make_family(
            "Synthetic hatchery discovery", family_id=91,
            parents=[{"id": 6, "username": "hatchery-discovery-parent"}],
            children=[{"id": 7, "username": "hatchery-discovery-child"},
                      {"id": 8, "username": "hatchery-discovery-sibling"}],
        )
        self.parent = household.parents[0]
        self.child, self.sibling = household.children
        self.outsider = make_family(
            "Other synthetic hatchery discovery", family_id=92,
            children=[{"id": 99, "username": "hatchery-discovery-outsider"}],
        ).children[0]
        self.potions = {}
        self.ingredients = {}
        for potion_id, slug, color in ((41, "base", "#8B7355"), (42, "fire", "#F97316"),
                                       (43, "ice", "#38BDF8")):
            potion = PotionType.objects.create(
                id=potion_id, slug=slug, name=slug.title(), color_hex=color,
                rarity="common" if slug == "base" else "uncommon",
            )
            self.potions[slug] = potion
            self.ingredients[slug] = ItemDefinition.objects.create(
                id=potion_id + 10, slug=f"{slug}-potion", name=f"{slug.title()} Potion",
                item_type="potion", potion_type=potion, metadata={"variant": slug},
                rarity=potion.rarity, icon="P",
            )
        self.species = {}
        self.eggs = {}
        for species_id, slug, name, sprite in (
            (61, "chick", "Chick", "cute-chick"),
            (62, "meshtint-wolf", "Wolf", "meshtint-wolf"),
            (63, "meshtint-mushroom", "Mushroom", "meshtint-mushroom"),
            (64, "meshtint-dragon", "Dragon", "meshtint-dragon"),
        ):
            species = PetSpecies.objects.create(
                id=species_id, slug=slug, name=name, sprite_key=sprite, icon="S",
            )
            species.available_potions.add(*self.potions.values())
            self.species[slug] = species
            self.eggs[slug] = ItemDefinition.objects.create(
                id=species_id + 10, slug=f"{slug}-egg",
                name="Wolf Pup Egg" if slug == "meshtint-wolf" else f"{name} Egg",
                item_type="egg", pet_species=species, metadata={"species": slug}, icon="E",
            )
        self.definitions = {}
        for definition_id, name, species, potion, target, days in PATHS:
            self.add_definition(definition_id, name, species, potion, target, days)
        self.add_definition(99, "Reading Companion", "chick", "base", 2, None)
        self.client.force_authenticate(self.child)

    def add_definition(self, definition_id, name, species, potion, target, days):
        definition = QuestDefinition.objects.create(
            id=definition_id, name=name, description="Synthetic guaranteed hatch pair.",
            quest_type="collection", target_value=target, duration_days=days,
            is_system=True, is_repeatable=False, coin_reward=0, xp_reward=0,
            trigger_filter={"allowed_triggers": ["reading_logged" if days is None else "chore_complete"]},
        )
        self.definitions[name] = definition
        for reward_id, item in ((definition_id * 2, self.eggs[species]),
                                (definition_id * 2 + 1, self.ingredients[potion])):
            QuestRewardItem.objects.create(
                id=reward_id, quest_definition=definition, item=item, quantity=1,
            )
        return definition

    def saved_attempt(self, name, index, *, user=None, age=10, status="active",
                      progress=3, target=None, frozen_name=None):
        definition = self.definitions[name]
        user = user or self.child
        start = shared.FIXED_NOW - timedelta(days=age)
        end = start + timedelta(days=definition.duration_days) if definition.duration_days else None
        goal = ChallengeGoal.objects.create(
            id=300 + index, user=user, family=user.family, is_catalog=True,
            catalog_definition=definition, name=frozen_name or definition.name,
            description="Synthetic accepted challenge promise.", metric="count",
            target=Decimal(target or definition.target_value), unit="actions",
            trigger_filter=definition.trigger_filter, timezone_name="America/Phoenix",
            starts_at=start, ends_at=end, coin_reward=0, xp_reward=0,
            reward_items=[{"item_id": reward.item_id, "quantity": reward.quantity}
                          for reward in definition.reward_items.order_by("pk")],
        )
        return ChallengeOccurrence.objects.create(
            id=400 + index, goal=goal, starts_at=start, ends_at=end,
            snapshot=_snapshot(goal), status=status, progress=progress,
            completed_at=shared.FIXED_NOW - timedelta(days=1) if status == "completed" else None,
            awarded_at=shared.FIXED_NOW - timedelta(days=1) if status == "completed" else None,
        )

    def state(self):
        models = (
            ChallengeActivity, ChallengeContribution, ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence,
            ChallengePin, Quest, QuestParticipant, CoinLedger, SkillProgress, DropLog,
            CharacterProfile, UserInventory, UserPet, UserMount, PetIncubation,
            DiscoveryActivityCredit, DiscoveryRequest, DiscoverySearch, EggDiscovery, PracticeSession,
        )
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in models}

    @staticmethod
    def discoveries(body):
        return {(species["slug"], potion["slug"]): potion["acquisition_challenges"]
                for species in body["species"] for potion in species["available_potions"]}

    def test_codex_fixture_has_whole_offers_and_frozen_active_expired_completed_attempts(self):
        active = self.saved_attempt("Ember Grove", 1, target=8, frozen_name="My saved Ember Grove")
        expired = self.saved_attempt("Frost Grove", 2, age=181, progress=4)
        completed = self.saved_attempt("Ember Summit", 3, status="completed", progress=50)
        untimed_attempt = self.saved_attempt("Reading Companion", 6, age=90, progress=1)
        # Another child's attempt never supplies this child's saved status.
        self.saved_attempt("Ember Grove", 4, user=self.sibling, frozen_name="Sibling-only saved Grove")
        self.saved_attempt("Frost Summit", 5, user=self.outsider, frozen_name="Other-household saved Summit")
        before = self.state()
        body = self.assert_response_fixture(
            self.client.get("/api/pets/codex/"), "pets-hatchery-discovery.json",
        )
        self.assertIs(body["egg_discovery_enabled"], False)
        self.assertTrue(all(potion["acquisition_discovery"] is None for species in body["species"]
                            for potion in species["available_potions"]))
        self.assertTrue(all("acquisition_challenges" not in potion for potion in body["potions"]))
        choices = self.discoveries(body)
        for definition_id, name, species, potion, target, days in PATHS:
            with self.subTest(name=name):
                self.assertEqual(len(choices[species, potion]), 1)
                offer = choices[species, potion][0]
                self.assertEqual(set(offer), {
                    "definition_id", "name", "offer_available", "target", "duration_days", "attempt", "path",
                })
                self.assertEqual((offer["definition_id"], offer["name"], offer["target"], offer["duration_days"]),
                                 (definition_id, name, str(target), days))
                self.assertIs(type(offer["offer_available"]), bool)
                self.assertEqual(offer["path"], (
                    f"/quests?tab=trials&goal=goal%3A{offer['attempt']['id'].split(':')[1]}"
                    if offer["attempt"] else "/quests?tab=trials"
                ))
                rewards = list(self.definitions[name].reward_items.select_related("item"))
                self.assertEqual({reward.item_id for reward in rewards},
                                 {self.eggs[species].pk, self.ingredients[potion].pk})
                self.assertEqual([reward.quantity for reward in rewards], [1, 1])
                self.assertEqual(self.eggs[species].pet_species_id, self.species[species].pk)
                self.assertEqual(self.ingredients[potion].potion_type_id, self.potions[potion].pk)
        active_offer = choices["meshtint-mushroom", "fire"][0]
        self.assertEqual(active_offer["attempt"], {
            "id": f"goal:{active.pk}", "name": "My saved Ember Grove", "status": "active",
            "progress": "3", "target": "8", "ends_at": active.ends_at.isoformat(), "retry_available": False,
        })
        expired_offer = choices["meshtint-mushroom", "ice"][0]
        self.assertEqual(expired_offer["attempt"], {
            "id": f"goal:{expired.pk}", "name": "Frost Grove", "status": "expired",
            "progress": "4", "target": "10", "ends_at": expired.ends_at.isoformat(), "retry_available": True,
        })
        completed_offer = choices["meshtint-dragon", "fire"][0]
        self.assertEqual(completed_offer["attempt"], {
            "id": f"goal:{completed.pk}", "name": "Ember Summit", "status": "completed",
            "progress": "50", "target": "50", "ends_at": completed.ends_at.isoformat(), "retry_available": False,
        })
        self.assertFalse(completed_offer["offer_available"])
        new_offer = choices["meshtint-dragon", "ice"][0]
        self.assertTrue(new_offer["offer_available"])
        self.assertIsNone(new_offer["attempt"])
        untimed = choices["chick", "base"][0]
        self.assertEqual((untimed["name"], untimed["target"], untimed["duration_days"]),
                         ("Reading Companion", "2", None))
        self.assertEqual(untimed["attempt"], {
            "id": f"goal:{untimed_attempt.pk}", "name": "Reading Companion", "status": "active",
            "progress": "1", "target": "2", "ends_at": None, "retry_available": False,
        })
        self.assertTrue(untimed["offer_available"])
        for species in ("meshtint-wolf", "meshtint-mushroom", "meshtint-dragon"):
            self.assertEqual(choices[species, "base"], [])
        self.assertNotIn("Sibling-only", str(body))
        self.assertNotIn("Other-household", str(body))
        self.assertEqual(self.client.get("/api/pets/codex/").json(), body)
        # Child-selected user IDs cannot inspect another account's discovery.
        self.assertEqual(self.client.get("/api/pets/codex/", {"user_id": self.outsider.pk}).json(), body)
        self.assertEqual(self.state(), before)

    def test_parent_catalog_keeps_ordinary_potion_shape_and_does_not_enroll(self):
        self.client.force_authenticate(self.parent)
        before = self.state()
        response = self.client.get("/api/pets/species/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 4)
        for species in response.json():
            for potion in species["available_potions"]:
                self.assertEqual(set(potion), {"id", "slug", "name", "color_hex", "rarity"})
        self.assertEqual(self.state(), before)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get("/api/pets/species/catalog/").status_code, 403)

    @override_settings(EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={})
    def test_enabled_codex_fixture_preserves_earlier_promise_and_exact_discovery_choices_without_writes(self):
        active = self.saved_attempt("Ember Grove", 1, target=8, frozen_name="My earlier Ember Grove")
        # A random supported egg used to be a possible path. Discovery now
        # owns new collection; the accepted occurrence remains fulfillable.
        self.species["meshtint-dragon"].rarity = "rare"
        self.species["meshtint-dragon"].save(update_fields=["rarity"])
        ItemDefinition.objects.create(
            id=81, slug="discovery-common-food", name="Discovery Common Food",
            item_type="food", rarity="common", icon="F",
        )
        before = self.state()
        with CaptureQueriesContext(connection) as queries:
            body = self.assert_response_fixture(
                self.client.get("/api/pets/codex/"), "codex-discovery-enabled.json",
            )
        writes = [row["sql"] for row in queries if row["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE"),
        )]
        self.assertEqual(writes, [])
        self.assertIs(body["egg_discovery_enabled"], True)
        potions = {(species["slug"], potion["slug"]): potion
                   for species in body["species"] for potion in species["available_potions"]}
        ordinary = potions["chick", "base"]
        self.assertEqual(ordinary["acquisition_discovery"], {
            "key": "chick-egg:base", "path": "/quests?tab=trials", "name": "Chick Egg · Base",
            "tier": "ordinary", "eligible": True, "unavailable_reason": None,
        })
        self.assertEqual(ordinary["acquisition_challenges"], [])
        rare = potions["meshtint-dragon", "base"]
        self.assertEqual(rare["acquisition_discovery"], {
            "key": "meshtint-dragon-egg:base", "path": "/quests?tab=trials", "name": "Dragon Egg · Base",
            "tier": "rare", "eligible": False,
            "unavailable_reason": "Hatch two different companions to unlock rare discoveries.",
        })
        self.assertEqual(rare["acquisition_challenges"], [])
        earlier = potions["meshtint-mushroom", "fire"]["acquisition_challenges"]
        self.assertEqual(len(earlier), 1)
        self.assertFalse(earlier[0]["offer_available"])
        self.assertEqual(earlier[0]["attempt"], {
            "id": f"goal:{active.pk}", "name": "My earlier Ember Grove", "status": "active",
            "progress": "3", "target": "8", "ends_at": active.ends_at.isoformat(), "retry_available": False,
        })
        self.assertEqual(sum(len(potion["acquisition_challenges"]) for potion in potions.values()), 1)
        self.assertTrue(all(potion["acquisition_discovery"] is not None for potion in potions.values()))
        self.assertEqual(self.client.get("/api/pets/codex/").json(), body)
        self.assertEqual(self.client.get("/api/pets/codex/", {"user_id": self.outsider.pk}).json(), body)
        self.assertEqual(self.state(), before)

    def test_codex_authentication_still_precedes_discovery(self):
        before = self.state()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get("/api/pets/codex/").status_code, 401)
        self.assertEqual(self.state(), before)

    @override_settings(EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={})
    def test_enabled_challenge_fixture_marks_retained_promises_without_new_enrollment_or_payout(self):
        active = self.saved_attempt("Ember Grove", 1, target=8, frozen_name="My earlier Ember Grove")
        ChallengeEnrollment.objects.create(
            user=self.child, starts_at=shared.FIXED_NOW - timedelta(days=90), timezone_name="America/Phoenix",
        )
        ChallengePin.objects.create(user=self.child, occurrence=active)
        before = self.state()
        with CaptureQueriesContext(connection) as queries:
            body = self.assert_response_fixture(
                self.client.get("/api/challenges/"), "challenge-discovery-retained-promises.json",
            )
        self.assertEqual(len(body["results"]), 1)
        row = body["results"][0]
        self.assertEqual((row["id"], row["name"], row["progress"], row["target"], row["status"]),
                         (f"goal:{active.pk}", "My earlier Ember Grove", "3", "8", "active"))
        self.assertIs(row["legacy_egg_promise"], True)
        self.assertIs(row["pinned"], True)
        self.assertEqual({item["item_id"] for item in row["rewards"]["items"]},
                         {self.eggs["meshtint-mushroom"].pk, self.ingredients["fire"].pk})
        self.assertEqual(row["reward_receipt"]["status"], "pending")
        self.assertEqual(body["locked_catalog"], [])
        self.assertEqual(body["recent_receipts"], [])
        self.assertEqual([query["sql"] for query in queries if query["sql"].lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "REPLACE"),
        )], [])
        self.assertEqual(self.client.get("/api/challenges/").json(), body)
        self.assertEqual(self.state(), before)

    @override_settings(EGG_DISCOVERY_ENABLED=True, EGG_DISCOVERY_SEASONS={})
    def test_enabled_locked_milestone_fixture_exposes_exact_hatch_alternative_without_enrolling(self):
        target = QuestDefinition.objects.create(
            id=100, name="Reading Voyager", description="Synthetic future reading milestone.",
            quest_type="collection", target_value=20, duration_days=84, is_system=True,
            prerequisite_quest=self.definitions["Reading Companion"],
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        ChallengeEnrollment.objects.create(
            user=self.child, starts_at=shared.FIXED_NOW - timedelta(days=90), timezone_name="America/Phoenix",
        )
        ChallengePin.objects.create(user=self.child)
        before = self.state()
        body = self.assert_response_fixture(
            self.client.get("/api/challenges/"), "challenge-discovery-locked-milestone.json",
        )
        self.assertEqual(body["results"], [])
        self.assertEqual([row["id"] for row in body["locked_catalog"]], [target.pk])
        eligibility = body["locked_catalog"][0]["milestone_eligibility"]
        self.assertIs(eligibility["unlocked"], False)
        self.assertEqual(eligibility["requirements"], [{
            "kind": "challenge", "met": False,
            "description": "Complete Reading Companion, or hatch Base Chick.",
        }])
        self.assertEqual(eligibility["prerequisite_hatch_pairs"], [{
            "species_id": self.species["chick"].pk, "potion_id": self.potions["base"].pk,
            "species_name": "Chick", "potion_name": "Base",
        }])
        self.assertEqual(self.client.get("/api/challenges/").json(), body)
        self.assertEqual(self.state(), before)
