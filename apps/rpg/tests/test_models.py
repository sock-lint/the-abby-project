from django.db import IntegrityError
from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import (
    CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory,
)


class CharacterProfileTests(TestCase):
    def test_profile_auto_created_on_user_save(self):
        user = User.objects.create_user(username="testchild", password="testpass")
        self.assertTrue(CharacterProfile.objects.filter(user=user).exists())

    def test_profile_defaults(self):
        user = User.objects.create_user(username="testchild2", password="testpass")
        profile = user.character_profile
        self.assertEqual(profile.level, 0)
        self.assertEqual(profile.login_streak, 0)
        self.assertEqual(profile.longest_login_streak, 0)
        self.assertIsNone(profile.last_active_date)
        self.assertEqual(profile.perfect_days_count, 0)

    def test_str(self):
        user = User.objects.create_user(username="abby", password="testpass", display_name="Abby")
        profile = user.character_profile
        self.assertEqual(str(profile), "Abby (Level 0)")

    def test_str_no_display_name(self):
        user = User.objects.create_user(username="kiduser", password="testpass")
        profile = user.character_profile
        self.assertEqual(str(profile), "kiduser (Level 0)")


class ItemDefinitionTests(TestCase):
    def test_create_item_definition(self):
        item = ItemDefinition.objects.create(
            name="Dragon Egg",
            icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            rarity=ItemDefinition.Rarity.RARE,
            coin_value=50,
        )
        self.assertEqual(str(item), "🥚 Dragon Egg (Rare)")
        self.assertEqual(item.item_type, "egg")
        self.assertEqual(item.rarity, "rare")
        self.assertEqual(item.coin_value, 50)


class UserInventoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="invchild", password="testpass", role="child")
        self.item = ItemDefinition.objects.create(
            name="Fire Potion", icon="🧪", item_type=ItemDefinition.ItemType.POTION,
        )

    def test_create_user_inventory(self):
        inv = UserInventory.objects.create(user=self.user, item=self.item, quantity=3)
        self.assertEqual(str(inv), f"{self.user} x3 Fire Potion")

    def test_unique_together(self):
        UserInventory.objects.create(user=self.user, item=self.item, quantity=1)
        with self.assertRaises(IntegrityError):
            UserInventory.objects.create(user=self.user, item=self.item, quantity=1)


class DropTableTests(TestCase):
    def test_create_drop_table_entry(self):
        item = ItemDefinition.objects.create(
            name="Common Egg", icon="🥚", item_type=ItemDefinition.ItemType.EGG,
        )
        entry = DropTable.objects.create(
            trigger_type=DropTable.TriggerType.CLOCK_OUT, item=item, weight=10, min_level=0,
        )
        self.assertEqual(str(entry), "Clock Out -> Common Egg (w=10)")


class CharacterProfileUnlocksTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create(username="kid", role=User.Role.CHILD)
        # CharacterProfile auto-created via post_save signal

    def test_unlocks_defaults_to_empty_dict(self):
        self.assertEqual(self.user.character_profile.unlocks, {})

    def test_is_unlocked_false_for_missing_slug(self):
        self.assertFalse(self.user.character_profile.is_unlocked("drivers_ed"))

    def test_unlock_sets_enabled_true_and_timestamps(self):
        self.user.character_profile.unlock("drivers_ed")
        self.assertTrue(self.user.character_profile.is_unlocked("drivers_ed"))
        entry = self.user.character_profile.unlocks["drivers_ed"]
        self.assertTrue(entry["enabled"])
        self.assertIn("enabled_at", entry)  # ISO date string

    def test_lock_sets_enabled_false(self):
        self.user.character_profile.unlock("first_job")
        self.user.character_profile.lock("first_job")
        self.assertFalse(self.user.character_profile.is_unlocked("first_job"))

    def test_unlock_persists_to_db(self):
        self.user.character_profile.unlock("college_prep")
        self.user.character_profile.save()
        self.user.character_profile.refresh_from_db()
        self.assertTrue(self.user.character_profile.is_unlocked("college_prep"))


class DropLogTests(TestCase):
    def test_create_drop_log(self):
        user = User.objects.create_user(username="dropchild", password="testpass", role="child")
        item = ItemDefinition.objects.create(
            name="Shiny Gem", icon="💎", item_type=ItemDefinition.ItemType.COSMETIC_FRAME,
        )
        log = DropLog.objects.create(
            user=user, item=item, trigger_type="clock_out", quantity=1, was_salvaged=False,
        )
        self.assertEqual(log.trigger_type, "clock_out")
        self.assertFalse(log.was_salvaged)
        self.assertEqual(log.quantity, 1)
