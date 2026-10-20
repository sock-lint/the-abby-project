"""A consumable whose effect earns a badge keeps that badge's same-item drop."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Badge, Skill, SkillCategory, SkillProgress
from apps.rpg.constants import TriggerType
from apps.rpg.models import DropLog, ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from apps.rpg.tests.test_accomplishment_drops import AccomplishmentDropFixture


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    RPG_ASSET_SUPPORT_POLICY=None,
)
class ConsumableBadgeDropStackTests(AccomplishmentDropFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.tonic = ItemDefinition.objects.create(
            slug="tonic-badge-drop", name="Skill tonic", icon="T",
            item_type=ItemDefinition.ItemType.CONSUMABLE,
            rarity=ItemDefinition.Rarity.UNCOMMON,
            metadata={"effect": "skill_tonic", "xp": 50},
        )
        category = SkillCategory.objects.create(name="Tonic skills")
        skill = Skill.objects.create(name="Tonic skill", category=category, is_locked_by_default=True)
        SkillProgress.objects.create(user=self.child, skill=skill, unlocked=True)
        Badge.objects.create(
            name="First unlocked skill", description="Unlock a skill",
            criteria_type=Badge.CriteriaType.SKILLS_UNLOCKED,
            criteria_value={"count": 1}, xp_bonus=0, award_coins=False,
        )
        self.seed_drop(TriggerType.BADGE_EARNED, self.tonic)

    def use_with_stack(self, quantity):
        UserInventory.objects.create(user=self.child, item=self.tonic, quantity=quantity)
        with patch("apps.rpg.services.random.random", return_value=0):
            ConsumableService.use(self.child, self.tonic.pk)
        self.assertEqual(DropLog.objects.filter(
            user=self.child, trigger_type=TriggerType.BADGE_EARNED, item=self.tonic,
        ).count(), 1)
        return UserInventory.objects.filter(user=self.child, item=self.tonic).first()

    def test_last_unit_use_keeps_the_dropped_unit(self):
        stack = self.use_with_stack(1)
        self.assertIsNotNone(stack)
        self.assertEqual(stack.quantity, 1)

    def test_partial_stack_use_keeps_the_dropped_unit(self):
        self.assertEqual(self.use_with_stack(3).quantity, 3)
