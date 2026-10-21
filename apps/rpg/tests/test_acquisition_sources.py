from django.test import TestCase
from django.utils import timezone
from django.db import connection
from django.test.utils import CaptureQueriesContext
from datetime import timedelta
from unittest.mock import patch
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.quests.models import QuestDefinition, QuestRewardItem
from apps.rewards.models import Reward
from apps.rpg.models import ItemDefinition


class AcquisitionSourcesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="source-child", role="child")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.frame = ItemDefinition.objects.create(name="Trail frame", item_type="cosmetic_frame", rarity="rare")
        self.quest = QuestDefinition.objects.create(name="Steady Trail", description="Keep making progress.",
            quest_type="collection", target_value=10, duration_days=30, is_system=True)
        QuestRewardItem.objects.create(quest_definition=self.quest, item=self.frame)

    def test_locked_collectible_names_its_guaranteed_challenge(self):
        response = self.client.get("/api/cosmetics/catalog/")
        self.assertEqual(response.status_code, 200)
        row = response.data["active_frame"][0]
        self.assertIn({"kind": "challenge", "name": "Steady Trail", "path": "/quests?tab=trials"},
            row.get("acquisition_sources", []))

    def test_private_shop_sources_stay_inside_the_family(self):
        from apps.families.models import Family
        other = Family.objects.create(name="Other source family", slug="other-source-family")
        Reward.objects.create(name="Other secret reward", cost_coins=10, family=other,
            fulfillment_kind="digital_item", item_definition=self.frame)
        Reward.objects.create(name="Our frame reward", cost_coins=10, family=self.user.family,
            fulfillment_kind="digital_item", item_definition=self.frame)
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        names = [source["name"] for source in row.get("acquisition_sources", [])]
        self.assertIn("Our frame reward", names)
        self.assertNotIn("Other secret reward", names)

    def test_saved_goal_hint_keeps_its_accepted_reward_after_catalog_edit(self):
        from apps.quests.models import ChallengeGoal
        ChallengeGoal.objects.create(user=self.user, family=self.user.family,
            catalog_definition=self.quest, is_catalog=True, name=self.quest.name,
            metric="count", target=10, timezone_name="America/Phoenix",
            starts_at=timezone.now(), ends_at=timezone.now() + timedelta(days=30),
            reward_items=[{"item_id": self.frame.pk, "quantity": 1}])
        replacement = ItemDefinition.objects.create(name="Replacement frame", item_type="cosmetic_frame")
        self.quest.reward_items.all().delete()
        QuestRewardItem.objects.create(quest_definition=self.quest, item=replacement)
        rows = {row["id"]: row for row in self.client.get("/api/cosmetics/catalog/").data["active_frame"]}
        self.assertTrue(any(source["name"] == self.quest.name for source in rows[self.frame.pk]["acquisition_sources"]))
        self.assertFalse(any(source["name"] == self.quest.name for source in rows[replacement.pk]["acquisition_sources"]))

    def test_reward_only_trigger_is_not_advertised_as_an_automatic_goal(self):
        self.quest.trigger_filter = {"allowed_triggers": ["badge_earned"]}
        self.quest.save()
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [])

    def test_retained_alias_does_not_advertise_a_second_challenge(self):
        alias = QuestDefinition.objects.create(
            name="Retained duplicate", quest_type="collection", target_value=10,
            is_system=True, superseded_by=self.quest,
        )
        QuestRewardItem.objects.create(quest_definition=alias, item=self.frame)
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual([source["name"] for source in row["acquisition_sources"]], [self.quest.name])

    def test_unassigned_family_campaign_is_not_an_individual_acquisition_offer(self):
        self.quest.is_cooperative = True
        self.quest.save(update_fields=["is_cooperative"])
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [])

    def test_current_occurrence_uses_its_frozen_item_list(self):
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence
        now = timezone.now()
        goal = ChallengeGoal.objects.create(user=self.user, family=self.user.family,
            catalog_definition=self.quest, is_catalog=True, name=self.quest.name,
            metric="count", target=10, timezone_name="America/Phoenix", starts_at=now,
            ends_at=now + timedelta(days=30), reward_items=[{"item_id": self.frame.pk, "quantity": 1}])
        ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at,
            ends_at=goal.ends_at, snapshot={"items": []})
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [])

    def test_expired_or_completed_nonrepeatable_goal_is_not_advertised(self):
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence
        now = timezone.now()
        goal = ChallengeGoal.objects.create(user=self.user, family=self.user.family,
            catalog_definition=self.quest, is_catalog=True, name=self.quest.name,
            metric="count", target=10, timezone_name="America/Phoenix", starts_at=now - timedelta(days=31),
            ends_at=now - timedelta(days=1), reward_items=[{"item_id": self.frame.pk, "quantity": 1}])
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [])
        goal.ends_at = now + timedelta(days=2)
        goal.save()
        ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at,
            ends_at=goal.ends_at, status="completed", awarded_at=now)
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [])

    def test_active_retried_goal_remains_an_item_acquisition_source(self):
        from apps.quests.controls import retry_challenge
        from apps.quests.goals import list_goals
        from apps.quests.models import ChallengeOccurrence

        now = timezone.now()
        with patch("django.utils.timezone.now", return_value=now - timedelta(days=10)):
            definition = QuestDefinition.objects.create(
                name="Two-day chore trail", quest_type="collection", target_value=2,
                duration_days=2, is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            QuestRewardItem.objects.create(quest_definition=definition, item=self.frame)
            list_goals(self.user)
        original = ChallengeOccurrence.objects.get(goal__catalog_definition=definition)
        self.assertLess(original.goal.ends_at, now)
        with patch("django.utils.timezone.now", return_value=now):
            retry, created = retry_challenge(self.user, original.pk)
            response = self.client.get("/api/cosmetics/catalog/")
        self.assertTrue(created)
        self.assertEqual(retry.status, "active")
        self.assertIsNone(retry.awarded_at)
        self.assertGreater(retry.ends_at, now)
        self.assertEqual(response.status_code, 200)
        frame = next(row for row in response.data["active_frame"] if row["id"] == self.frame.pk)
        self.assertIn(
            {"kind": "challenge", "name": definition.name, "path": "/quests?tab=trials"},
            frame["acquisition_sources"],
        )
        replacement = ItemDefinition.objects.create(name="Changed future frame", item_type="cosmetic_frame")
        definition.reward_items.all().delete()
        QuestRewardItem.objects.create(quest_definition=definition, item=replacement)
        rows = {row["id"]: row for row in self.client.get("/api/cosmetics/catalog/").data["active_frame"]}
        self.assertTrue(any(source["name"] == definition.name for source in rows[self.frame.pk]["acquisition_sources"]))
        self.assertFalse(any(source["name"] == definition.name for source in rows[replacement.pk]["acquisition_sources"]))
        retry.status = "closed"
        retry.closed_reason = "reward_already_awarded"
        retry.save(update_fields=["status", "closed_reason"])
        frame = next(row for row in self.client.get("/api/cosmetics/catalog/").data["active_frame"]
                     if row["id"] == self.frame.pk)
        self.assertFalse(any(source["name"] == definition.name for source in frame["acquisition_sources"]))

    def test_hints_are_batched_and_catalog_reads_create_no_progress(self):
        from apps.quests.models import ChallengeGoal
        with CaptureQueriesContext(connection) as first:
            self.client.get("/api/cosmetics/catalog/")
        ItemDefinition.objects.bulk_create([
            ItemDefinition(name=f"Extra frame {index}", item_type="cosmetic_frame")
            for index in range(40)
        ])
        with CaptureQueriesContext(connection) as expanded:
            self.client.get("/api/cosmetics/catalog/")
        self.assertLessEqual(len(expanded), len(first) + 1)
        self.assertEqual(ChallengeGoal.objects.filter(user=self.user).count(), 0)

    def test_untimed_saved_window_keeps_frozen_item_hint_after_long_absence(self):
        from apps.quests.models import ChallengeGoal, ChallengeOccurrence
        now = timezone.now()
        self.quest.duration_days = None
        self.quest.trigger_filter = {"allowed_triggers": ["reading_logged"]}
        self.quest.save()
        goal = ChallengeGoal.objects.create(user=self.user, family=self.user.family,
            catalog_definition=self.quest, is_catalog=True, name=self.quest.name,
            metric="count", target=10, timezone_name="America/Phoenix",
            starts_at=now - timedelta(days=1000), ends_at=None,
            reward_items=[{"item_id": self.frame.pk, "quantity": 1}])
        occurrence = ChallengeOccurrence.objects.create(goal=goal, starts_at=goal.starts_at,
            ends_at=None, snapshot={"items": [{"item_id": self.frame.pk, "quantity": 1}]})
        self.quest.reward_items.all().delete()
        row = self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]
        self.assertEqual(row["acquisition_sources"], [{"kind": "challenge", "name": goal.name,
                                                      "path": "/quests?tab=trials"}])
        occurrence.status = "completed"
        occurrence.awarded_at = now
        occurrence.save()
        self.assertEqual(self.client.get("/api/cosmetics/catalog/").data["active_frame"][0]["acquisition_sources"], [])
