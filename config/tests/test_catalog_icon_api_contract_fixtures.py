"""Real catalog/drop/goal APIs expose presentation IDs after identity checks."""
from unittest.mock import patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress, Subject, UserBadge
from apps.pets.models import PetSpecies, PotionType
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeEnrollment, ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem
from apps.rewards.models import CoinLedger
from apps.rpg.models import DropLog, ItemDefinition
from apps.rpg.models import CharacterProfile, UserInventory
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
        self.custom = QuestDefinition.objects.create(id=93, name="Feather Collector", quest_type="collection", target_value=3, is_system=False, created_by=self.parent)
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

@override_settings(ALLOWED_HOSTS=["testserver"], PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ArtworkApiResponseFixtureTests(APITestCase):
    """Real artwork projections preserve progress, rewards and custom content."""
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family("Artwork fixtures", family_id=72, children=[{
            "id": 7, "username": "artwork-fixture-child", "display_name": "Artwork Child",
        }])
        self.child = family.children[0]
        self.client.force_authenticate(self.child)
        self.category = SkillCategory.objects.create(id=101, name="Coding", icon="CODE", color="#123456")
        other = SkillCategory.objects.create(id=102, name="Custom Coding", icon="CUSTOM")
        self.subject = Subject.objects.create(id=201, category=self.category, name="Languages & Apps", icon="APPS")
        custom_subject = Subject.objects.create(id=202, category=other, name=self.subject.name, icon="ALT")
        self.skill = Skill.objects.create(id=301, category=self.category, subject=self.subject, name="Python", icon="PYTHON")
        Skill.objects.create(id=302, category=other, subject=custom_subject, name="Python", icon="OTHER", is_locked_by_default=True)
        SkillProgress.objects.create(id=401, user=self.child, skill=self.skill, xp_points=150, level=1)
        self.badge = Badge.objects.create(id=501, name="10-Hour Club", icon="TEN", description="Synthetic ten-hour badge",
                                          criteria_type="hours_worked", criteria_value={"hours": 10}, xp_bonus=25)
        Badge.objects.create(id=502, name="25-Hour Club", icon="CUSTOM BADGE", description="Synthetic changed criterion",
                             criteria_type="hours_worked", criteria_value={"hours": 999}, rarity="rare")
        UserBadge.objects.create(id=601, user=self.child, badge=self.badge)
        # Update in place so the wire identity is stable even after other tests.
        CharacterProfile.objects.filter(user=self.child).update(id=701, active_trophy_badge=self.badge)

    @staticmethod
    def saved_gameplay():
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in (Badge, SkillCategory, Subject, Skill, SkillProgress, UserBadge,
                              CharacterProfile, CoinLedger, UserInventory)}

    def test_catalog_tree_progress_summary_trophy_and_dashboard_preserve_artwork_identity(self):
        before = self.saved_gameplay()
        categories = self.assert_response_fixture(self.client.get("/api/categories/"), "artwork-categories.json")
        self.assertEqual({row["name"]: row["catalog_icon"] for row in categories["results"]},
                         {"Coding": "category-coding", "Custom Coding": None})
        subjects = self.assert_response_fixture(self.client.get("/api/subjects/"), "artwork-subjects.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in subjects["results"]},
                         {201: "subject-coding-languages-apps", 202: None})
        self.assertEqual(subjects["results"][0]["category_name"], "Coding")
        skills = self.assert_response_fixture(self.client.get("/api/skills/"), "artwork-skills.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in skills["results"]}, {301: "skill-coding-python", 302: None})
        self.assertTrue(skills["results"][1]["is_locked_by_default"])
        tree = self.assert_response_fixture(self.client.get("/api/skills/tree/101/"), "artwork-tree.json")
        self.assertEqual(tree["category"]["catalog_icon"], "category-coding")
        self.assertEqual(tree["subjects"][0]["catalog_icon"], "subject-coding-languages-apps")
        self.assertEqual(tree["subjects"][0]["skills"][0]["catalog_icon"], "skill-coding-python")
        self.assertEqual(tree["subjects"][0]["skills"][0]["xp_points"], 150)
        progress = self.assert_response_fixture(self.client.get("/api/skill-progress/"), "artwork-progress.json")
        self.assertEqual(progress["results"][0]["skill_catalog_icon"], "skill-coding-python")
        badges = self.assert_response_fixture(self.client.get("/api/badges/"), "artwork-badges.json")
        self.assertEqual({row["id"]: row["catalog_icon"] for row in badges["results"]}, {501: "badge-10-hour-club", 502: None})
        summary = self.assert_response_fixture(self.client.get("/api/achievements/summary/"), "artwork-summary.json")
        self.assertEqual(summary["badges_earned"][0]["badge"]["catalog_icon"], "badge-10-hour-club")
        self.assertEqual(summary["skill_categories"]["Coding"]["catalog_icon"], "category-coding")
        character = self.assert_response_fixture(self.client.get("/api/character/"), "artwork-character.json")
        self.assertEqual(character["active_trophy_badge"]["catalog_icon"], "badge-10-hour-club")
        dashboard = self.assert_response_fixture(self.client.get("/api/dashboard/"), "artwork-dashboard.json")
        self.assertEqual(dashboard["recent_badges"][0]["badge__catalog_icon"], "badge-10-hour-club")
        self.assertEqual(self.saved_gameplay(), before)
