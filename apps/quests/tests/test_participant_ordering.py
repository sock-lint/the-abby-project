"""Shared challenge wire order is independent of database/prefetch row order."""
from datetime import timedelta

from django.db.models import Prefetch
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.quests.goals import _legacy_payload
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.serializers import QuestSerializer
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParticipantOrderingTests(TestCase):
    def setUp(self):
        household = make_family("Stable shared participants", children=[
            {"username": "ordered-first"}, {"username": "ordered-second"}, {"username": "ordered-third"},
        ])
        definition = QuestDefinition.objects.create(
            name="Stable family challenge", description="Saved pooled work", quest_type="collection",
            target_value=6, is_system=True, is_cooperative=True,
        )
        quest = Quest.objects.create(
            definition=definition, status="completed", current_progress=6,
            end_date=timezone.now() + timedelta(days=1), reward_items_snapshot=[],
        )
        self.user_ids = [child.pk for child in household.children]
        self.expected = [(user_id, 2) for user_id in self.user_ids]
        for child_id, contribution in reversed(self.expected):
            QuestParticipant.objects.create(quest=quest, user_id=child_id, contribution=contribution)
        self.quest = self.prefetched_quest(quest.pk)
        self.assert_reverse_prefetch()

    def prefetched_quest(self, quest_id):
        return Quest.objects.select_related("definition").prefetch_related(
            Prefetch("participants", queryset=QuestParticipant.objects.select_related("user").order_by("-user_id", "-pk")),
            "definition__reward_items__item", "definition__skill_tags__skill__category",
        ).get(pk=quest_id)

    def unequal_contributions(self):
        contributions = [(self.user_ids[0], 3), (self.user_ids[1], 0), (self.user_ids[2], 3)]
        for user_id, contribution in contributions:
            QuestParticipant.objects.filter(quest=self.quest, user_id=user_id).update(contribution=contribution)
        self.expected = sorted(contributions, key=lambda row: (-row[1], row[0]))
        self.quest = self.prefetched_quest(self.quest.pk)
        self.assert_reverse_prefetch()

    def assert_reverse_prefetch(self):
        self.assertEqual(
            [row.user_id for row in self.quest._prefetched_objects_cache["participants"]],
            list(reversed(self.user_ids)),
        )

    def test_legacy_goal_projection_sorts_participants_without_queries_or_cache_mutation(self):
        with self.assertNumQueries(0):
            payload = _legacy_payload(self.quest, None, item_catalog={})
        self.assertEqual([(row["user"], row["contribution"]) for row in payload["participants"]], self.expected)
        self.assert_reverse_prefetch()

    def test_quest_serializer_sorts_participants_without_queries_or_cache_mutation(self):
        with self.assertNumQueries(0):
            payload = QuestSerializer(self.quest).data
        self.assertEqual([(row["user"], row["contribution"]) for row in payload["participants"]], self.expected)
        self.assert_reverse_prefetch()

    def test_legacy_goal_preserves_contribution_ranking_with_stable_user_ties(self):
        self.unequal_contributions()
        with self.assertNumQueries(0):
            payload = _legacy_payload(self.quest, None, item_catalog={})
        self.assertEqual([(row["user"], row["contribution"]) for row in payload["participants"]], self.expected)
        self.assert_reverse_prefetch()

    def test_quest_serializer_preserves_contribution_ranking_with_stable_user_ties(self):
        self.unequal_contributions()
        with self.assertNumQueries(0):
            payload = QuestSerializer(self.quest).data
        self.assertEqual([(row["user"], row["contribution"]) for row in payload["participants"]], self.expected)
        self.assert_reverse_prefetch()
