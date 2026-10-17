"""Accepted item promises survive catalog retirement without opening new offers."""
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.pets.models import PetSpecies
from apps.achievements.models import SkillProgress, UserBadge
from apps.activity.models import ActivityEvent
from apps.quests.goals import _occurrence, ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, Quest, QuestDefinition, QuestParticipant, QuestRewardItem
from apps.quests.serializers import QuestSerializer
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.companion_catalog import reconcile_companion_offers
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import ItemDefinition, UserInventory
from config.tests.factories import make_family


PRIOR_POLICY = {
    "schema_version": 1,
    "pets": [
        {"species_slug": "wolf", "sprite_key": "wolf", "potion_slugs": ["base"]},
        {"species_slug": "chick", "sprite_key": "cute-chick", "potion_slugs": ["base"]},
    ],
    "potion_slugs": ["base"],
    "disabled_item_types": ["cosmetic_pet_accessory"],
}


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class RetiredRewardPromiseTests(TestCase):
    def setUp(self):
        household = make_family("Reward preservation", children=[
            {"username": "promise-first"}, {"username": "promise-second"},
        ])
        self.first, self.second = household.children
        wolf = PetSpecies.objects.create(slug="wolf", name="Wolf", sprite_key="wolf")
        chick = PetSpecies.objects.create(slug="chick", name="Chick", sprite_key="cute-chick")
        self.eggs = [
            ItemDefinition.objects.create(
                slug="wolf-egg", name="Wolf Egg", item_type="egg", pet_species=wolf,
                metadata={"species": "wolf"},
            ),
            ItemDefinition.objects.create(
                slug="accepted-chick-alias", name="Earlier Chick Egg", item_type="egg",
                pet_species=chick, metadata={"species": "Chick"},
            ),
        ]
        self.definition = QuestDefinition.objects.create(
            name="Accepted egg challenge", quest_type="collection", target_value=1,
        )
        for egg in self.eggs:
            QuestRewardItem.objects.create(quest_definition=self.definition, item=egg, quantity=2)

    def automatic_goal(self, *, name="Accepted automatic challenge"):
        now = timezone.now()
        goal = ChallengeGoal.objects.create(
            user=self.first, family=self.first.family, name=name,
            metric="count", target=1, timezone_name="America/Phoenix",
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=1),
            trigger_filter={"allowed_triggers": ["chore_complete"]},
            reward_items=[{"item_id": egg.pk, "quantity": 2} for egg in self.eggs],
        )
        return _occurrence(goal, now)

    def assert_original_items(self, user):
        self.assertEqual(
            dict(UserInventory.objects.filter(user=user).values_list("item_id", "quantity")),
            {egg.pk: 2 for egg in self.eggs},
        )

    def test_frozen_automatic_promise_stays_visible_and_pays_original_items_once(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=PRIOR_POLICY):
            occurrence = self.automatic_goal()
        snapshot = occurrence.snapshot
        reconcile_companion_offers()
        row = next(row for row in list_goals(self.first)["results"] if row["id"] == f"goal:{occurrence.pk}")
        self.assertEqual([item["item_id"] for item in row["rewards"]["items"]], [egg.pk for egg in self.eggs])
        for source in ("first-chore", "first-chore", "second-chore"):
            ingest_activity(self.first, "chore", source, "chore_complete")
        self.assert_original_items(self.first)
        occurrence.refresh_from_db()
        self.assertEqual(occurrence.snapshot, snapshot)
        self.assertEqual([row["quantity"] for row in occurrence.reward_receipt["items"]], [2, 2])

    def test_new_automatic_snapshot_excludes_retired_items(self):
        occurrence = self.automatic_goal(name="New automatic challenge")
        self.assertEqual(occurrence.snapshot["items"], [])
        ingest_activity(self.first, "chore", "new-chore", "chore_complete")
        self.assertFalse(UserInventory.objects.filter(user=self.first).exists())

    def test_frozen_automatic_payout_does_not_recheck_retired_catalog(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=PRIOR_POLICY):
            self.automatic_goal()
        reconcile_companion_offers()
        ingest_activity(self.first, "chore", "pay-accepted-chore", "chore_complete")
        self.assert_original_items(self.first)

    def test_accepted_legacy_coop_promise_ignores_later_policy_and_definition_edits(self):
        with override_settings(RPG_ASSET_SUPPORT_POLICY=PRIOR_POLICY):
            quest = QuestService.start_co_op_quest(self.definition.pk, [self.first, self.second])
        self.assertEqual({row["item_id"]: row["quantity"] for row in quest.reward_items_snapshot},
                         {egg.pk: 2 for egg in self.eggs})
        reconcile_companion_offers()
        QuestRewardItem.objects.filter(quest_definition=self.definition).update(quantity=9)
        preview = QuestSerializer(quest).data["definition"]["reward_items"]
        self.assertEqual({row["item"]: row["quantity"] for row in preview}, {egg.pk: 2 for egg in self.eggs})
        QuestService.record_progress(self.first, "chore_complete")
        QuestService._complete_quest(quest, self.second)
        for child in (self.first, self.second):
            self.assert_original_items(child)

    def old_accepted_quest(self):
        quest = Quest.objects.create(
            definition=self.definition, end_date=timezone.now() + timedelta(days=1),
        )
        QuestParticipant.objects.create(quest=quest, user=self.first)
        return quest

    def test_reconcile_freezes_existing_legacy_links_once_and_dry_run_writes_nothing(self):
        quest = self.old_accepted_quest()
        before = list(Quest.objects.values())
        awards_before = {
            model: list(model.objects.order_by("pk").values())
            for model in (UserInventory, CoinLedger, SkillProgress, UserBadge, ActivityEvent)
        }
        report = reconcile_companion_offers(dry_run=True)
        self.assertEqual(report["quests_snapshotted"], 1)
        self.assertEqual(report["quest_ids"], [quest.pk])
        self.assertEqual(list(Quest.objects.values()), before)
        self.assertEqual(reconcile_companion_offers(dry_run=True), report)
        reconcile_companion_offers()
        quest.refresh_from_db()
        snapshot = quest.reward_items_snapshot
        self.assertEqual({row["item_id"]: row["quantity"] for row in snapshot}, {egg.pk: 2 for egg in self.eggs})
        self.assertEqual(
            [{key: value for key, value in row.items() if key != "reward_items_snapshot"}
             for row in Quest.objects.values()],
            [{key: value for key, value in row.items() if key != "reward_items_snapshot"} for row in before],
        )
        self.assertEqual({model: list(model.objects.order_by("pk").values()) for model in awards_before}, awards_before)
        self.assertEqual(reconcile_companion_offers()["quests_snapshotted"], 0)
        self.assertEqual(reconcile_companion_offers(dry_run=True)["quests_snapshotted"], 0)
        QuestRewardItem.objects.filter(quest_definition=self.definition).delete()
        self.assertEqual(reconcile_companion_offers()["quests_snapshotted"], 0)
        quest.refresh_from_db()
        self.assertEqual(quest.reward_items_snapshot, snapshot)
        QuestService.record_progress(self.first, "chore_complete")
        QuestService._complete_quest(quest, self.first)
        self.assert_original_items(self.first)
    def test_existing_null_legacy_promise_pays_without_operator_reconciliation(self):
        quest = self.old_accepted_quest()
        self.assertEqual(len(QuestSerializer(quest).data["definition"]["reward_items"]), 2)
        QuestService.record_progress(self.first, "chore_complete")
        QuestService._complete_quest(quest, self.first)
        self.assert_original_items(self.first)
        quest.refresh_from_db()
        self.assertIsNotNone(quest.reward_items_snapshot)
        QuestRewardItem.objects.filter(quest_definition=self.definition).delete()
        self.assertEqual(len(QuestSerializer(quest).data["definition"]["reward_items"]), 2)

    def test_content_reload_freezes_old_promise_before_updating_definition_links(self):
        quest = self.old_accepted_quest()
        data = {"quests": [{
            "name": self.definition.name, "quest_type": "collection", "target_value": 1,
            "reward_items": [{"slug": egg.slug, "quantity": 9} for egg in self.eggs],
        }]}
        with TemporaryDirectory() as path:
            Path(path, "quests.yaml").write_text(json.dumps(data))
            ContentPack(path).load(dry_run=True)
            quest.refresh_from_db()
            self.assertIsNone(quest.reward_items_snapshot)
            ContentPack(path).load()
        quest.refresh_from_db()
        self.assertEqual({row["item_id"]: row["quantity"] for row in quest.reward_items_snapshot},
                         {egg.pk: 2 for egg in self.eggs})
        QuestService.record_progress(self.first, "chore_complete")
        self.assert_original_items(self.first)

    def test_new_legacy_quest_freezes_empty_eligible_offer_and_cannot_acquire_later_items(self):
        quest = QuestService.start_quest(self.first, self.definition.pk)
        self.assertEqual(quest.reward_items_snapshot, [])
        new_food = ItemDefinition.objects.create(slug="later-food", name="Later food", item_type="food")
        QuestRewardItem.objects.create(quest_definition=self.definition, item=new_food)
        self.assertEqual(QuestSerializer(quest).data["definition"]["reward_items"], [])
        QuestService.record_progress(self.first, "chore_complete")
        self.assertFalse(UserInventory.objects.filter(user=self.first).exists())
