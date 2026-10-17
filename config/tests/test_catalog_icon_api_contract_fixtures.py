"""Real catalog/drop/goal APIs expose presentation IDs after identity checks."""
from unittest.mock import patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, UserBadge
from apps.pets.models import PetSpecies, PotionType
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, ItemDefinition
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"], RPG_ASSET_SUPPORT_POLICY=None)
class CatalogIconApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family("Catalog image fixtures", family_id=71,
                             parents=[{"id": 6, "username": "catalog-image-parent"}],
                             children=[{"id": 7, "username": "catalog-image-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.fish = ItemDefinition.objects.create(id=81, slug="food-fish", name="Fish", item_type="food", icon="F", sprite_key="fish")
        self.cooked = ItemDefinition.objects.create(id=82, slug="food-fish-cooked", name="Cooked Fish", item_type="food", icon="C", sprite_key="fish")
        self.hidden = ItemDefinition.objects.create(id=83, slug="scholar-draught-ii", name="Scholar's Draught II", item_type="consumable", icon="S", metadata={"effect": "xp_boost", "duration_hours": 48})
        self.unmatched = ItemDefinition.objects.create(id=84, slug="custom-fish", name="Fish", item_type="food", icon="U", sprite_key="fish")
        self.base = PotionType.objects.create(id=85, slug="base", name="Base")
        self.chick = PetSpecies.objects.create(id=86, slug="chick", name="Chick", icon="C", sprite_key="cute-chick")
        self.chick.available_potions.add(self.base)
        self.definition = QuestDefinition.objects.create(id=91, name="Feather Collector", quest_type="collection", target_value=3,
                                                       duration_days=7, is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
        QuestRewardItem.objects.create(id=92, quest_definition=self.definition, item=self.fish, quantity=1)
        self.custom = QuestDefinition.objects.create(id=93, name="Feather Collector", quest_type="collection", target_value=3, is_system=False)
        DropLog.objects.create(id=94, user=self.child, item=self.cooked, trigger_type="clock_out")
        ChallengeEnrollment.objects.create(user=self.child, starts_at=shared.FIXED_NOW, timezone_name="America/Phoenix")
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ChallengeGoal, ChallengeOccurrence]):
                cursor.execute(sql)

    def test_bound_and_unbound_catalog_images_are_server_owned_wire_fields(self):
        self.client.force_authenticate(self.parent)
        items = self.assert_response_fixture(self.client.get("/api/items/catalog/"), "catalog-icons-items.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in items}, {
            81: "item-fish", 82: "item-fish-cooked", 83: "item-scholar-draught-ii", 84: None,
        })
        quests = self.assert_response_fixture(self.client.get("/api/quests/catalog/"), "catalog-icons-challenges.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in quests}, {91: "challenge-feather-collector", 93: None})
        self.assertEqual(quests[0]["reward_items"][0]["item_catalog_icon"], "item-fish")
        self.assert_response_fixture(self.client.get("/api/pets/species/catalog/"), "catalog-icons-species.json")
        create_goal(self.parent, self.child, {"name": self.definition.name, "metric": "count", "target": 3, "unit": "actions",
                                            "trigger_type": "chore_complete", "period": "this_week", "coin_reward": 0,
                                            "xp_reward": 0, "skill_tags": []})
        self.client.force_authenticate(self.child)
        drops = self.assert_response_fixture(self.client.get("/api/drops/recent/"), "catalog-icons-drops.json")
        self.assertEqual(drops[0]["item_catalog_icon"], "item-fish-cooked")
        self.assertEqual(drops[0]["item_type"], "food")
        self.assertIn("Adds 5 growth", drops[0]["item_effect_summary"])
        self.assertIsNone(drops[0]["salvage_coins"])
        self.assertEqual(next(row for row in items if row["id"] == self.fish.pk)["acquisition_sources"], [{
            "kind": "challenge", "name": "Feather Collector", "path": "/quests?tab=trials",
        }])
        goals = self.assert_response_fixture(self.client.get("/api/challenges/"), "catalog-icons-goals.json")
        self.assertEqual({row["origin"]: row["catalog_icon"] for row in goals["results"]}, {
            "catalog": "challenge-feather-collector", "parent": None,
        })

    def test_catalog_and_earned_badges_expose_base_coin_bonus_without_awarding_again(self):
        badge = Badge.objects.create(id=101, name="Fixture rare achievement", rarity="rare", criteria_type="first_project", xp_bonus=30)
        Badge.objects.create(id=102, name="Fixture honor badge", rarity="legendary", criteria_type="first_project", award_coins=False)
        UserBadge.objects.create(id=103, user=self.child, badge=badge)
        outsider = make_family("Other badge household", family_id=72, children=[{"id": 99, "username": "badge-fixture-outsider"}]).children[0]
        UserBadge.objects.create(id=104, user=outsider, badge=badge)
        coins_before = list(CoinLedger.objects.order_by("pk").values())
        self.client.force_authenticate(self.child)
        catalog = self.assert_response_fixture(self.client.get("/api/badges/"), "badges-rarity-bonuses.json")
        rows = {row["id"]: row for row in catalog["results"]}
        self.assertEqual(rows[101]["coin_bonus"], 35)
        self.assertEqual(rows[102]["coin_bonus"], 0)
        earned = self.assert_response_fixture(self.client.get("/api/badges/earned/"), "badges-earned-rarity-bonuses.json")
        self.assertEqual(earned["results"][0]["badge"]["coin_bonus"], 35)
        self.assertEqual([(row["id"], row["user"]) for row in earned["results"]], [(103, self.child.pk)])
        self.assertEqual(UserBadge.objects.filter(user=self.child).count(), 1)
        self.assertEqual(list(CoinLedger.objects.order_by("pk").values()), coins_before)
