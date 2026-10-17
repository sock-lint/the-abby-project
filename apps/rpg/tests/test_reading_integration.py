"""Reading's daily reward uses the supported RPG catalog and atomic pipeline."""
from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService, TRIGGER_DAMAGE
from apps.rewards.models import CoinLedger
from apps.rpg.catalog_support import item_is_available
from apps.rpg.constants import TriggerType
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import CharacterProfile, DropLog, DropTable, UserInventory
from apps.rpg.services import BASE_DROP_RATES, DropService, GameLoopService


class ReadingRPGIntegrationTests(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="reader", role="child")

    def test_reading_is_a_canonical_reward_trigger_and_coin_reason(self):
        self.assertIn("reading_logged", TriggerType.values)
        self.assertIn("reading", CoinLedger.Reason.values)
        self.assertEqual(BASE_DROP_RATES.get("reading_logged"), 0.20)
        self.assertEqual(TRIGGER_DAMAGE.get("reading_logged"), 5)

    def test_initial_reading_pool_grants_supported_inventory_with_receipt(self):
        ContentPack("content/rpg/initial").load()
        pool = list(DropTable.objects.filter(trigger_type="reading_logged").select_related("item"))
        self.assertTrue(pool, "Reading must have a real authored drop pool")
        self.assertEqual(
            {row.item.item_type for row in pool},
            {"food", "coin_pouch"},
        )
        self.assertTrue(all(item_is_available(row.item) for row in pool))
        with patch("apps.rpg.services.random.random", return_value=0.1):
            drops = DropService.process_drops(self.child, "reading_logged")
        self.assertEqual(len(drops), 1)
        receipt = DropLog.objects.get(user=self.child, trigger_type="reading_logged")
        self.assertEqual(receipt.item_id, drops[0]["item_id"])
        self.assertEqual(UserInventory.objects.get(user=self.child, item=receipt.item).quantity, 1)

    def test_strict_pipeline_failure_rolls_back_outer_reward_and_prior_steps(self):
        before = CharacterProfile.objects.get(user=self.child)
        with self.assertRaisesRegex(RuntimeError, "reading drop failed"):
            with transaction.atomic():
                CoinLedger.objects.create(user=self.child, amount=5, reason="reading")
                with patch(
                    "apps.rpg.services.DropService.process_drops",
                    side_effect=RuntimeError("reading drop failed"),
                ), patch("apps.quests.services.QuestService.record_progress") as quest:
                    try:
                        GameLoopService.on_task_completed(
                            self.child, "reading_logged", strict=True,
                        )
                    finally:
                        quest.assert_not_called()
        after = CharacterProfile.objects.get(user=self.child)
        self.assertEqual(after.login_streak, before.login_streak)
        self.assertEqual(after.last_active_date, before.last_active_date)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_saved_legacy_boss_uses_reading_damage_and_filter(self):
        definition = QuestDefinition.objects.create(
            name="Saved reading quest", quest_type="boss", target_value=100,
            trigger_filter={"allowed_triggers": ["reading_logged"]},
        )
        quest = Quest.objects.create(
            definition=definition, end_date=timezone.now() + timedelta(days=7),
        )
        participant = QuestParticipant.objects.create(quest=quest, user=self.child)
        self.assertIsNone(QuestService.record_progress(self.child, "habit_log"))
        result = QuestService.record_progress(self.child, "reading_logged")
        self.assertEqual(result["damage_dealt"], 5)
        quest.refresh_from_db()
        participant.refresh_from_db()
        self.assertEqual(quest.current_progress, 5)
        self.assertEqual(participant.contribution, 5)
