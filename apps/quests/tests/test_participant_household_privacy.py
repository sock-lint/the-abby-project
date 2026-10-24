"""Saved co-op work does not expose a departed member's new household name."""
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.serializers import QuestSerializer
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ParticipantHouseholdPrivacyTests(TestCase):
    def setUp(self):
        own = make_family("Original co-op household", parents=[
            {"username": "participant-old-parent", "is_staff": True},
        ], children=[
            {"username": "participant-staying", "display_name": "Staying shared name"},
            {"username": "participant-moving", "display_name": "Original shared name"},
        ])
        other = make_family("New co-op household", parents=[
            {"username": "participant-new-parent", "is_staff": True},
        ])
        self.parent, self.other_parent = own.parents[0], other.parents[0]
        self.staying, self.moving = own.children
        definition = QuestDefinition.objects.create(name="Saved shared practice", is_system=True,
            is_cooperative=True, quest_type="collection", target_value=10)
        self.quest = Quest.objects.create(definition=definition,
            end_date=timezone.now() + timedelta(days=2), reward_items_snapshot=[], current_progress=7)
        QuestParticipant.objects.create(quest=self.quest, user=self.staying, contribution=5)
        QuestParticipant.objects.create(quest=self.quest, user=self.moving, contribution=2)

    def wire(self, name, params, *, actor=None):
        with override_user(actor or self.parent, scopes=frozenset({"mcp:read"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params})
        if isinstance(result, tuple):
            return result[1]
        self.assertFalse(result.isError, result.structuredContent)
        return result.structuredContent

    def move_and_rename(self):
        self.moving.family = self.other_parent.family
        self.moving.save(update_fields=["family"])
        client = APIClient()
        client.force_authenticate(self.other_parent)
        response = client.patch(f"/api/children/{self.moving.pk}/",
            {"display_name": "Private new household name"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def assert_private_participants(self, rows, *, observer_new_family=False):
        by_id = {row["user"]: row for row in rows}
        self.assertEqual(set(by_id), {self.staying.pk, self.moving.pk})
        self.assertEqual(by_id[self.staying.pk]["contribution"], 5)
        self.assertEqual(by_id[self.moving.pk]["contribution"], 2)
        if observer_new_family:
            self.assertEqual(by_id[self.moving.pk]["user_name"], "Private new household name")
            self.assertEqual(by_id[self.staying.pk]["user_name"], "Former participant")
        else:
            self.assertEqual(by_id[self.staying.pk]["user_name"], "Staying shared name")
            self.assertEqual(by_id[self.moving.pk]["user_name"], "Former participant")

    def test_registered_mcp_challenge_and_quest_reads_mask_departed_current_label(self):
        before = self.wire("get_challenge", {"user_id": self.staying.pk,
            "challenge_id": f"legacy:{self.quest.pk}"})
        self.assertIn("Original shared name", [row["user_name"] for row in before["participants"]])
        self.move_and_rename()
        cases = [
            ("get_challenge", {"user_id": self.staying.pk, "challenge_id": f"legacy:{self.quest.pk}"},
                lambda data: data["participants"]),
            ("list_challenges", {"user_id": self.staying.pk, "source": "legacy"},
                lambda data: next(row for row in data["results"] if row["id"] == f"legacy:{self.quest.pk}")["participants"]),
            ("get_quest", {"quest_id": self.quest.pk}, lambda data: data["participants"]),
            ("list_quests", {"user_id": self.staying.pk}, lambda data: data["quests"][0]["participants"]),
        ]
        for name, params, participants in cases:
            with self.subTest(tool=name):
                self.assert_private_participants(participants(self.wire(name, params)))

    def test_native_active_history_and_challenges_apply_same_household_boundary(self):
        self.move_and_rename()
        client = APIClient()
        client.force_authenticate(self.staying)
        for path in ("/api/quests/active/", "/api/challenges/", "/api/pulse/"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, response.data)
                if path.endswith("active/"):
                    payload = response.data
                elif path.endswith("pulse/"):
                    payload = response.data["active_quest"]
                else:
                    payload = next(row for row in response.data["results"] if row["id"] == f"legacy:{self.quest.pk}")
                self.assert_private_participants(payload["participants"])
        self.quest.status = "completed"
        self.quest.save(update_fields=["status"])
        history = client.get("/api/quests/history/")
        self.assertEqual(history.status_code, 200, history.data)
        self.assert_private_participants(history.data[0]["participants"])

        client.force_authenticate(self.parent)
        self.quest.status = "active"
        self.quest.save(update_fields=["status"])
        family = client.get("/api/quests/family/")
        self.assertEqual(family.status_code, 200, family.data)
        saved = next(row["quest"] for row in family.data["results"] if row["child_id"] == self.staying.pk)
        self.assert_private_participants(saved["participants"])

    def test_new_household_reads_keep_own_label_and_mask_previous_household(self):
        self.move_and_rename()
        payload = self.wire("get_quest", {"quest_id": self.quest.pk}, actor=self.other_parent)
        self.assert_private_participants(payload["participants"], observer_new_family=True)
        client = APIClient()
        client.force_authenticate(self.moving)
        native = client.get("/api/quests/active/")
        self.assertEqual(native.status_code, 200, native.data)
        self.assert_private_participants(native.data["participants"], observer_new_family=True)

    def test_same_household_renames_remain_visible_and_contributions_unchanged(self):
        self.moving.display_name = "Updated shared name"
        self.moving.save(update_fields=["display_name"])
        payload = self.wire("get_quest", {"quest_id": self.quest.pk})
        self.assertIn("Updated shared name", [row["user_name"] for row in payload["participants"]])
        self.assertEqual([(row["user"], row["contribution"]) for row in payload["participants"]],
            [(self.staying.pk, 5), (self.moving.pk, 2)])

    def test_serializer_without_observer_fails_closed_for_mixed_households(self):
        self.move_and_rename()
        payload = QuestSerializer(Quest.objects.get(pk=self.quest.pk)).data
        self.assertEqual([row["user_name"] for row in payload["participants"]],
            ["Former participant", "Former participant"])
