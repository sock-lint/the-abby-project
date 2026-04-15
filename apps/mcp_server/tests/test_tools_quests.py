"""Tests for Tier-2.2 quest authoring MCP tools."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)
from apps.mcp_server.schemas import (
    AssignQuestIn,
    CancelQuestIn,
    CreateQuestDefinitionIn,
    GetQuestIn,
    ListQuestCatalogIn,
    ListQuestsIn,
)
from apps.mcp_server.tools import quests as q
from apps.projects.models import User
from apps.quests.models import Quest, QuestDefinition, QuestParticipant


class _Base(TestCase):
    def setUp(self) -> None:
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )


class CatalogAndCreateTests(_Base):
    def test_create_definition_without_assignment(self) -> None:
        with override_user(self.parent):
            r = q.create_quest_definition(CreateQuestDefinitionIn(
                name="Slay the bug",
                description="Fix 5 bugs.",
                quest_type="collection",
                target_value=5,
            ))
        self.assertIsNone(r["quest"])
        self.assertEqual(r["definition"]["name"], "Slay the bug")
        self.assertEqual(QuestDefinition.objects.count(), 1)

    def test_create_definition_with_auto_assignment(self) -> None:
        with override_user(self.parent):
            r = q.create_quest_definition(CreateQuestDefinitionIn(
                name="Boss",
                description="d",
                quest_type="boss",
                target_value=500,
                assigned_to_id=self.child.id,
            ))
        self.assertIsNotNone(r["quest"])
        self.assertEqual(
            Quest.objects.filter(participants__user=self.child).count(), 1,
        )

    def test_duplicate_name_rejected(self) -> None:
        QuestDefinition.objects.create(
            name="Taken", description="", quest_type="boss", target_value=10,
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            q.create_quest_definition(CreateQuestDefinitionIn(
                name="Taken", description="", quest_type="boss",
                target_value=1,
            ))

    def test_catalog_parent_only(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            q.list_quest_catalog(ListQuestCatalogIn())

    def test_catalog_filter_by_type(self) -> None:
        QuestDefinition.objects.create(
            name="Boss1", description="", quest_type="boss", target_value=1,
        )
        QuestDefinition.objects.create(
            name="Coll1", description="", quest_type="collection",
            target_value=1,
        )
        with override_user(self.parent):
            bosses = q.list_quest_catalog(
                ListQuestCatalogIn(quest_type="boss"),
            )
        self.assertEqual(len(bosses["quest_definitions"]), 1)
        self.assertEqual(bosses["quest_definitions"][0]["name"], "Boss1")


class AssignQuestTests(_Base):
    def test_assign_to_child(self) -> None:
        defn = QuestDefinition.objects.create(
            name="D", description="", quest_type="boss", target_value=100,
        )
        with override_user(self.parent):
            r = q.assign_quest(AssignQuestIn(
                definition_id=defn.id, user_id=self.child.id,
            ))
        self.assertEqual(r["status"], "active")

    def test_cannot_assign_second_active_quest(self) -> None:
        defn1 = QuestDefinition.objects.create(
            name="D1", description="", quest_type="boss", target_value=100,
        )
        defn2 = QuestDefinition.objects.create(
            name="D2", description="", quest_type="boss", target_value=100,
        )
        with override_user(self.parent):
            q.assign_quest(AssignQuestIn(
                definition_id=defn1.id, user_id=self.child.id,
            ))
            with self.assertRaises(MCPValidationError):
                q.assign_quest(AssignQuestIn(
                    definition_id=defn2.id, user_id=self.child.id,
                ))

    def test_child_cannot_assign(self) -> None:
        defn = QuestDefinition.objects.create(
            name="D", description="", quest_type="boss", target_value=1,
        )
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            q.assign_quest(AssignQuestIn(
                definition_id=defn.id, user_id=self.child.id,
            ))


class ListAndGetTests(_Base):
    def _make_quest(self, for_user) -> Quest:
        defn = QuestDefinition.objects.create(
            name=f"for-{for_user.id}",
            description="",
            quest_type="boss",
            target_value=100,
        )
        now = timezone.now()
        quest = Quest.objects.create(
            definition=defn,
            start_date=now,
            end_date=now + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=for_user)
        return quest

    def test_child_sees_only_own_quests(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        mine = self._make_quest(self.child)
        _theirs = self._make_quest(other)
        with override_user(self.child):
            r = q.list_quests(ListQuestsIn())
        ids = [x["id"] for x in r["quests"]]
        self.assertEqual(ids, [mine.id])

    def test_get_quest_denied_for_non_participant(self) -> None:
        other = User.objects.create_user(
            username="o", password="pw", role="child",
        )
        quest = self._make_quest(other)
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            q.get_quest(GetQuestIn(quest_id=quest.id))


class CancelQuestTests(_Base):
    def test_cancel_active(self) -> None:
        defn = QuestDefinition.objects.create(
            name="X", description="", quest_type="boss", target_value=100,
        )
        now = timezone.now()
        quest = Quest.objects.create(
            definition=defn, start_date=now, end_date=now + timedelta(days=7),
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        with override_user(self.parent):
            r = q.cancel_quest(CancelQuestIn(quest_id=quest.id))
        self.assertEqual(r["status"], "failed")

    def test_cannot_cancel_completed(self) -> None:
        defn = QuestDefinition.objects.create(
            name="X", description="", quest_type="boss", target_value=100,
        )
        now = timezone.now()
        quest = Quest.objects.create(
            definition=defn,
            start_date=now,
            end_date=now + timedelta(days=7),
            status=Quest.Status.COMPLETED,
        )
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            q.cancel_quest(CancelQuestIn(quest_id=quest.id))
