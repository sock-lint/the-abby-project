"""Untimed onboarding content keeps a real null deadline across authoring paths."""
from pathlib import Path
import tempfile
from django.test import TestCase
from apps.quests.models import QuestDefinition
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.validation import validate_content
from apps.rpg.content.workbench import create_draft, save_draft, preview_draft, simulate_draft, publish_draft
from config.tests.factories import make_family


class UntimedContentTests(TestCase):
    def setUp(self):
        self.actor = make_family("Untimed designers", parents=[{"username": "untimed-designer", "is_staff": True}]).parents[0]
        self.quest = QuestDefinition.objects.create(name="Untimed Reading", description="Read when ready", is_system=True,
            quest_type="collection", target_value=3, duration_days=14,
            trigger_filter={"allowed_triggers": ["reading_logged"]})

    def test_private_preview_carries_null_without_changing_live_definition(self):
        draft = create_draft(self.actor, "Untimed onboarding")
        draft = save_draft(self.actor, draft["id"], draft["revision"], [{"section": "quests", "object_id": self.quest.pk,
            "key": "untimed-reading", "values": {"duration_days": None}}])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])
        self.assertIsNone(reviewed["changes"][0]["values"]["duration_days"])
        self.assertIsNone(reviewed["published_at"])
        self.quest.refresh_from_db()
        self.assertEqual(self.quest.duration_days, 14)

    def test_yaml_loads_real_untimed_reading_and_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/"quests.yaml").write_text("quests:\n- name: Untimed Reading\n  quest_type: collection\n  target_value: 3\n  duration_days: null\n  trigger_filter: {allowed_triggers: [reading_logged]}\n")
            ContentPack(path).load()
            ContentPack(path).load()
        self.quest.refresh_from_db()
        self.assertIsNone(self.quest.duration_days)
        self.assertEqual(QuestDefinition.objects.filter(name="Untimed Reading").count(), 1)

    def test_reviewed_null_override_survives_a_timed_yaml_reload(self):
        draft = create_draft(self.actor, "Untimed onboarding")
        draft = save_draft(self.actor, draft["id"], draft["revision"], [{"section": "quests", "object_id": self.quest.pk,
            "key": "untimed-reading", "values": {"duration_days": None}}])
        plan = preview_draft(self.actor, draft["id"], draft["revision"])["preview"]
        simulate_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"],
            {"horizon_days": 30, "trials": 1, "reading_minutes": 10})
        publish_draft(self.actor, draft["id"], draft["revision"], plan["preview_id"], plan["content_digest"])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/"quests.yaml").write_text("quests:\n- name: Untimed Reading\n  quest_type: collection\n  target_value: 3\n  duration_days: 14\n  trigger_filter: {allowed_triggers: [reading_logged]}\n")
            ContentPack(path).load()
        self.quest.refresh_from_db()
        self.assertIsNone(self.quest.duration_days)

    def test_reroll_chooses_only_manual_timed_challenges(self):
        from unittest.mock import patch
        from apps.rpg.models import ItemDefinition, UserInventory
        from apps.rpg.services import ConsumableService
        QuestDefinition.objects.filter(pk=self.quest.pk).update(duration_days=None)
        manual = QuestDefinition.objects.create(name="Manual challenge", description="Timed", is_system=True,
            quest_type="collection", target_value=2, duration_days=7)
        reroll = ItemDefinition.objects.create(name="Reroll", slug="untimed-reroll", item_type="consumable",
            metadata={"effect": "quest_reroll"})
        UserInventory.objects.create(user=self.actor, item=reroll, quantity=1)
        with patch("apps.rpg.services.random.choice", side_effect=lambda rows: rows[0]) as choose:
            ConsumableService.use(self.actor, reroll.pk)
        self.assertEqual([row.pk for row in choose.call_args.args[0]], [manual.pk])

    def test_content_rejects_null_repeatable_boss_or_nonreading_rules(self):
        base={"name": "Invalid", "quest_type": "collection", "target_value": 3, "duration_days": None,
              "trigger_filter": {"allowed_triggers": ["reading_logged"]}}
        for edit in ({"is_repeatable": True}, {"quest_type": "boss"}, {"trigger_filter": {"allowed_triggers": ["habit_log"]}}):
            with self.subTest(edit=edit), self.assertRaises(ContentPackError):
                validate_content({"quests": {"quests": [{**base, **edit}]}})
