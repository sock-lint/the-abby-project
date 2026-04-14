from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from apps.rpg.services import CosmeticService


class CosmeticServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cosmeticchild", password="testpass", role="child",
        )
        self.profile, _ = CharacterProfile.objects.get_or_create(user=self.user)

        self.frame = ItemDefinition.objects.create(
            name="Bronze Frame",
            icon="🟫",
            item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
            metadata={"border_color": "#CD7F32"},
        )
        self.title = ItemDefinition.objects.create(
            name="Apprentice",
            icon="🎓",
            item_type=ItemDefinition.ItemType.COSMETIC_TITLE,
            rarity=ItemDefinition.Rarity.COMMON,
            coin_value=5,
            metadata={"text": "Apprentice"},
        )
        self.theme = ItemDefinition.objects.create(
            name="Ocean Theme",
            icon="🌊",
            item_type=ItemDefinition.ItemType.COSMETIC_THEME,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            coin_value=20,
        )
        self.egg = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.COMMON,
        )

    def _give_item(self, item, qty=1):
        UserInventory.objects.create(user=self.user, item=item, quantity=qty)

    def test_equip_cosmetic_frame(self):
        self._give_item(self.frame)

        result = CosmeticService.equip(self.user, self.frame.pk)

        self.assertEqual(result["slot"], "active_frame")
        self.assertEqual(result["item_id"], self.frame.pk)
        self.assertEqual(result["item_name"], "Bronze Frame")

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.active_frame_id, self.frame.pk)

    def test_equip_item_not_owned(self):
        # User does not own the frame
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, self.frame.pk)
        self.assertIn("don't own", str(ctx.exception))

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_frame)

    def test_equip_non_cosmetic_raises(self):
        self._give_item(self.egg)

        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, self.egg.pk)
        self.assertIn("not a cosmetic", str(ctx.exception))

    def test_equip_unknown_item_raises(self):
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.equip(self.user, 999999)
        self.assertIn("not found", str(ctx.exception))

    def test_unequip_clears_slot(self):
        self._give_item(self.frame)
        CosmeticService.equip(self.user, self.frame.pk)

        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.active_frame)

        result = CosmeticService.unequip(self.user, "active_frame")
        self.assertEqual(result["slot"], "active_frame")

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.active_frame)

    def test_unequip_invalid_slot_raises(self):
        with self.assertRaises(ValueError) as ctx:
            CosmeticService.unequip(self.user, "active_bogus")
        self.assertIn("Invalid slot", str(ctx.exception))

    def test_list_owned_cosmetics(self):
        self._give_item(self.frame)
        self._give_item(self.title)
        self._give_item(self.theme)
        self._give_item(self.egg)  # Should NOT appear in results

        owned = CosmeticService.list_owned_cosmetics(self.user)

        self.assertIn("active_frame", owned)
        self.assertIn("active_title", owned)
        self.assertIn("active_theme", owned)
        self.assertIn("active_pet_accessory", owned)

        self.assertEqual(len(owned["active_frame"]), 1)
        self.assertEqual(owned["active_frame"][0].pk, self.frame.pk)

        self.assertEqual(len(owned["active_title"]), 1)
        self.assertEqual(owned["active_title"][0].pk, self.title.pk)

        self.assertEqual(len(owned["active_theme"]), 1)
        self.assertEqual(owned["active_theme"][0].pk, self.theme.pk)

        self.assertEqual(len(owned["active_pet_accessory"]), 0)
