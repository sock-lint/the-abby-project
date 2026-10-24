"""Shared catalog goals require parent assignment and pool household effort."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, Quest, QuestDefinition, QuestParticipant
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.validation import validate_content
from apps.rpg.content.workbench_validation import validate_changes
from config.tests.factories import make_family


class CooperativeCatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("loadrpgcontent", pack="content/rpg/initial", stdout=StringIO())
        cls.definition = QuestDefinition.objects.get(name="Family Co-op — Spring Cleaning", is_system=True)
        QuestDefinition.objects.exclude(pk=cls.definition.pk).update(is_system=False)

    def setUp(self):
        self.family = make_family(
            "Shared challenge household", parents=[{"username": "shared-parent"}],
            children=[{"username": "shared-first"}, {"username": "shared-second"}],
        )
        self.parent = self.family.parents[0]
        self.first, self.second = self.family.children
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def _assign(self):
        return self.client.post(
            f"/api/quests/{self.definition.pk}/co-op/",
            {"user_ids": [self.first.pk, self.second.pk]}, format="json",
        )

    def _personal_occurrence(self, *, expired=False, paid=False):
        now = timezone.now()
        start, end = now - timedelta(days=15), now - timedelta(days=1) if expired else now + timedelta(days=1)
        goal = ChallengeGoal.objects.create(
            user=self.first, family=self.family.family, catalog_definition=self.definition, is_catalog=True,
            name=self.definition.name, metric="count", target=20, unit="actions",
            trigger_filter={"allowed_triggers": ["chore_complete"]}, timezone_name="America/Phoenix",
            starts_at=start, ends_at=end, coin_reward=100,
        )
        return ChallengeOccurrence.objects.create(
            goal=goal, starts_at=start, ends_at=end,
            snapshot={"name": goal.name, "description": "Accepted individual promise", "metric": "count",
                      "target": "20", "unit": "actions", "filter": goal.trigger_filter,
                      "coins": 100, "xp": 0, "skill_tags": [], "items": []},
            progress=20 if paid else 7, status="completed" if paid else "active",
            completed_at=now if paid else None, awarded_at=now if paid else None,
            reward_receipt={"coins": 100, "xp": 0, "items": []} if paid else {},
        )

    def test_bundled_shared_goal_does_not_enroll_individually(self):
        for child in self.family.children:
            self.assertEqual(list_goals(child)["results"], [])
        self.assertFalse(ChallengeGoal.objects.filter(catalog_definition=self.definition).exists())

    def test_parent_catalog_exposes_shared_assignment_mode(self):
        response = self.client.get("/api/quests/catalog/")
        self.assertEqual(response.status_code, 200, response.data)
        definition = next(row for row in response.data if row["id"] == self.definition.pk)
        self.assertIs(definition["is_cooperative"], True)

    def test_parent_assigns_after_catalog_read_and_twenty_pooled_chores_pay_each_child_once(self):
        for child in self.family.children:
            list_goals(child)
        response = self._assign()
        self.assertEqual(response.status_code, 201, response.data)
        quest = Quest.objects.get(definition=self.definition)
        self.assertEqual(set(quest.participants.values_list("user_id", flat=True)), {self.first.pk, self.second.pk})
        for child in self.family.children:
            for _ in range(10):
                QuestService.record_progress(child, "chore_complete")
        quest.refresh_from_db()
        self.assertEqual((quest.current_progress, quest.status), (20, "completed"))
        for child in self.family.children:
            self.assertEqual(QuestParticipant.objects.get(quest=quest, user=child).contribution, 10)
            self.assertEqual(list(CoinLedger.objects.filter(
                user=child, description=f"Quest complete: {self.definition.name}",
            ).values_list("amount", flat=True)), [100])
            listed = list_goals(child)["results"]
            self.assertEqual([(row["id"], row["progress"], row["target"], row["status"]) for row in listed],
                             [(f"legacy:{quest.pk}", "20", "20", "completed")])
            self.assertIsNone(QuestService.record_progress(child, "chore_complete"))
        self.assertEqual(self._assign().status_code, 400)
        self.assertEqual(Quest.objects.filter(definition=self.definition).count(), 1)

    def test_shared_catalog_cannot_start_as_a_solo_quest(self):
        with self.assertRaisesMessage(ValueError, "parent"):
            QuestService.start_quest(self.first, self.definition.pk)
        self.assertFalse(Quest.objects.exists())

    def test_internal_shared_start_requires_two_children(self):
        with self.assertRaisesMessage(ValueError, "at least two"):
            QuestService.start_co_op_quest(self.definition.pk, [self.first])
        self.assertFalse(Quest.objects.exists())

    def test_children_cannot_assign_shared_catalog_challenges(self):
        self.client.force_authenticate(self.first)
        self.assertEqual(self._assign().status_code, 403)
        self.assertFalse(Quest.objects.exists())

    def test_shared_catalog_rejects_parent_participants(self):
        with self.assertRaisesMessage(ValueError, "children"):
            QuestService.start_co_op_quest(self.definition.pk, [self.first, self.parent])
        self.assertFalse(Quest.objects.exists())

    def test_active_individual_promise_is_preserved_and_blocks_overlapping_shared_assignment(self):
        occurrence = self._personal_occurrence()
        snapshot = occurrence.snapshot.copy()
        response = self._assign()
        self.assertEqual(response.status_code, 400, response.data)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.snapshot), (Decimal(7), snapshot))
        self.assertFalse(Quest.objects.exists())

    def test_expired_unpaid_one_time_personal_promise_cannot_create_a_second_shared_reward(self):
        occurrence = self._personal_occurrence(expired=True)
        response = self._assign()
        self.assertEqual(response.status_code, 400, response.data)
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.progress, occurrence.awarded_at), (Decimal(7), None))
        self.assertFalse(Quest.objects.exists())

        # A saved fact accepted before expiry can finish its original promise
        # during delayed processing; expiry does not make that reward void.
        for index in range(20):
            ingest_activity(
                self.first, "chore_complete", f"delayed-{index}", "chore_complete",
                occurred_at=occurrence.ends_at - timedelta(minutes=1),
            )
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.status, occurrence.reward_receipt["coins"]), ("completed", 100))
        self.assertEqual(self._assign().status_code, 400)
        self.assertFalse(Quest.objects.exists())

    def test_saved_personal_promise_can_still_finish_without_a_second_shared_payout(self):
        occurrence = self._personal_occurrence()
        for index in range(20):
            ingest_activity(self.first, "chore_complete", f"accepted-{index}", "chore_complete")
        occurrence.refresh_from_db()
        self.assertEqual((occurrence.status, occurrence.reward_receipt["coins"]), ("completed", 100))
        self.assertEqual(self._assign().status_code, 400)
        self.assertFalse(Quest.objects.exists())

    def test_paid_individual_goal_cannot_pay_again_as_a_nonrepeatable_shared_campaign(self):
        occurrence = self._personal_occurrence(expired=True, paid=True)
        receipt = occurrence.reward_receipt.copy()
        response = self._assign()
        self.assertEqual(response.status_code, 400, response.data)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.reward_receipt, receipt)
        self.assertFalse(Quest.objects.exists())

    def test_cooperative_mode_is_a_strict_boolean_in_packs_and_workbench(self):
        for value in ("true", 1, None):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ContentPackError, "is_cooperative"):
                    validate_content({"quests": {"quests": [{
                        "name": "Shared future", "quest_type": "collection", "target_value": 20,
                        "is_cooperative": value,
                    }]}})
                self.parent.is_staff = True
                with self.assertRaisesMessage(ContentPackError, "is_cooperative"):
                    validate_changes(self.parent, [{
                        "section": "quests", "object_id": self.definition.pk, "key": "shared",
                        "values": {"is_cooperative": value},
                    }])

    def test_cooperative_mode_cannot_rewrite_an_active_legacy_promise(self):
        quest = Quest.objects.create(definition=self.definition, end_date=timezone.now() + timedelta(days=7))
        pack = ContentPack.__new__(ContentPack)
        count, changed = pack._active_quest_changes(self.definition, {"is_cooperative": False}, {})
        self.assertEqual((count, changed), (1, ["is_cooperative"]))
        quest.refresh_from_db()
        self.assertEqual((quest.status, quest.current_progress), ("active", 0))
