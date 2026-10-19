"""Private quest definitions cannot offer another household's rewards."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPNotFoundError
from apps.mcp_server.schemas import AssignCoOpQuestIn, AssignQuestIn, CreateQuestDefinitionIn
from apps.mcp_server.tools import quests as quest_tools
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class QuestFamilyBoundaryTests(TestCase):
    def setUp(self):
        self.home = make_family("Quest home", parents=[{"username": "quest-home-parent"}],
                                children=[{"username": "quest-home-child"}, {"username": "quest-home-sibling"}])
        self.other = make_family("Quest other", parents=[{"username": "quest-other-parent"}],
                                 children=[{"username": "quest-other-child"}])
        self.parent, self.child = self.home.parents[0], self.home.children[0]
        self.private = QuestDefinition.objects.create(
            name="Private family promise", description="Private household details",
            quest_type="collection", target_value=1, coin_reward=1_000_000,
            created_by=self.other.parents[0],
        )
        self.own = QuestDefinition.objects.create(
            name="Our promise", quest_type="collection", target_value=1, created_by=self.parent,
        )
        self.system = QuestDefinition.objects.create(
            name="Shared catalog", quest_type="collection", target_value=1, is_system=True,
        )
        self.client = APIClient()

    def test_guessed_private_id_cannot_start_or_pay_large_foreign_promise(self):
        self.client.force_authenticate(self.child)
        response = self.client.post("/api/quests/start/", {"definition_id": self.private.pk}, format="json")
        # Exercising progress also demonstrates that a rejected start has no
        # campaign available to turn a foreign parent's promise into Coins.
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"error": "Quest not found"})
        self.assertIsNone(result)
        self.assertFalse(Quest.objects.exists())
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_parent_catalog_contains_only_system_and_own_family_definitions(self):
        self.client.force_authenticate(self.parent)
        response = self.client.get("/api/quests/catalog/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data}, {self.own.pk, self.system.pk})

    def test_rejected_foreign_start_does_not_consume_a_quest_scroll(self):
        scroll = ItemDefinition.objects.create(slug="family-quest-scroll", name="Quest scroll", item_type="quest_scroll")
        inventory = UserInventory.objects.create(user=self.child, item=scroll, quantity=2)
        self.client.force_authenticate(self.child)
        response = self.client.post("/api/quests/start/", {
            "definition_id": self.private.pk, "scroll_item_id": scroll.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        inventory.refresh_from_db()
        self.assertEqual(inventory.quantity, 2)
        self.assertFalse(Quest.objects.exists())

    def test_parent_cannot_assign_foreign_definition_solo_or_coop(self):
        self.client.force_authenticate(self.parent)
        for route, payload in (
            ("assign", {"user_id": self.child.pk}),
            ("co-op", {"user_ids": [child.pk for child in self.home.children]}),
        ):
            with self.subTest(route=route):
                response = self.client.post(f"/api/quests/{self.private.pk}/{route}/", payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"error": "Quest not found"})
        self.assertFalse(Quest.objects.exists())

    def test_shared_service_rejects_foreign_definition_and_mixed_family_coop(self):
        with self.assertRaisesMessage(ValueError, "Quest not found"):
            QuestService.start_quest(self.child, self.private.pk)
        with self.assertRaisesMessage(ValueError, "Quest not found"):
            QuestService.start_co_op_quest(self.private.pk, self.home.children)
        with self.assertRaisesMessage(ValueError, "same family"):
            QuestService.start_co_op_quest(self.system.pk, [self.child, self.other.children[0]])
        self.assertFalse(Quest.objects.exists())

    def test_mcp_assignment_has_not_found_semantics_for_foreign_definition(self):
        with override_user(self.parent):
            with self.assertRaises(MCPNotFoundError):
                quest_tools.assign_quest(AssignQuestIn(user_id=self.child.pk, definition_id=self.private.pk))
            with self.assertRaises(MCPNotFoundError):
                quest_tools.assign_co_op_quest(AssignCoOpQuestIn(
                    user_ids=[child.pk for child in self.home.children], definition_id=self.private.pk,
                ))
        self.assertFalse(Quest.objects.exists())

    def test_same_family_and_system_definitions_remain_startable(self):
        first = QuestService.start_quest(self.child, self.own.pk)
        first.status = Quest.Status.FAILED
        first.save(update_fields=["status", "updated_at"])
        self.assertEqual(QuestService.start_quest(self.child, self.system.pk).definition_id, self.system.pk)

    def test_same_family_parent_keeps_control_of_its_own_reward_amount(self):
        self.own.coin_reward = 1_000_000
        self.own.save(update_fields=["coin_reward", "updated_at"])
        QuestService.start_quest(self.child, self.own.pk)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertEqual(result["rewards"]["coins"], 1_000_000)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [1_000_000])

    def test_mcp_name_validation_does_not_expose_private_other_family_names(self):
        with override_user(self.parent):
            result = quest_tools.create_quest_definition(CreateQuestDefinitionIn(
                name=self.private.name, description="Our own household promise", quest_type="collection", target_value=1,
            ))
        self.assertEqual(result["definition"]["name"], self.private.name)
        self.assertEqual(QuestDefinition.objects.filter(name=self.private.name).count(), 2)

    def test_deleted_author_does_not_make_private_definition_public(self):
        self.other.parents[0].delete()
        with self.assertRaisesMessage(ValueError, "Quest not found"):
            QuestService.start_quest(self.child, self.private.pk)

    def test_existing_foreign_campaign_cannot_progress_or_pay(self):
        # Simulate a campaign accepted through the former unscoped start.
        quest = Quest.objects.create(definition=self.private, end_date=timezone.now() + timedelta(days=1))
        participant = QuestParticipant.objects.create(quest=quest, user=self.child)
        result = QuestService.record_progress(self.child, "chore_complete")
        self.assertIsNone(result)
        quest.refresh_from_db()
        participant.refresh_from_db()
        self.assertEqual((quest.status, quest.current_progress, participant.contribution), ("active", 0, 0))
        with self.assertRaisesMessage(ValueError, "Quest not found"):
            QuestService._complete_quest(quest, self.child)
        self.assertFalse(CoinLedger.objects.filter(user=self.child).exists())

    def test_valid_saved_campaign_keeps_its_promise_after_author_deletion(self):
        co_parent = self.home.parents[0]
        self.own.coin_reward = 7
        self.own.save(update_fields=["coin_reward", "updated_at"])
        quest = QuestService.start_quest(self.child, self.own.pk)
        # Direct model deletion also covers historical SET_NULL ownership.
        co_parent.delete()
        self.assertTrue(QuestService.record_progress(self.child, "chore_complete")["completed"])
        quest.refresh_from_db()
        self.assertEqual(quest.status, "completed")
        self.assertEqual(list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)), [7])
