"""Deploy-time seeding must preserve household offers and ambiguous links."""
from io import StringIO
from pathlib import Path
import tempfile

import yaml
from django.core.management import call_command
from django.test import TestCase

from apps.families.models import Family
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.rewards.models import Reward
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.publication import preview_content_pack, publish_content_pack
from apps.rpg.models import DropTable, ItemDefinition
from config.tests.factories import make_family


class StartupLoaderSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.default_family = Family.objects.get(slug="default-family")
        cls.other_family = make_family("Another household").family

    def reload(self):
        output = StringIO()
        call_command("loadrpgcontent", stdout=output)
        return output.getvalue()

    def custom_reward(self, family):
        return Reward.objects.create(
            family=family, name="Streak Freeze", description="Parent's private offer",
            cost_coins=713, requires_parent_approval=True, stock=3,
        )

    def assert_custom_offer_unchanged(self, reward):
        reward.refresh_from_db()
        self.assertEqual(reward.cost_coins, 713)
        self.assertTrue(reward.requires_parent_approval)
        self.assertEqual(reward.stock, 3)
        self.assertEqual(reward.description, "Parent's private offer")
        self.assertEqual(reward.fulfillment_kind, "real_world")
        self.assertIsNone(reward.item_definition_id)

    def test_other_family_same_name_does_not_block_startup(self):
        reward = self.custom_reward(self.other_family)
        self.reload()
        self.assert_custom_offer_unchanged(reward)
        self.assertEqual(Reward.objects.filter(name="Streak Freeze").count(), 2)

    def test_missing_seed_offer_does_not_adopt_other_family_reward(self):
        Reward.objects.filter(family=self.default_family, name="Streak Freeze").delete()
        reward = self.custom_reward(self.other_family)
        self.reload()
        self.assert_custom_offer_unchanged(reward)
        seed = Reward.objects.get(family=self.default_family, name="Streak Freeze")
        self.assertEqual(seed.cost_coins, 60)
        self.assertFalse(seed.requires_parent_approval)
        self.assertEqual(seed.item_definition.slug, "streak-freeze")

    def test_default_family_custom_offer_is_preserved(self):
        Reward.objects.filter(family=self.default_family, name="Streak Freeze").delete()
        reward = self.custom_reward(self.default_family)
        output = self.reload()
        self.assert_custom_offer_unchanged(reward)
        self.assertIn("preserved_family_reward", output)

    def test_parent_edits_to_seed_offer_survive_restarts(self):
        reward = Reward.objects.get(family=self.default_family, name="Streak Freeze")
        reward.cost_coins = 713
        reward.requires_parent_approval = True
        reward.is_active = False
        reward.save()
        self.reload()
        reward.refresh_from_db()
        self.assertEqual(reward.cost_coins, 713)
        self.assertTrue(reward.requires_parent_approval)
        self.assertFalse(reward.is_active)

    def test_duplicate_drop_rows_are_reported_and_left_unchanged(self):
        row = DropTable.objects.get(trigger_type="milestone_complete", item__slug="streak-freeze")
        duplicate = DropTable.objects.create(
            trigger_type=row.trigger_type, item=row.item, weight=91, min_level=17,
        )
        rows = DropTable.objects.filter(trigger_type=row.trigger_type, item=row.item).order_by("pk")
        expected = list(rows.values())
        output = self.reload()
        self.assertEqual(list(rows.values()), expected)
        self.assertTrue(DropTable.objects.filter(pk=duplicate.pk).exists())
        self.assertIn("ambiguous_droptable", output)

    def test_duplicate_quest_reward_rows_are_reported_and_left_unchanged(self):
        quest = QuestDefinition.objects.get(name="Ghost Trail", created_by=None)
        row = quest.reward_items.get(item__slug="meshtint-ghost-egg")
        duplicate = QuestRewardItem.objects.create(quest_definition=quest, item=row.item, quantity=7)
        rows = QuestRewardItem.objects.filter(quest_definition=quest, item=row.item).order_by("pk")
        expected = list(rows.values())
        output = self.reload()
        self.assertEqual(list(rows.values()), expected)
        self.assertTrue(QuestRewardItem.objects.filter(pk=duplicate.pk).exists())
        self.assertIn("ambiguous_questrewarditem", output)


class ReviewedPublicationAmbiguityTests(TestCase):
    def test_reviewed_drop_publication_refuses_duplicate_owned_natural_key(self):
        family = make_family("Drop publication", parents=[{
            "username": "drop-publisher", "is_staff": True,
        }])
        actor = family.parents[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "items.yaml").write_text(yaml.safe_dump({"items": [{
                "slug": "token", "name": "Token", "item_type": "food", "icon": "x",
            }]}), encoding="utf-8")
            (path / "drops.yaml").write_text(yaml.safe_dump({"rules": [{
                "trigger": "chore_complete", "item_slugs": ["token"], "weight": 2,
            }]}), encoding="utf-8")
            plan = preview_content_pack(path, "reviewed", actor)
            publish_content_pack(path, "reviewed", actor, plan["preview_id"], plan["content_digest"])
            item = ItemDefinition.objects.get(slug="reviewed-token")
            DropTable.objects.create(trigger_type="chore_complete", item=item, weight=9)
            with self.assertRaisesMessage(ContentPackError, "natural key collides"):
                preview_content_pack(path, "reviewed", actor)
            self.assertEqual(list(DropTable.objects.filter(item=item).order_by("weight").values_list("weight", flat=True)), [2, 9])

    def test_reviewed_reward_publication_still_updates_owned_price_and_approval(self):
        family = make_family("Shop publication", parents=[{
            "username": "shop-publisher", "is_staff": True,
        }])
        actor = family.parents[0]
        other = make_family("Private shop").family
        private = Reward.objects.create(family=other, name="Reward", cost_coins=713)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for price, approval in ((20, True), (30, False)):
                (path / "rewards.yaml").write_text(yaml.safe_dump({"rewards": [{
                    "id": "reward", "name": "Reward", "cost_coins": price,
                    "requires_parent_approval": approval,
                }]}), encoding="utf-8")
                plan = preview_content_pack(path, "reviewed", actor)
                publish_content_pack(path, "reviewed", actor, plan["preview_id"], plan["content_digest"])
            reward = Reward.objects.get(family=family.family, name="Reward")
            self.assertEqual(reward.cost_coins, 30)
            self.assertFalse(reward.requires_parent_approval)
            private.refresh_from_db()
            self.assertEqual(private.cost_coins, 713)
            self.assertTrue(private.requires_parent_approval)

    def test_reviewed_publication_refuses_duplicate_links_and_rolls_back(self):
        family = make_family("Reviewed publication", parents=[{
            "username": "catalog-publisher", "is_staff": True,
        }])
        actor = family.parents[0]
        parsed = {
            "items": {"items": [{"slug": "token", "name": "Token", "item_type": "food", "icon": "x"}]},
            "quests": {"quests": [{
                "id": "quest", "name": "Published quest", "description": "Original",
                "quest_type": "collection", "target_value": 2,
                "reward_items": [{"slug": "token", "quantity": 1}],
            }]},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for section, value in parsed.items():
                (path / f"{section}.yaml").write_text(yaml.safe_dump(value), encoding="utf-8")
            plan = preview_content_pack(path, "reviewed", actor)
            publish_content_pack(path, "reviewed", actor, plan["preview_id"], plan["content_digest"])
            quest = QuestDefinition.objects.get(name="Published quest")
            item = ItemDefinition.objects.get(slug="reviewed-token")
            QuestRewardItem.objects.create(quest_definition=quest, item=item, quantity=9)
            parsed["quests"]["quests"][0]["description"] = "Must roll back"
            loader = ContentPack(path, namespace="reviewed-", pack_key="reviewed",
                                 family=family.family, parsed_content=parsed)
            with self.assertRaisesMessage(ContentPackError, "Ambiguous questrewarditem"):
                loader.load()
            quest.refresh_from_db()
            self.assertEqual(quest.description, "Original")
            self.assertEqual(list(quest.reward_items.order_by("quantity").values_list("quantity", flat=True)), [1, 9])
