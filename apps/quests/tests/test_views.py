"""Tests for quest views — active, available, start, history, catalog, create."""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant


class _Fixture(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="p", password="pw", role="parent")
        self.child = User.objects.create_user(username="c", password="pw", role="child")
        self.client = APIClient()
        self.definition = QuestDefinition.objects.create(
            name="Slay Dragon", description="Beat the boss",
            quest_type="boss", target_value=100,
            duration_days=7, coin_reward=50, xp_reward=100,
        )


class ActiveQuestTests(_Fixture):
    def test_no_active_quest_returns_null(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/quests/active/")
        self.assertEqual(resp.status_code, 200)
        # Response body is null/empty when no active quest.
        self.assertFalse(resp.data)

    def test_active_quest_returned(self):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() + timezone.timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/quests/active/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.json())


class StartQuestTests(_Fixture):
    def test_start_quest(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/quests/start/", {
            "definition_id": self.definition.pk,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(
            Quest.objects.filter(
                definition=self.definition, status="active",
            ).exists()
        )

    def test_start_quest_while_one_active_fails(self):
        quest = Quest.objects.create(
            definition=self.definition, status="active",
            end_date=timezone.now() + timezone.timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/quests/start/", {
            "definition_id": self.definition.pk,
        }, format="json")
        self.assertIn(resp.status_code, (400, 409))


class QuestHistoryTests(_Fixture):
    def test_returns_completed_quests(self):
        quest = Quest.objects.create(
            definition=self.definition, status="completed",
            end_date=timezone.now() + timezone.timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/quests/history/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)


class QuestCatalogTests(_Fixture):
    def test_parent_sees_catalog(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.get("/api/quests/catalog/")
        self.assertEqual(resp.status_code, 200)

    def test_child_denied_catalog(self):
        self.client.force_authenticate(self.child)
        resp = self.client.get("/api/quests/catalog/")
        self.assertEqual(resp.status_code, 403)


class CreateQuestTests(_Fixture):
    def test_parent_creates_quest_definition(self):
        self.client.force_authenticate(self.parent)
        resp = self.client.post("/api/quests/", {
            "name": "Read 5 books",
            "description": "Collection quest",
            "quest_type": "collection",
            "target_value": 5,
            "coin_reward": 30,
            "xp_reward": 50,
        }, format="json")
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(QuestDefinition.objects.filter(name="Read 5 books").exists())

    def test_child_cannot_create_quest(self):
        self.client.force_authenticate(self.child)
        resp = self.client.post("/api/quests/", {
            "name": "Hack",
            "description": "...",
            "quest_type": "boss",
            "target_value": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 403)
