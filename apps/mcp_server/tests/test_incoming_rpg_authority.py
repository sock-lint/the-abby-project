"""A household operation cannot adopt members who joined after its lock batch."""
from contextlib import contextmanager
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from apps.mcp_server import legacy_household
from apps.quests.models import Quest, QuestDefinition, QuestParticipant
from apps.rewards.models import CoinLedger, Reward
from apps.rewards.services import CoinService, RewardService
from apps.rpg.models import ItemDefinition, UserInventory

from . import test_remaining_rpg_authority as fixtures


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   MCP_RESOURCE_URL="http://synthetic.invalid/mcp")
class IncomingRPGAuthorityTests(TestCase):
    wire = fixtures.RemainingRPGAuthorityTests.wire
    assert_error = fixtures.RemainingRPGAuthorityTests.assert_error

    def setUp(self):
        fixtures.RemainingRPGAuthorityTests.setUp(self)
        self.foreign_parent = get_user_model().objects.create_user(
            username="incoming-author", role="parent", family=self.other_family,
        )
        self.private_definition = QuestDefinition.objects.create(
            name="Incoming private quest", description="Private incoming description", quest_type="boss",
            target_value=100, created_by=self.foreign_parent, is_system=False,
        )
        self.foreign_quest = Quest.objects.create(definition=self.private_definition,
                                                end_date=timezone.now() + timedelta(days=7))
        QuestParticipant.objects.create(quest=self.foreign_quest, user=self.foreign, contribution=3)
        self.food = ItemDefinition.objects.create(slug="incoming-safe-food", name="Saved food", item_type="food")
        reward = Reward.objects.create(family=self.other_family, name="Incoming saved promise", cost_coins=5,
            fulfillment_kind="digital_item", item_definition=self.food, requires_parent_approval=True)
        CoinService.award_coins(self.foreign, 50, CoinLedger.Reason.ADJUSTMENT)
        self.foreign_redemption = RewardService.request_redemption(self.foreign, reward)

    @contextmanager
    def join_after_batch(self, *members):
        original = legacy_household.authorized_household

        @contextmanager
        def admitted(*args, **kwargs):
            with original(*args, **kwargs) as selected:
                get_user_model().objects.filter(pk__in=[member.pk for member in members]).update(
                    family=self.parent.family,
                )
                yield selected

        with patch.object(legacy_household, "authorized_household", admitted):
            yield

    def test_redemption_entry_does_not_adopt_a_late_joiner(self):
        before = list(CoinLedger.objects.values())
        with self.join_after_batch(self.foreign):
            self.assert_error(self.wire("approve_redemption", {"redemption_id": self.foreign_redemption.pk}), "not_found")
        self.assertFalse(UserInventory.objects.filter(user=self.foreign).exists())
        self.foreign_redemption.refresh_from_db()
        self.assertEqual(self.foreign_redemption.status, "pending")
        self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_foreign_entry_remains_hidden_without_mutating_saved_promise(self):
        before = list(CoinLedger.objects.values())
        self.assert_error(self.wire("approve_redemption", {"redemption_id": self.foreign_redemption.pk}), "not_found")
        self.assertFalse(UserInventory.objects.filter(user=self.foreign).exists())
        self.foreign_redemption.refresh_from_db()
        self.assertEqual(self.foreign_redemption.status, "pending")
        self.assertEqual(list(CoinLedger.objects.values()), before)

    def test_quest_entry_and_family_list_do_not_adopt_a_late_joiner(self):
        for name, params in (("get_quest", {"quest_id": self.foreign_quest.pk}), ("list_quests", {}),
                             ("cancel_quest", {"quest_id": self.foreign_quest.pk})):
            with self.subTest(tool=name), self.join_after_batch(self.foreign):
                result = self.wire(name, params)
                if name != "list_quests":
                    self.assert_error(result, "not_found")
                else:
                    self.assertNotIn(self.foreign_quest.pk, {row["id"] for row in result["quests"]})
            get_user_model().objects.filter(pk=self.foreign.pk).update(family=self.other_family)

    def test_private_catalog_and_author_mutations_do_not_adopt_a_late_author(self):
        cases = (("list_quest_catalog", {}),
                 ("set_quest_definition_skill_tags", {"quest_definition_id": self.private_definition.pk, "skill_tags": []}),
                 ("delete_quest_definition", {"quest_definition_id": self.private_definition.pk}))
        for name, params in cases:
            with self.subTest(tool=name), self.join_after_batch(self.foreign_parent):
                result = self.wire(name, params)
                if name == "list_quest_catalog":
                    self.assertNotIn(self.private_definition.pk, {row["id"] for row in result["quest_definitions"]})
                else:
                    self.assert_error(result, "not_found")
            get_user_model().objects.filter(pk=self.foreign_parent.pk).update(family=self.other_family)

    def test_coop_does_not_adopt_a_late_participant(self):
        self.foreign_quest.delete()
        self.quest.delete()
        with self.join_after_batch(self.foreign):
            result = self.wire("assign_co_op_quest", {"definition_id": self.definition.pk,
                                                     "user_ids": [self.child.pk, self.foreign.pk]})
            self.assertIn("error", result, result)
        self.assertFalse(Quest.objects.exists())

    def test_assignment_does_not_adopt_a_late_private_author(self):
        self.quest.delete()
        cases = (("assign_quest", {"definition_id": self.private_definition.pk,
                                   "user_id": self.child.pk}),
                 ("assign_co_op_quest", {"definition_id": self.private_definition.pk,
                                         "user_ids": [self.child.pk, self.sibling.pk]}))
        for name, params in cases:
            with self.subTest(tool=name):
                before = Quest.objects.count()
                with self.join_after_batch(self.foreign_parent):
                    self.assert_error(self.wire(name, params), "not_found")
                self.assertEqual(Quest.objects.count(), before)

                # The same co-author already present before the next batch is
                # a normal household author, and both assignment paths work.
                get_user_model().objects.filter(pk=self.foreign_parent.pk).update(family=self.parent.family)
                result = self.wire(name, params)
                self.assertNotIn("error", result, result)
                assigned = Quest.objects.get(pk=result["id"])
                self.assertEqual(assigned.definition_id, self.private_definition.pk)
                expected = {self.child.pk} if name == "assign_quest" else {self.child.pk, self.sibling.pk}
                self.assertEqual(set(assigned.participants.values_list("user_id", flat=True)), expected)
                assigned.delete()
                get_user_model().objects.filter(pk=self.foreign_parent.pk).update(family=self.other_family)

    def test_shared_participant_labels_outside_batch_remain_masked(self):
        QuestParticipant.objects.create(quest=self.quest, user=self.foreign, contribution=2)
        for params in ({}, {"user_id": self.child.pk}):
            with self.subTest(params=params), self.join_after_batch(self.foreign):
                result = self.wire("list_quests", params)
                row = next(row for row in result["quests"] if row["id"] == self.quest.pk)
                labels = {participant["user"]: participant["user_name"] for participant in row["participants"]}
                self.assertEqual(labels[self.foreign.pk], "Former participant")
                self.assertEqual(labels[self.child.pk], self.child.display_label)
            get_user_model().objects.filter(pk=self.foreign.pk).update(family=self.other_family)

    def test_join_before_next_request_is_admitted_normally(self):
        get_user_model().objects.filter(pk=self.foreign.pk).update(family=self.parent.family)
        result = self.wire("approve_redemption", {"redemption_id": self.foreign_redemption.pk})
        self.assertNotIn("error", result, result)
        self.assertEqual(UserInventory.objects.get(user=self.foreign, item=self.food).quantity, 1)
