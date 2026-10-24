"""Manual quest rerolls cannot select automatic active-day challenges."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.quests.models import ChallengeGoal, Quest, QuestDefinition
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FuturePolicyRerollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", stdout=StringIO())
        cls.child = make_family("Future rerolls", children=[{"username": "future-reroll-child"}]).children[0]
        cls.reroll = ItemDefinition.objects.create(
            name="Future-policy reroll", slug="future-policy-reroll", item_type="consumable",
            metadata={"effect": "quest_reroll"},
        )
        UserInventory.objects.create(user=cls.child, item=cls.reroll, quantity=2)

    def test_fresh_child_reroll_skips_active_day_offers_and_spends_one_item(self):
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())

        def prefer_active_days(rows):
            return next((row for row in rows if row.trigger_filter.get("distinct_active_days") is True), rows[0])

        with patch("apps.rpg.services.random.choice", side_effect=prefer_active_days) as choose:
            result = ConsumableService.use(self.child, self.reroll.pk)

        self.assertTrue(choose.call_args.args[0])
        self.assertFalse(any(row.trigger_filter.get("distinct_active_days") is True
                             for row in choose.call_args.args[0]))
        quest = Quest.objects.get(pk=result["detail"]["quest_id"])
        self.assertNotEqual(quest.definition.trigger_filter.get("distinct_active_days"), True)
        self.assertEqual(Quest.objects.filter(participants__user=self.child).count(), 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.reroll).quantity, 1)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())

    def test_only_active_day_offers_keep_existing_no_eligible_behavior_and_inventory(self):
        active_day_ids = list(QuestDefinition.objects.filter(
            trigger_filter__distinct_active_days=True,
        ).values_list("pk", flat=True))
        self.assertTrue(active_day_ids)
        # Untimed onboarding must stay system-owned; rerolls already exclude it.
        QuestDefinition.objects.exclude(pk__in=active_day_ids).exclude(duration_days=None).update(is_system=False)
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            with self.assertRaisesMessage(ValueError, "No eligible quests to reroll into"):
                ConsumableService.use(self.child, self.reroll.pk)
        choose.assert_not_called()
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.reroll).quantity, 2)
        self.assertFalse(Quest.objects.exists())
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child).exists())
