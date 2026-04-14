from unittest.mock import patch

from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import (
    CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory,
)
from apps.rpg.services import DropService


class DropServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dropchild", password="testpass", role="child"
        )
        self.profile = CharacterProfile.objects.get(user=self.user)
        self.egg_item = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.COMMON,
        )
        DropTable.objects.create(
            trigger_type=DropTable.TriggerType.CLOCK_OUT,
            item=self.egg_item,
            weight=10,
            min_level=0,
        )

    @patch("apps.rpg.services.random.choices")
    @patch("apps.rpg.services.random.random")
    def test_drop_awarded_when_roll_succeeds(self, mock_random, mock_choices):
        mock_random.return_value = 0  # Always passes the drop rate check
        # mock_choices needs to return a list of DropTable entries
        entry = DropTable.objects.get(item=self.egg_item)
        mock_choices.return_value = [entry]

        result = DropService.process_drops(self.user, "clock_out")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_name"], "Dragon Egg")
        self.assertFalse(result[0]["was_salvaged"])
        # Verify inventory
        inv = UserInventory.objects.get(user=self.user, item=self.egg_item)
        self.assertEqual(inv.quantity, 1)
        # Verify drop log
        log = DropLog.objects.get(user=self.user)
        self.assertEqual(log.trigger_type, "clock_out")
        self.assertFalse(log.was_salvaged)

    @patch("apps.rpg.services.random.random")
    def test_no_drop_when_roll_fails(self, mock_random):
        mock_random.return_value = 1.0  # Always fails the drop rate check

        result = DropService.process_drops(self.user, "clock_out")

        self.assertEqual(result, [])
        self.assertFalse(UserInventory.objects.filter(user=self.user).exists())
        self.assertFalse(DropLog.objects.filter(user=self.user).exists())

    @patch("apps.rpg.services.random.choices")
    @patch("apps.rpg.services.random.random")
    def test_cosmetic_salvage(self, mock_random, mock_choices):
        cosmetic = ItemDefinition.objects.create(
            name="Gold Frame",
            icon="🖼️",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.RARE,
            coin_value=25,
        )
        entry = DropTable.objects.create(
            trigger_type=DropTable.TriggerType.CLOCK_OUT,
            item=cosmetic,
            weight=10,
        )
        # User already owns this cosmetic
        UserInventory.objects.create(user=self.user, item=cosmetic, quantity=1)

        mock_random.return_value = 0
        mock_choices.return_value = [entry]

        result = DropService.process_drops(self.user, "clock_out")

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["was_salvaged"])
        # Inventory quantity should NOT increase (salvaged)
        inv = UserInventory.objects.get(user=self.user, item=cosmetic)
        self.assertEqual(inv.quantity, 1)
        # Drop log should show salvaged
        log = DropLog.objects.get(user=self.user, item=cosmetic)
        self.assertTrue(log.was_salvaged)
        # Coin ledger should have salvage entry
        from apps.rewards.models import CoinLedger
        self.assertTrue(
            CoinLedger.objects.filter(
                user=self.user, description="Salvaged duplicate: Gold Frame"
            ).exists()
        )

    @patch("apps.rpg.services.random.choices")
    @patch("apps.rpg.services.random.random")
    def test_inventory_quantity_increments(self, mock_random, mock_choices):
        mock_random.return_value = 0
        entry = DropTable.objects.get(item=self.egg_item)
        mock_choices.return_value = [entry]

        DropService.process_drops(self.user, "clock_out")
        DropService.process_drops(self.user, "clock_out")

        inv = UserInventory.objects.get(user=self.user, item=self.egg_item)
        self.assertEqual(inv.quantity, 2)
        self.assertEqual(DropLog.objects.filter(user=self.user).count(), 2)

    @patch("apps.rpg.services.random.random")
    def test_min_level_filtering(self, mock_random):
        """Drop entry with min_level=5 should not drop for a level-0 user."""
        high_level_item = ItemDefinition.objects.create(
            name="Legendary Scroll",
            icon="📜",
            item_type=ItemDefinition.ItemType.QUEST_SCROLL,
            rarity=ItemDefinition.Rarity.LEGENDARY,
        )
        # Only drop table entry for this trigger requires level 5
        DropTable.objects.filter(trigger_type="badge_earned").delete()
        DropTable.objects.create(
            trigger_type=DropTable.TriggerType.BADGE_EARNED,
            item=high_level_item,
            weight=10,
            min_level=5,
        )

        mock_random.return_value = 0  # Guaranteed to pass rate check

        result = DropService.process_drops(self.user, "badge_earned")

        # User is level 0, min_level=5, so no eligible entries -> no drop
        self.assertEqual(result, [])
