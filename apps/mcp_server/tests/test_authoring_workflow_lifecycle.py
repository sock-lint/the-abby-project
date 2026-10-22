"""Exercise reviewed MCP authoring across reloads and reversible retirement."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from asgiref.sync import async_to_sync, sync_to_async
from django.core.cache import cache
from django.db import connections
from django.test import TransactionTestCase, override_settings
from mcp.server.fastmcp.exceptions import ToolError

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition, QuestRewardItem, QuestSkillTag
from apps.rewards.models import CoinLedger
from apps.rpg.content.loader import ContentPack
from apps.rpg.content.workbench import describe_workbench
from apps.rpg.models import ItemDefinition, RPGContentOverride, UserInventory
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthoringWorkflowLifecycleTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Workflow designers", parents=[{"username": "workflow-author", "is_staff": True}],
            children=[{"username": "workflow-accepted"}, {"username": "workflow-next"}, {"username": "workflow-waiting"}])
        self.actor = family.parents[0]
        self.accepted, self.next_child, self.waiting = family.children
        self.category = SkillCategory.objects.create(name="Workflow category")
        self.skill = Skill.objects.create(name="Workflow practice", category=self.category)
        self.item = ItemDefinition.objects.create(slug="workflow-food", name="Original snack", item_type="food")
        self.quest = QuestDefinition.objects.create(name="Original practice", description="Synthetic practice",
            is_system=True, quest_type="collection", target_value=2, coin_reward=17, xp_reward=11,
            trigger_filter={"allowed_triggers": ["chore_complete"]})
        QuestRewardItem.objects.create(quest_definition=self.quest, item=self.item, quantity=2)
        QuestSkillTag.objects.create(quest_definition=self.quest, skill=self.skill)

    def invoke(self, name, params, *, scope="mcp:author", **arguments):
        entry = mcp._tool_manager.get_tool(name)
        self.assertIsNotNone(entry)

        async def run():
            with override_user(self.actor, scopes=frozenset({scope})):
                try:
                    result = await entry.run({"params": params, **arguments}, convert_result=True)
                    return result[1] if isinstance(result, tuple) else result
                finally:
                    await sync_to_async(connections.close_all, thread_sensitive=True)()
        return async_to_sync(run)()

    def reviewed_draft(self):
        draft = self.invoke("create_content_draft", {"name": "Workflow review"})
        draft = self.invoke("save_content_draft", {"draft_id": draft["id"], "revision": draft["revision"], "changes": [
            {"section": "items", "object_id": self.item.pk, "key": "snack", "values": {"name": "Published snack"}},
            {"section": "quests", "object_id": self.quest.pk, "key": "practice", "values": {
                "name": "Published practice", "coin_reward": 29, "xp_reward": 23,
                "reward_items": [{"item_id": self.item.pk, "quantity": 3}],
                "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
            }},
        ]}, confirmation=True)
        reviewed = self.invoke("preview_content_draft", {"draft_id": draft["id"], "revision": draft["revision"]})
        identity = {"draft_id": draft["id"], "revision": draft["revision"], "preview_id": reviewed["preview"]["preview_id"]}
        return reviewed, identity

    def rewards_state(self):
        return {model.__name__: list(model.objects.order_by("pk").values())
                for model in (ChallengeGoal, ChallengeOccurrence, CoinLedger, SkillProgress, UserInventory)}

    def reload_baseline(self):
        with TemporaryDirectory() as folder:
            source = {
                "items.yaml": {"items": [{"slug": self.item.slug, "name": "Original snack", "item_type": "food"}]},
                "quests.yaml": {"quests": [{"name": "Original practice", "description": "Synthetic practice",
                    "quest_type": "collection", "target_value": 2, "coin_reward": 17, "xp_reward": 11,
                    "trigger_filter": {"allowed_triggers": ["chore_complete"]},
                    "reward_items": [{"slug": self.item.slug, "quantity": 2}]}]},
                "skill_tree.yaml": {"categories": [{"name": self.category.name}],
                    "skills": [{"name": self.skill.name, "category": self.category.name}]},
            }
            for filename, body in source.items():
                Path(folder, filename).write_text(json.dumps(body))
            ContentPack(folder).load()

    def test_publish_reload_retire_restore_keeps_accepted_promises_and_future_choices(self):
        list_goals(self.accepted)
        accepted = ChallengeOccurrence.objects.get(goal__user=self.accepted, goal__catalog_definition=self.quest)
        original = deepcopy(accepted.snapshot)
        before_review = self.rewards_state()
        reviewed, identity = self.reviewed_draft()
        self.invoke("simulate_content_draft", {**identity, "config": {"horizon_days": 30, "trials": 1}})
        self.assertEqual(self.rewards_state(), before_review, "Preview and simulation must not change household state")
        publish = {**identity, "content_digest": reviewed["preview"]["content_digest"]}
        first = self.invoke("publish_content_draft", publish, scope="mcp:publish", confirmation=True)
        self.assertEqual(self.invoke("publish_content_draft", publish, scope="mcp:publish", confirmation=True), first)
        self.reload_baseline()
        self.quest.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual((self.quest.name, self.quest.coin_reward, self.item.name), ("Published practice", 29, "Published snack"))
        self.assertEqual(QuestDefinition.objects.count(), 1)
        self.assertEqual(ItemDefinition.objects.count(), 1)
        self.assertEqual(RPGContentOverride.objects.filter(model_label="quests.questdefinition", object_id=self.quest.pk).count(), 1)
        list_goals(self.next_child)
        next_attempt = ChallengeOccurrence.objects.get(goal__user=self.next_child, goal__catalog_definition=self.quest)
        self.assertEqual((next_attempt.snapshot["coins"], next_attempt.snapshot["xp"], next_attempt.snapshot["items"][0]["quantity"]), (29, 23, 3))

        before_retirement = self.rewards_state()
        retired = self.invoke("update_category", {"category_id": self.category.pk, "is_retired": True}, scope="mcp:publish", confirmation=True)
        self.assertFalse(retired["available_for_new_choices"])
        self.assertEqual(self.invoke("list_skills", {"category_id": self.category.pk}, scope="mcp:catalog")["skills"], [])
        retained = self.invoke("list_skills", {"category_id": self.category.pk, "include_retired": True}, scope="mcp:catalog")["skills"]
        self.assertEqual([row["id"] for row in retained], [self.skill.pk])
        self.assertFalse(retained[0]["available_for_new_choices"])
        self.reload_baseline()
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_retired, "An omitted YAML flag must preserve saved retirement")
        rows = self.invoke("get_content_workbench", {"section": "quests"}, scope="mcp:catalog")["results"]
        self.assertFalse(rows[0]["available_for_new_user"])
        self.assertEqual(self.rewards_state(), before_retirement)
        list_goals(self.waiting)
        self.assertFalse(ChallengeGoal.objects.filter(user=self.waiting, catalog_definition=self.quest).exists())

        for source in ("first", "second", "second"):
            ingest_activity(self.accepted, "chore", source, "chore_complete")
        accepted.refresh_from_db()
        self.assertEqual(accepted.snapshot, original)
        self.assertEqual(accepted.reward_receipt["coins"], 17)
        self.assertEqual(accepted.reward_receipt["xp"], 11)
        self.assertEqual(list(CoinLedger.objects.filter(user=self.accepted).values_list("amount", flat=True)), [17])
        self.assertEqual(UserInventory.objects.get(user=self.accepted, item=self.item).quantity, 2)
        self.assertEqual(SkillProgress.objects.get(user=self.accepted, skill=self.skill).xp_points, 11)
        before_restore = self.rewards_state()
        self.invoke("update_category", {"category_id": self.category.pk, "is_retired": False}, scope="mcp:publish", confirmation=True)
        self.assertEqual(self.rewards_state(), before_restore)
        list_goals(self.waiting)
        restored_attempt = ChallengeOccurrence.objects.get(goal__user=self.waiting, goal__catalog_definition=self.quest)
        self.assertEqual((restored_attempt.snapshot["coins"], restored_attempt.snapshot["items"][0]["quantity"]), (29, 3))
        self.assertEqual(restored_attempt.snapshot["skill_tags"], original["skill_tags"])

    def test_retirement_after_simulation_requires_a_new_review_before_publication(self):
        reviewed, identity = self.reviewed_draft()
        self.invoke("simulate_content_draft", {**identity, "config": {"horizon_days": 30, "trials": 1}})
        self.invoke("update_category", {"category_id": self.category.pk, "is_retired": True}, scope="mcp:publish", confirmation=True)
        with self.assertRaisesRegex(ToolError, "Catalog state changed"):
            self.invoke("publish_content_draft", {**identity, "content_digest": reviewed["preview"]["content_digest"]}, scope="mcp:publish", confirmation=True)
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.name, "Original practice")
        self.assertFalse(RPGContentOverride.objects.filter(model_label="quests.questdefinition").exists())

    def test_mcp_catalog_explains_untrackable_retained_challenges_like_native_workbench(self):
        for quest_type, triggers in (("collection", ["perfect_day"]), ("boss", ["creation_logged"])):
            with self.subTest(quest_type=quest_type, triggers=triggers):
                QuestDefinition.objects.filter(pk=self.quest.pk).update(quest_type=quest_type,
                    trigger_filter={"allowed_triggers": triggers})
                native = describe_workbench(self.actor)["catalog"]["quests"][0]
                self.assertFalse(native["available_for_new_user"])
                for tool in ("get_content_workbench", "read_rpg_catalog"):
                    projected = self.invoke(tool, {"section": "quests"}, scope="mcp:catalog")["results"][0]
                    self.assertEqual(projected["available_for_new_user"], native["available_for_new_user"], tool)
                    self.assertEqual(projected["automatic_tracking_available"], native["automatic_tracking_available"])
                    self.assertEqual(projected["unsupported_triggers"], triggers)
        QuestDefinition.objects.filter(pk=self.quest.pk).update(quest_type="collection",
            trigger_filter={"allowed_triggers": ["chore_complete"]})
        row = self.invoke("get_content_workbench", {"section": "quests"}, scope="mcp:catalog")["results"][0]
        self.assertTrue(row["available_for_new_user"])
        self.assertTrue(row["automatic_tracking_available"])
        self.assertEqual(row["unsupported_triggers"], [])
