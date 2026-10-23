"""New bundled prices guide future offers without repricing family promises."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.families.models import Family
from apps.rewards.models import Reward


class RewardPricePlanningTests(TestCase):
    def test_missing_streak_freeze_uses_three_days_at_fifty_coins(self):
        call_command("loadrpgcontent", stdout=StringIO())
        reward = Reward.objects.get(family__slug="default-family", name="Streak Freeze")
        self.assertEqual(reward.cost_coins, 150)
        self.assertEqual(reward.item_definition.slug, "streak-freeze")
        self.assertFalse(reward.requires_parent_approval)

    def test_existing_legacy_price_is_preserved_when_new_seed_price_loads(self):
        family = Family.objects.create(slug="default-family", name="Default Family")
        reward = Reward.objects.create(family=family, name="Streak Freeze", cost_coins=60)
        call_command("loadrpgcontent", stdout=StringIO())
        reward.refresh_from_db()
        self.assertEqual(reward.cost_coins, 60)
        self.assertEqual(reward.fulfillment_kind, Reward.FulfillmentKind.REAL_WORLD)
        self.assertIsNone(reward.item_definition_id)
