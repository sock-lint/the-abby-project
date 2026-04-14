from django.db import IntegrityError
from django.test import TestCase

from apps.projects.models import User
from apps.rpg.models import (
    CharacterProfile, DropLog, DropTable, Habit, HabitLog, ItemDefinition, UserInventory,
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


class HabitTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="parent", password="testpass", role="parent")
        self.child = User.objects.create_user(username="child", password="testpass", role="child")

    def test_create_positive_habit(self):
        habit = Habit.objects.create(
            name="Read a book",
            user=self.child,
            created_by=self.parent,
        )
        self.assertEqual(habit.habit_type, Habit.HabitType.POSITIVE)
        self.assertEqual(habit.coin_reward, 1)
        self.assertEqual(habit.xp_reward, 5)
        self.assertEqual(habit.strength, 0)
        self.assertTrue(habit.is_active)
        self.assertEqual(str(habit), "Read a book")

    def test_create_habit_with_icon(self):
        habit = Habit.objects.create(
            name="Exercise",
            icon="💪",
            user=self.child,
            created_by=self.parent,
        )
        self.assertEqual(str(habit), "💪 Exercise")

    def test_create_habit_log(self):
        habit = Habit.objects.create(
            name="Study",
            user=self.child,
            created_by=self.parent,
        )
        log = HabitLog.objects.create(
            habit=habit,
            user=self.child,
            direction=1,
            streak_at_time=3,
        )
        self.assertEqual(log.direction, 1)
        self.assertEqual(log.streak_at_time, 3)
        self.assertEqual(log.habit, habit)

    def test_habit_type_choices(self):
        valid_values = {choice.value for choice in Habit.HabitType}
        self.assertEqual(valid_values, {"positive", "negative", "both"})


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
