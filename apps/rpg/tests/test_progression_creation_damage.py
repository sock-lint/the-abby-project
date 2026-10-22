"""Supporting coverage for the already-correct automatic creation boundary."""

from django.test import TestCase

from apps.achievements.models import Skill, SkillCategory
from apps.quests.models import QuestDefinition
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial
from apps.rpg.tests.test_progression_economy import quiet_config


class ProgressionCreationDamageTests(TestCase):
    def test_creations_advance_collections_without_boss_progress_or_rewards(self):
        category = SkillCategory.objects.create(name="Art & Crafts")
        Skill.objects.create(category=category, name="Drawing")
        boss = QuestDefinition.objects.create(
            name="Creation cannot damage this boss", quest_type="boss", target_value=1,
            duration_days=7, is_system=True, coin_reward=999, xp_reward=999,
            trigger_filter={"allowed_triggers": ["creation_logged"]},
        )
        collection = QuestDefinition.objects.create(
            name="Three eligible creations", quest_type="collection", target_value=3,
            duration_days=7, is_system=True, coin_reward=7,
            trigger_filter={"allowed_triggers": ["creation_logged"]},
        )
        trial = Trial(quiet_config(creations_per_day=3), load_catalog(), 42)

        with self.assertNumQueries(0):
            self.assertNotIn(f"quest:{boss.pk}", trial.finite_keys)
            trial.daily(1)
            self.assertEqual(trial.quest_windows[collection.pk]["progress"], 2)
            self.assertNotIn(boss.pk, trial.quest_windows)
            self.assertFalse(trial.completed_quests)
            self.assertEqual(trial.source_totals["challenges"]["coins"], 0)

            trial.daily(2)
            self.assertEqual(trial.completed_quests, {collection.pk})
            self.assertNotIn(boss.pk, trial.quest_windows)
            self.assertEqual(trial.counters["creations"], 6)
            self.assertEqual(trial.source_totals["creations"]["xp"], 40)
            self.assertEqual(trial.source_totals["challenges"]["coins"], 7)
            self.assertEqual(trial.source_totals["challenges"]["xp"], 0)
            self.assertEqual(trial.counters["drop_opportunities:creation_logged"], 4)
            self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 1)
