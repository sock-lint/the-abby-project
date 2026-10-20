"""Reviewed pack edits clear explicit relationships and reject unusable content."""
from copy import deepcopy
from pathlib import Path
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
import yaml

from apps.achievements.models import Badge, SkillPrerequisite
from apps.mcp_server.content_pack_schemas import PreviewContentPackIn, PublishContentPackIn
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPValidationError
from apps.mcp_server.schemas import DraftPackEntriesIn, UpdateBadgeIn, WritePackFileIn
from apps.mcp_server.tools import achievements
from apps.mcp_server.tools import content_packs as tools
from apps.quests.models import Quest, QuestDefinition
from apps.rpg.models import ItemDefinition
from config.tests.factories import make_family


class PackManagementTests(TestCase):
    def setUp(self):
        family = make_family("Pack management", parents=[{"username": "pack-parent", "is_staff": True}])
        self.parent = family.parents[0]
        folder = tempfile.TemporaryDirectory(prefix="abby-pack-management-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = override_settings(BASE_DIR=self.root)
        settings.enable()
        self.addCleanup(settings.disable)
        identity = override_user(self.parent)
        identity.__enter__()
        self.addCleanup(identity.__exit__, None, None, None)

    def write(self, filename, value):
        tools.write_pack_file(WritePackFileIn(pack="managed", filename=filename, yaml_content=yaml.safe_dump(value)))

    def preview(self):
        return tools.preview_content_pack(PreviewContentPackIn(pack="managed"))

    def publish(self, plan=None):
        plan = plan or self.preview()
        return tools.publish_content_pack(PublishContentPackIn(
            pack="managed", preview_id=plan["preview_id"], content_digest=plan["content_digest"],
        ))

    def skill_tree(self):
        return {
            "categories": [{"name": "Managed category"}],
            "skills": [
                {"name": "First", "category": "Managed category", "levels": {1: "Beginner"}},
                {"name": "Next", "category": "Managed category", "levels": {1: "Beginner"}, "prereqs": ["First"]},
            ],
        }

    def test_explicit_empty_prerequisites_remove_only_the_owned_skill_edges(self):
        data = self.skill_tree()
        self.write("skill_tree.yaml", data)
        self.publish()
        self.assertEqual(SkillPrerequisite.objects.count(), 1)
        data["skills"][1]["prereqs"] = []
        self.write("skill_tree.yaml", data)
        plan = self.preview()
        self.assertTrue(any(change["action"] == "remove" and "skillprerequisite" in change["object"] for change in plan["changes"]))
        self.assertEqual(SkillPrerequisite.objects.count(), 1, "Preview must roll back relationship edits")
        self.publish(plan)
        self.assertFalse(SkillPrerequisite.objects.exists())

    def test_omitted_prerequisites_retain_existing_edges(self):
        data = self.skill_tree()
        self.write("skill_tree.yaml", data)
        self.publish()
        del data["skills"][1]["prereqs"]
        self.write("skill_tree.yaml", data)
        self.publish()
        self.assertEqual(SkillPrerequisite.objects.count(), 1)

    def gated_quest(self):
        badge = Badge.objects.create(
            name="Managed gate", description="Synthetic", criteria_type="projects_completed", criteria_value={"count": 1},
        )
        row = {"id": "gated", "name": "Managed quest", "description": "Synthetic", "quest_type": "collection",
               "target_value": 1, "required_badge": badge.name}
        self.write("quests.yaml", {"quests": [row]})
        self.publish()
        return row, QuestDefinition.objects.get(name=row["name"])

    def test_explicit_null_required_badge_clears_the_gate(self):
        row, quest = self.gated_quest()
        row["required_badge"] = None
        self.write("quests.yaml", {"quests": [row]})
        plan = self.preview()
        self.assertTrue(any(change["action"] == "update" and change["after"].get("required_badge", "missing") is None for change in plan["changes"]))
        self.publish(plan)
        quest.refresh_from_db()
        self.assertIsNone(quest.required_badge_id)

    def test_omitted_badge_preserves_it_and_active_legacy_gate_cannot_be_cleared(self):
        row, quest = self.gated_quest()
        omitted = deepcopy(row)
        omitted.pop("required_badge")
        self.write("quests.yaml", {"quests": [omitted]})
        self.publish()
        quest.refresh_from_db()
        self.assertIsNotNone(quest.required_badge_id)
        Quest.objects.create(definition=quest, end_date=timezone.now() + timedelta(days=7))
        row["required_badge"] = None
        self.write("quests.yaml", {"quests": [row]})
        with self.assertRaisesRegex(MCPValidationError, "active legacy"):
            self.preview()

    def test_stable_id_rename_replaces_one_draft_row_and_retains_runtime_identity(self):
        row = {"id": "stable", "name": "Old name", "description": "Synthetic", "quest_type": "collection", "target_value": 1}
        tools.draft_pack_entries(DraftPackEntriesIn(pack="managed", filename="quests.yaml", entries=[row]))
        self.publish()
        original = QuestDefinition.objects.get(name="Old name")
        row["name"] = "New name"
        result = tools.draft_pack_entries(DraftPackEntriesIn(pack="managed", filename="quests.yaml", entries=[row]))
        self.assertEqual(result["entry_count"], 1)
        self.publish()
        self.assertEqual(QuestDefinition.objects.get(name="New name").pk, original.pk)

    def test_competing_stable_ids_for_same_name_reject_before_file_write(self):
        row = {"id": "first", "name": "Same name", "quest_type": "collection", "target_value": 1}
        tools.draft_pack_entries(DraftPackEntriesIn(pack="managed", filename="quests.yaml", entries=[row]))
        path = self.root / "content/rpg/packs/managed/quests.yaml"
        original = path.read_bytes()
        with self.assertRaises(MCPValidationError):
            tools.draft_pack_entries(DraftPackEntriesIn(pack="managed", filename="quests.yaml", entries=[{**row, "id": "other"}]))
        self.assertEqual(path.read_bytes(), original)

    def test_bad_runtime_item_metadata_rejects_before_preview_or_publication(self):
        for metadata in ({"effect": "not-a-runtime-effect"}, {"effect": "xp_boost", "duration_hours": -1}):
            with self.subTest(metadata=metadata):
                self.write("items.yaml", {"items": [{"slug": "bad", "name": "Bad tonic", "item_type": "consumable", "metadata": metadata}]})
                with self.assertRaises(MCPValidationError):
                    self.preview()
                self.assertFalse(ItemDefinition.objects.filter(slug="managed-bad").exists())

    def test_owned_badge_rename_cannot_reuse_another_direct_authored_source_name(self):
        original = Badge.objects.create(name="Bundled source badge", description="Synthetic",
            criteria_type="projects_completed", criteria_value={"count": 1})
        achievements.update_badge(UpdateBadgeIn(badge_id=original.pk, name="Authored source badge"))
        row = {"id": "other-badge", "name": "Pack badge", "description": "Synthetic",
               "criteria_type": "projects_completed", "criteria_value": {"count": 2}}
        self.write("badges.yaml", {"badges": [row]})
        self.publish()
        owned = Badge.objects.get(name="Pack badge")
        row["name"] = "Bundled source badge"
        self.write("badges.yaml", {"badges": [row]})
        with self.assertRaises(MCPValidationError):
            self.preview()
        self.assertEqual(Badge.objects.get(pk=owned.pk).name, "Pack badge")
        self.assertEqual(Badge.objects.get(pk=original.pk).name, "Authored source badge")
