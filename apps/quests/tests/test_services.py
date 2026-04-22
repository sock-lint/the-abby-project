from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import User
from apps.quests.models import QuestDefinition, Quest, QuestParticipant
from apps.quests.services import QuestService


class QuestServiceTest(TestCase):
    def setUp(self):
        self.child = User.objects.create_user(username="questchild", password="test", role="child")
        self.boss_def = QuestDefinition.objects.create(
            name="Dragon Slayer", description="Defeat the dragon",
            quest_type="boss", target_value=100, duration_days=7,
            coin_reward=50, xp_reward=100, is_system=True,
        )
        self.collection_def = QuestDefinition.objects.create(
            name="Gather Feathers", description="Collect feathers",
            quest_type="collection", target_value=5, duration_days=3,
        )

    def test_start_quest(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        self.assertEqual(quest.status, "active")
        self.assertEqual(quest.definition, self.boss_def)
        self.assertTrue(QuestParticipant.objects.filter(quest=quest, user=self.child).exists())

    def test_cannot_start_two_active_quests(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        with self.assertRaises(ValueError):
            QuestService.start_quest(self.child, self.collection_def.pk)

    def test_record_boss_progress(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertIsNotNone(result)
        self.assertEqual(result["damage_dealt"], 15)
        self.assertFalse(result["completed"])

    def test_record_collection_progress(self):
        QuestService.start_quest(self.child, self.collection_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertEqual(result["damage_dealt"], 1)

    def test_quest_completes_when_target_reached(self):
        self.boss_def.target_value = 15
        self.boss_def.save()
        QuestService.start_quest(self.child, self.boss_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertTrue(result["completed"])
        self.assertIsNotNone(result["rewards"])

    def test_no_progress_without_active_quest(self):
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertIsNone(result)

    def test_trigger_filter_blocks_unmatched(self):
        filtered_def = QuestDefinition.objects.create(
            name="Chore Quest", description="Only chores",
            quest_type="collection", target_value=5,
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        )
        QuestService.start_quest(self.child, filtered_def.pk)
        result = QuestService.record_progress(self.child, "clock_out")
        self.assertIsNone(result)  # clock_out not in allowed_triggers

    def test_expire_quests(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        quest.end_date = timezone.now() - timedelta(hours=1)
        quest.save()
        expired_count = QuestService.expire_quests()
        self.assertEqual(expired_count, 1)
        quest.refresh_from_db()
        self.assertEqual(quest.status, "expired")

    def test_boss_rage(self):
        quest = QuestService.start_quest(self.child, self.boss_def.pk)
        # Simulate no progress today by backdating participant updated_at
        QuestParticipant.objects.filter(quest=quest).update(
            updated_at=timezone.now() - timedelta(days=1),
        )
        result = QuestService.apply_boss_rage()
        self.assertEqual(result["raged"], 1)
        self.assertEqual(result["decayed"], 0)
        quest.refresh_from_db()
        self.assertEqual(quest.rage_shield, 20)

    def test_get_active_quest(self):
        QuestService.start_quest(self.child, self.boss_def.pk)
        active = QuestService.get_active_quest(self.child)
        self.assertIsNotNone(active)
        self.assertEqual(active.definition.name, "Dragon Slayer")


class QuestEggSalvageTest(TestCase):
    """2026-04-23 review — egg quest rewards salvage to coins when the
    player already mounts that species, so completionists with full stables
    don't accumulate dead eggs from boss rewards like Dragon Slayer.
    """

    def setUp(self):
        from apps.pets.models import PetSpecies, PotionType, UserMount
        from apps.quests.models import QuestRewardItem
        from apps.rpg.models import ItemDefinition

        self.child = User.objects.create_user(
            username="hatcher", password="test", role="child",
        )
        self.species = PetSpecies.objects.create(
            slug="wolf", name="Wolf", icon="🐺",
        )
        self.potion = PotionType.objects.create(slug="base", name="Base")

        self.egg = ItemDefinition.objects.create(
            slug="wolf-egg", name="Wolf Egg", icon="🥚",
            item_type=ItemDefinition.ItemType.EGG,
            pet_species=self.species,
            rarity="common", coin_value=3,
        )
        self.boss_def = QuestDefinition.objects.create(
            name="Wolf Boss", description="x",
            quest_type="boss", target_value=10, duration_days=1,
            coin_reward=0, xp_reward=0,
        )
        QuestRewardItem.objects.create(
            quest_definition=self.boss_def, item=self.egg, quantity=2,
        )
        # Player already owns the matching mount.
        UserMount.objects.create(
            user=self.child, species=self.species, potion=self.potion,
        )

    def test_egg_salvages_when_species_already_mounted(self):
        from apps.rewards.services import CoinService
        from apps.rpg.models import UserInventory

        QuestService.start_quest(self.child, self.boss_def.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        # Damage 15 ≥ target 10 → completes on first hit.
        self.assertTrue(result["completed"])

        # Inventory unchanged — egg never lands as an item.
        self.assertFalse(
            UserInventory.objects.filter(user=self.child, item=self.egg).exists()
        )
        # Coins credited at coin_value × quantity = 3 × 2 = 6.
        self.assertEqual(CoinService.get_balance(self.child), 6)

        salvage_entry = next(
            (i for i in result["rewards"]["items"] if "salvaged_to_coins" in i),
            None,
        )
        self.assertIsNotNone(salvage_entry)
        self.assertEqual(salvage_entry["salvaged_to_coins"], 6)

    def test_egg_lands_normally_when_species_not_mounted(self):
        from apps.pets.models import UserMount
        from apps.rpg.models import UserInventory
        UserMount.objects.filter(user=self.child).delete()

        QuestService.start_quest(self.child, self.boss_def.pk)
        QuestService.record_progress(self.child, "chore_complete")
        inv = UserInventory.objects.get(user=self.child, item=self.egg)
        self.assertEqual(inv.quantity, 2)
