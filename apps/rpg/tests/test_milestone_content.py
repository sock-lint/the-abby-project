"""Authored milestone identity and native forecasting regression checks."""
from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory, SkillProgress, XP_THRESHOLDS
from apps.quests.models import Quest, QuestDefinition, QuestRewardItem
from apps.rpg.models import ItemDefinition, UserInventory
from apps.rpg.services import ConsumableService
from apps.rpg.acquisition import sources_for_request
from types import SimpleNamespace
from apps.rpg.content.loader import ContentPack, ContentPackError
from apps.rpg.content.workbench import create_draft, save_draft, preview_draft, simulate_draft, publish_draft
from apps.rpg.progression.catalog import CatalogRecord, _freeze, load_catalog
from apps.rpg.progression.engine import Trial
from apps.rpg.tests.test_progression_engine import quiet_config
from config.tests.factories import make_family


class MilestoneContentTests(TestCase):
    def setUp(self):
        self.actor = make_family(parents=[{"username": "designer"}]).parents[0]
        self.actor.is_staff = True
        self.actor.save(update_fields=["is_staff"])
        category = SkillCategory.objects.create(name="Language Arts")
        self.skill = Skill.objects.create(category=category, name="Reading Comprehension")
        self.prior = QuestDefinition.objects.create(name="Companion", description="A starter challenge", is_system=True,
            quest_type="collection", target_value=1,
            trigger_filter={"allowed_triggers": ["reading_logged"]})
        self.target = QuestDefinition.objects.create(name="Voyager", description="A follow-on challenge", is_system=True,
            quest_type="collection", target_value=20, duration_days=56,
            trigger_filter={"allowed_triggers": ["reading_logged"]})

    def test_loader_resolves_forward_challenge_and_qualified_skill_references(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "quests.yaml").write_text("""quests:
- name: Voyager
  quest_type: collection
  target_value: 20
  duration_days: 56
  trigger_filter: {allowed_triggers: [reading_logged]}
  prerequisite_quest: New companion
  required_skill: Language Arts::Reading Comprehension
  required_skill_level: 1
- name: New companion
  quest_type: collection
  target_value: 2
""")
            ContentPack(directory).load()
        self.target.refresh_from_db()
        self.assertEqual(getattr(self.target, "prerequisite_quest_id", None),
                         QuestDefinition.objects.get(name="New companion").pk)
        self.assertEqual(getattr(self.target, "required_skill_id", None), self.skill.pk)

    def test_workbench_previews_exact_gate_ids_without_mutating_catalog(self):
        draft = create_draft(self.actor, "Milestone preview")
        saved = save_draft(self.actor, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": self.target.pk, "key": "voyager",
            "values": {"prerequisite_quest": self.prior.pk,
                       "required_skill": self.skill.pk, "required_skill_level": 1},
        }])
        reviewed = preview_draft(self.actor, saved["id"], saved["revision"])
        self.assertTrue(reviewed["preview"]["changes"])
        self.target.refresh_from_db()
        self.assertIsNone(self.target.prerequisite_quest_id)

    def test_loader_clears_the_skill_and_level_together(self):
        self.target.required_skill = self.skill
        self.target.required_skill_level = 1
        self.target.save()
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "quests.yaml").write_text("""quests:
- name: Voyager
  quest_type: collection
  target_value: 20
  duration_days: 56
  trigger_filter: {allowed_triggers: [reading_logged]}
  required_skill: null
""")
            ContentPack(directory).load()
        self.target.refresh_from_db()
        self.assertEqual((self.target.required_skill_id, self.target.required_skill_level), (None, 0))

    def test_native_trial_waits_for_both_milestones_and_a_matching_fresh_fact(self):
        catalog = load_catalog()
        quests = []
        for row in catalog.quests:
            fields = dict(row.fields)
            if row.pk == self.target.pk:
                fields.update(prerequisite_quest_id=self.prior.pk,
                              required_skill_id=self.skill.pk, required_skill_level=1)
            quests.append(CatalogRecord(_freeze(fields)))
        trial = Trial(quiet_config(reading_minutes=10), replace(catalog, quests=quests), 1)
        trial.day = 1
        trial.advance_challenges("reading_logged", {})
        self.assertNotIn(self.target.pk, trial.quest_windows)
        trial.completed_quests.add(self.prior.pk)
        trial.xp[self.skill.pk] = XP_THRESHOLDS[1]
        trial.unlocked.add(self.skill.pk)
        trial.day = 2
        trial.advance_challenges("habit_log", {})
        self.assertNotIn(self.target.pk, trial.quest_windows)
        trial.advance_challenges("reading_logged", {})
        self.assertEqual(trial.quest_windows[self.target.pk]["start"], 2)
        self.assertEqual(trial.quest_windows[self.target.pk]["progress"], 1)

    def test_combined_draft_cycle_is_rejected_without_changing_either_definition(self):
        draft = create_draft(self.actor, "Cycle")
        with self.assertRaisesMessage(ContentPackError, "cycle"):
            save_draft(self.actor, draft["id"], draft["revision"], [
                {"section": "quests", "object_id": source.pk, "key": source.name.lower(),
                 "values": {"prerequisite_quest": target.pk}}
                for source, target in ((self.target, self.prior), (self.prior, self.target))
            ])
        self.assertFalse(QuestDefinition.objects.filter(prerequisite_quest__isnull=False).exists())

    def test_published_exact_milestones_survive_baseline_yaml_reload(self):
        draft = create_draft(self.actor, "Publish reviewed gates")
        draft = save_draft(self.actor, draft["id"], draft["revision"], [{
            "section": "quests", "object_id": self.target.pk, "key": "voyager", "values": {
                "prerequisite_quest": self.prior.pk, "required_skill": self.skill.pk, "required_skill_level": 1},
        }])
        reviewed = preview_draft(self.actor, draft["id"], draft["revision"])["preview"]
        simulate_draft(self.actor, draft["id"], draft["revision"], reviewed["preview_id"], quiet_config(reading_minutes=10))
        publish_draft(self.actor, draft["id"], draft["revision"], reviewed["preview_id"], reviewed["content_digest"])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "quests.yaml").write_text("quests:\n- name: Voyager\n  quest_type: collection\n  target_value: 20\n  duration_days: 45\n")
            ContentPack(directory).load()
        self.target.refresh_from_db()
        self.assertEqual((self.target.prerequisite_quest_id, self.target.required_skill_id,
                          self.target.required_skill_level, self.target.duration_days),
                         (self.prior.pk, self.skill.pk, 1, 56))

    def test_acquisition_and_reroll_exclude_locked_milestones(self):
        self.target.prerequisite_quest = self.prior
        self.target.required_skill = self.skill
        self.target.required_skill_level = 1
        self.target.save()
        title = ItemDefinition.objects.create(slug="milestone-title", name="Title", item_type="cosmetic_title")
        QuestRewardItem.objects.create(quest_definition=self.target, item=title)
        self.assertNotIn(title.pk, sources_for_request(SimpleNamespace(user=self.actor)))
        reroll = ItemDefinition.objects.create(slug="reroll", name="Reroll", item_type="consumable",
                                               metadata={"effect": "quest_reroll"})
        UserInventory.objects.create(user=self.actor, item=reroll, quantity=1)
        with patch("apps.rpg.services.random.choice", side_effect=lambda choices: choices[0]) as choose:
            ConsumableService.use(self.actor, reroll.pk)
        self.assertEqual([q.pk for q in choose.call_args.args[0]], [self.prior.pk])
        prior = Quest.objects.get(definition=self.prior)
        prior.status = "completed"
        prior.save()
        SkillProgress.objects.create(user=self.actor, skill=self.skill, level=1,
                                     xp_points=XP_THRESHOLDS[1], unlocked=True)
        self.assertEqual(sources_for_request(SimpleNamespace(user=self.actor))[title.pk][0]["name"], self.target.name)
        alternate = QuestDefinition.objects.create(name="Another manual quest", description="Legacy start",
            quest_type="collection", target_value=1, is_system=True)
        UserInventory.objects.update_or_create(user=self.actor, item=reroll, defaults={"quantity": 1})
        with patch("apps.rpg.services.random.choice", side_effect=lambda choices: next(q for q in choices if q.pk == alternate.pk)) as choose:
            ConsumableService.use(self.actor, reroll.pk)
        self.assertNotIn(self.target.pk, [q.pk for q in choose.call_args.args[0]])
