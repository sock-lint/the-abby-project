from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.quests.goals import _award, _occurrence, _snapshot, occurrence_payload
from apps.quests.models import ChallengeGoal, QuestDefinition, QuestRewardItem
from apps.quests.serializers import QuestRewardItemSerializer, QuestSerializer
from apps.quests.services import QuestService
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


class ChallengeRewardVisibilityTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "visible-reward-child"}]).children[0]
        self.item = ItemDefinition.objects.create(
            slug="pouch-large", name="Large Coin Pouch", icon="C", sprite_key="silver-coin-stack",
            item_type="coin_pouch", rarity="rare", description="Open for 50 Coins",
            metadata={"coins": 50}, coin_value=50,
        )
        self.definition = QuestDefinition.objects.create(name="Visible rewards", quest_type="collection", target_value=1, is_system=True)
        self.reward = QuestRewardItem.objects.create(quest_definition=self.definition, item=self.item, quantity=2)

    def goal(self):
        now = timezone.now()
        return ChallengeGoal.objects.create(
            user=self.child, family=self.child.family, name="Visible automatic rewards", metric="count", target=1,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1), timezone_name="America/Phoenix",
            trigger_filter={"allowed_triggers": ["chore_complete"]},
            reward_items=[{"item_id": self.item.pk, "quantity": 2}],
        )

    def assert_details(self, row):
        self.assertEqual(row.get("item_rarity"), "rare")
        self.assertEqual(row.get("item_type"), "coin_pouch")
        self.assertEqual(row.get("item_description"), "Open for 50 Coins")
        self.assertEqual(row.get("item_metadata"), {"coins": 50})
        self.assertEqual(row.get("item_sprite_key"), "silver-coin-stack")
        self.assertEqual(row.get("item_name"), "Large Coin Pouch")
        self.assertEqual(row.get("item_effect_summary"), "Open to collect 50 coins.")

    def test_promised_and_actual_automatic_rewards_keep_frozen_item_details(self):
        occurrence = _occurrence(self.goal(), timezone.now())
        self.assert_details(occurrence.snapshot["items"][0])
        ItemDefinition.objects.filter(pk=self.item.pk).update(name="Renamed", rarity="common", metadata={"coins": 1})
        self.assert_details(occurrence_payload(occurrence)["rewards"]["items"][0])
        receipt = _award(occurrence, self.child)
        self.assert_details(receipt["items"][0])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 2)
        self.assertEqual(_award(occurrence, self.child), receipt)

    def test_legacy_preview_exposes_details_and_keeps_accepted_snapshot_after_catalog_edit(self):
        self.assert_details(QuestRewardItemSerializer(self.reward).data)
        quest = QuestService.start_quest(self.child, self.definition.pk)
        ItemDefinition.objects.filter(pk=self.item.pk).update(name="Renamed", rarity="common", metadata={"coins": 1})
        self.assert_details(QuestSerializer(quest).data["definition"]["reward_items"][0])

    def test_legacy_actual_completion_keeps_promised_details_and_exact_quantity(self):
        QuestService.start_quest(self.child, self.definition.pk)
        ItemDefinition.objects.filter(pk=self.item.pk).update(name="Renamed", rarity="common", metadata={"coins": 1})
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertTrue(result["completed"])
        self.assert_details(result["rewards"]["items"][0])
        self.assertEqual(result["rewards"]["items"][0]["quantity"], 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 2)

    def test_saved_legacy_snapshot_is_not_modified_during_detail_reads(self):
        quest = QuestService.start_quest(self.child, self.definition.pk)
        original = [{"id": self.reward.pk, "item_id": self.item.pk, "quantity": 2}]
        quest.reward_items_snapshot = original
        quest.save(update_fields=["reward_items_snapshot"])
        self.assert_details(QuestSerializer(quest).data["definition"]["reward_items"][0])
        quest.refresh_from_db()
        self.assertEqual(quest.reward_items_snapshot, original)

    def test_historical_goal_receipt_is_read_without_rewriting_or_inventing_details(self):
        occurrence = _occurrence(self.goal(), timezone.now())
        original = {"coins": 0, "xp": 0, "items": [{"item_name": "Old reward", "quantity": 2}]}
        occurrence.reward_receipt = original
        occurrence.awarded_at = timezone.now()
        occurrence.save(update_fields=["reward_receipt", "awarded_at"])
        data = occurrence_payload(occurrence)
        self.assertEqual(data["reward_receipt"]["items"], original["items"])
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.reward_receipt, original)

    def test_retired_item_preview_disables_actions_without_erasing_accepted_promise(self):
        occurrence = _occurrence(self.goal(), timezone.now())
        snapshot = occurrence.snapshot
        retired_policy = {"schema_version": 1, "pets": [], "potion_slugs": [], "disabled_item_types": ["coin_pouch"]}
        with override_settings(RPG_ASSET_SUPPORT_POLICY=retired_policy):
            item = occurrence_payload(occurrence)["rewards"]["items"][0]
            self.assert_details(item)
            self.assertIs(item["item_catalog_available"], False)
            receipt = _award(occurrence, self.child)
        self.assertEqual(receipt["items"][0]["quantity"], 2)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 2)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, snapshot)

    def test_new_snapshot_batches_item_reads(self):
        goal = self.goal()
        goal.reward_items = [{"item_id": self.item.pk, "quantity": 2}] * 3
        with self.assertNumQueries(1):
            snapshot = _snapshot(goal)
        self.assertEqual(len(snapshot["items"]), 3)
