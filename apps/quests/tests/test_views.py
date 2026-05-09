"""Tests for quest views — active, available, start, history, catalog, create, co-op."""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from config.tests.factories import make_family


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


class StartCoOpQuestViewTests(TestCase):
    """POST /api/quests/{definition_id}/co-op/ — parent-only family-scoped fanout."""
    def setUp(self):
        self.fam_a = make_family(
            "Alpha",
            parents=[{"username": "alpha_parent"}],
            children=[{"username": "alpha_a"}, {"username": "alpha_b"}],
        )
        self.fam_b = make_family(
            "Bravo",
            parents=[{"username": "bravo_parent"}],
            children=[{"username": "bravo_kid"}],
        )
        self.definition = QuestDefinition.objects.create(
            name="Co-op Boss",
            description="Tag-team",
            quest_type="boss",
            target_value=200,
            duration_days=7,
            coin_reward=80,
            xp_reward=120,
        )
        self.client = APIClient()

    def _start_url(self):
        return f"/api/quests/{self.definition.pk}/co-op/"

    def test_parent_starts_co_op_for_two_same_family_children(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.post(
            self._start_url(),
            {"user_ids": [self.fam_a.children[0].pk, self.fam_a.children[1].pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        # One Quest, two participants — co-op shape.
        quest = Quest.objects.get(definition=self.definition, status="active")
        self.assertEqual(
            QuestParticipant.objects.filter(quest=quest).count(),
            2,
        )

    def test_child_caller_forbidden(self):
        self.client.force_authenticate(self.fam_a.children[0])
        resp = self.client.post(
            self._start_url(),
            {"user_ids": [self.fam_a.children[0].pk, self.fam_a.children[1].pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_too_few_user_ids_returns_400(self):
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.post(
            self._start_url(),
            {"user_ids": [self.fam_a.children[0].pk]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cross_family_user_id_returns_404_no_leak(self):
        """A parent in family Alpha cannot start a co-op quest for a child in family Bravo.

        Existence-leak prevention: the response must be the same 404 whether the
        user_id is real-but-cross-family or completely bogus. ``get_child_or_404``
        with ``requesting_user=`` enforces this at chokepoint (3).
        """
        self.client.force_authenticate(self.fam_a.parents[0])
        resp = self.client.post(
            self._start_url(),
            {
                "user_ids": [
                    self.fam_a.children[0].pk,
                    self.fam_b.children[0].pk,  # cross-family
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        # No quest got created — atomic.
        self.assertFalse(
            Quest.objects.filter(definition=self.definition, status="active").exists()
        )
