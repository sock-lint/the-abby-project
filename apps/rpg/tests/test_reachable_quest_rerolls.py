"""A reroll spends inventory only on a campaign normal saved work can advance."""
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.habits.models import Habit
from apps.quests.models import Quest, QuestDefinition
from apps.reading.models import ReadingBook, ReadingDailyReward
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReachableQuestRerollTests(TestCase):
    def setUp(self):
        household = make_family(
            "Reachable rerolls", parents=[{"username": "reroll-parent"}],
            children=[{"username": "reroll-child"}],
        )
        self.parent, self.child = household.parents[0], household.children[0]
        self.item = ItemDefinition.objects.create(
            slug="reachable-quest-reroll", name="Quest Reroll", item_type="consumable",
            metadata={"effect": "quest_reroll"},
        )
        UserInventory.objects.create(user=self.child, item=self.item, quantity=2)
        self.client = APIClient()
        self.client.force_authenticate(self.child)

    def definition(self, name, filters, **values):
        return QuestDefinition.objects.create(
            name=name, quest_type=values.pop("quest_type", "collection"),
            target_value=values.pop("target_value", 3), duration_days=14, is_system=True,
            trigger_filter=filters, **values,
        )

    def reroll(self):
        return self.client.post(f"/api/inventory/{self.item.pk}/use/", {}, format="json")

    def assert_reward_only_denied(self, triggers, **values):
        self.definition("Unreachable campaign", {"allowed_triggers": triggers}, **values)
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            response = self.reroll()
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data, {"error": "No eligible quests to reroll into"})
        choose.assert_not_called()
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 2)
        self.assertFalse(Quest.objects.filter(participants__user=self.child).exists())

    def test_badge_only_pool_preserves_item_instead_of_starting_a_stalled_campaign(self):
        self.assert_reward_only_denied(["badge_earned"])

    def test_perfect_day_only_pool_preserves_item_instead_of_starting_a_stalled_campaign(self):
        self.assert_reward_only_denied(["perfect_day"])

    def test_quest_completion_only_pool_also_has_no_activity_producer(self):
        self.assert_reward_only_denied(["quest_complete"])

    def assert_habit_advances(self, quest, expected_progress=1):
        habit = Habit.objects.create(user=self.child, created_by=self.parent, name="A real positive tap", xp_reward=0)
        logged = self.client.post(f"/api/habits/{habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(logged.status_code, 200, logged.data)
        quest.refresh_from_db()
        self.assertEqual(quest.current_progress, expected_progress)

    def test_mixed_pool_selects_real_effort_and_actual_habit_route_advances_it(self):
        self.definition("A reward-only campaign", {"allowed_triggers": ["badge_earned", "perfect_day"]})
        reachable = self.definition("Z reachable campaign", {"allowed_triggers": ["habit_log"]})
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            response = self.reroll()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row.pk for row in choose.call_args.args[0]], [reachable.pk])
        quest = Quest.objects.get(participants__user=self.child)
        self.assertEqual(quest.definition_id, reachable.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
        self.assert_habit_advances(quest)

    def assert_reachable_habit_definition(self, filters, **values):
        expected_progress = values.pop("expected_progress", 1)
        reachable = self.definition("A reachable campaign", filters, **values)
        response = self.reroll()
        self.assertEqual(response.status_code, 200, response.data)
        quest = Quest.objects.get(participants__user=self.child)
        self.assertEqual(quest.definition_id, reachable.pk)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
        self.assert_habit_advances(quest, expected_progress)

    def test_mixed_reward_and_effort_whitelist_remains_reachable(self):
        self.assert_reachable_habit_definition({"allowed_triggers": ["badge_earned", "habit_log", "perfect_day"]})

    def test_unfiltered_campaign_remains_reachable(self):
        self.assert_reachable_habit_definition({})

    def test_empty_whitelist_keeps_legacy_unfiltered_behavior(self):
        self.assert_reachable_habit_definition({"allowed_triggers": []})

    def test_nullable_whitelist_keeps_legacy_unfiltered_behavior(self):
        self.assert_reachable_habit_definition({"allowed_triggers": None})

    def test_boss_filtered_only_to_zero_damage_activity_preserves_item(self):
        self.assert_reward_only_denied(["creation_logged"], quest_type="boss")

    def test_mixed_boss_whitelist_keeps_real_damage_activity(self):
        self.assert_reachable_habit_definition(
            {"allowed_triggers": ["creation_logged", "habit_log"]},
            quest_type="boss", target_value=20, expected_progress=5,
        )

    def test_explicit_reading_campaign_advances_through_real_daily_adventure(self):
        reachable = self.definition("Reading campaign", {"allowed_triggers": ["reading_logged"]})
        response = self.reroll()
        self.assertEqual(response.status_code, 200, response.data)
        quest = Quest.objects.get(definition=reachable, participants__user=self.child)
        category = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(name="Reading Comprehension", category=category)
        book = ReadingBook.objects.create(
            user=self.child, title="A synthetic story", client_request_id=uuid4(), create_payload={},
        )

        logged = self.client.post("/api/reading-sessions/", {
            "book": book.pk, "duration_minutes": 10, "client_request_id": str(uuid4()),
        }, format="json")

        self.assertEqual(logged.status_code, 201, logged.data)
        self.assertTrue(ReadingDailyReward.objects.filter(user=self.child, awarded_at__isnull=False).exists())
        quest.refresh_from_db()
        self.assertEqual(quest.current_progress, 1)
        self.assertEqual(UserInventory.objects.get(user=self.child, item=self.item).quantity, 1)
