"""An untimed onboarding milestone must remain usable after long reading gaps."""

from dataclasses import replace
from io import StringIO

from django.test import TestCase, override_settings

from apps.achievements.models import Skill
from apps.quests.models import QuestDefinition, QuestSkillTag
from apps.rpg.content.loader import ContentPack
from apps.rpg.models import DropTable, ItemDefinition
from apps.rpg.progression.catalog import FrozenRows, _freeze, load_catalog
from apps.rpg.progression.engine import Trial, normalize_config
from apps.rpg.tests.test_progression_engine import quiet_config


@override_settings(RPG_ASSET_SUPPORT_POLICY=None)
class UntimedReadingForecastTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ContentPack("content/rpg/initial").load(stdout=StringIO())
        cls.companion = QuestDefinition.objects.create(
            name="Untimed forecast onboarding", quest_type="collection", target_value=3,
            duration_days=14, trigger_filter={"allowed_triggers": ["reading_logged"]},
            is_system=True, coin_reward=0, xp_reward=10,
        )
        QuestSkillTag.objects.create(
            quest_definition=cls.companion,
            skill=Skill.objects.get(name="Reading Comprehension", category__name="Language Arts"),
            xp_weight=1,
        )
        cls.voyager = QuestDefinition.objects.create(
            name="Forecast next chapter", quest_type="collection", target_value=2,
            duration_days=56, trigger_filter={"allowed_triggers": ["reading_logged"]},
            is_system=True, prerequisite_quest=cls.companion, coin_reward=0, xp_reward=0,
        )

    def catalog(self, *, untimed=True, **overrides):
        catalog = load_catalog()
        quests = []
        for quest in catalog.quests:
            if quest.pk not in {self.companion.pk, self.voyager.pk}:
                continue
            if quest.pk == self.companion.pk:
                quest = replace(quest, fields=_freeze({
                    **quest.fields, "duration_days": None if untimed else 14, **overrides,
                }))
            quests.append(quest)
        return replace(catalog, quests=FrozenRows(quests), badges=[])

    def trial(self, *, untimed=True, **overrides):
        return Trial(normalize_config(quiet_config(
            horizon_days=90, reading_minutes=10, habits_per_day=1,
        )), self.catalog(untimed=untimed, **overrides), 71)

    def test_late_first_reading_and_interrupted_first_three_keep_onboarding_available(self):
        trial = self.trial()
        reading_days = {22, 36, 57, 58, 59}
        for day in range(1, 91):
            trial.config["reading_minutes"] = 10 if day in reading_days else 0
            trial.daily(day)
            if day == 56:
                report = trial.challenge_gates.report(trial)
                rows = {row["quest_id"]: row for row in report["targets"]}
                self.assertFalse(rows[self.companion.pk]["expired"])
                self.assertFalse(rows[self.voyager.pk]["blocked"])
                self.assertEqual(trial.quest_windows[self.companion.pk]["progress"], 2)
                self.assertEqual(trial.trace[-1]["expired_oneoff_challenges"], 0)
        self.assertEqual(trial.challenge_gates.completion_days[self.companion.pk], 57)
        self.assertEqual(trial.quest_windows[self.voyager.pk]["start"], 58)
        self.assertEqual(trial.challenge_gates.completion_days[self.voyager.pk], 59)
        self.assertEqual(trial.source_totals["challenges"]["xp"], 10)
        self.assertEqual(trial.trace[-1]["expired_oneoff_challenges"], 0)

    def test_timed_control_still_expires_and_blocks_next_chapter(self):
        trial = self.trial(untimed=False)
        for day in range(1, 91):
            trial.config["reading_minutes"] = 10 if day >= 22 else 0
            trial.daily(day)
        rows = {row["quest_id"]: row for row in trial.challenge_gates.report(trial)["targets"]}
        self.assertTrue(rows[self.companion.pk]["expired"])
        self.assertTrue(rows[self.voyager.pk]["blocked"])
        self.assertFalse(trial.completed_quests)

    def test_null_does_not_admit_repeatable_or_nonreading_challenges(self):
        for overrides in (
            {"is_repeatable": True}, {"quest_type": "boss"},
            {"trigger_filter": {"allowed_triggers": ["habit_log"]}},
            {"trigger_filter": {"allowed_triggers": ["reading_logged"], "on_time": True}},
        ):
            with self.subTest(overrides=overrides):
                trial = self.trial(**overrides)
                self.assertNotIn(self.companion.pk, {q.pk for q in trial.quests})

    def test_84_day_twice_weekly_forecast_matches_native_reading_completion_and_absence_margin(self):
        skill = Skill.objects.get(name="Reading Comprehension", category__name="Language Arts")
        catalog = self.catalog()
        quests = FrozenRows(replace(quest, fields=_freeze({
            **quest.fields,
            **({"xp_reward": 20} if quest.pk == self.companion.pk else {
                "duration_days": 84, "target_value": 20, "required_skill_id": skill.pk, "required_skill_level": 1,
            }),
        })) for quest in catalog.quests)
        # No random reward or badge path is needed for this direct reading path.
        catalog = replace(catalog, quests=quests, pools={}, badges=[])
        for missed_days, completion in ((set(), 85), ({29, 30, 57, 58}, 99)):
            with self.subTest(missed_days=missed_days):
                trial = Trial(normalize_config(quiet_config(
                    horizon_days=180, active_days_per_week=2, reading_minutes=10,
                )), catalog, 71)
                with self.assertNumQueries(0):
                    for day in range(1, 181):
                        trial.config["reading_minutes"] = 0 if day in missed_days else 10
                        trial.daily(day)
                self.assertEqual(trial.quest_windows[self.voyager.pk]["start"], 16)
                self.assertEqual(trial.challenge_gates.completion_days[self.voyager.pk], completion)
                self.assertEqual(trial.quest_windows[self.voyager.pk]["progress"], 20)
                self.assertEqual(trial.counters["quest_completions"], 2)
                self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 2)
                self.assertEqual(trial.source_totals["reading"]["coins"], 260 - len(missed_days) * 5)
                self.assertFalse(next(row for row in trial.challenge_gates.report(trial)["targets"]
                                      if row["quest_id"] == self.voyager.pk)["expired"])

    def test_untimed_completion_supplies_one_finite_loot_draw_and_cannot_fund_a_pet_pair(self):
        # Completion loot chooses one item. No deadline must not turn one
        # onboarding completion into renewable eggs, potions or expedition loot.
        DropTable.objects.all().delete()
        egg = ItemDefinition.objects.filter(item_type="egg", pet_species__isnull=False).first()
        potion = ItemDefinition.objects.get(slug="base-potion")
        for item in (egg, potion):
            DropTable.objects.create(trigger_type="quest_complete", item=item, weight=1)
        catalog = self.catalog()
        catalog = replace(catalog, quests=FrozenRows(q for q in catalog.quests if q.pk == self.companion.pk))
        trial = Trial(normalize_config(quiet_config(
            horizon_days=90, reading_minutes=10, expeditions_per_day=1,
        )), catalog, 71)
        self.assertIn(f"quest:{self.companion.pk}", trial.finite_keys)
        self.assertFalse(any(key.startswith(("pet:", "middle:", "mount:")) for key in trial.finite_keys))
        self.assertNotIn("expedition_returned", trial._enabled_triggers())
        with self.assertNumQueries(0):
            for day in range(1, 91):
                trial.daily(day)
        self.assertEqual(trial.counters["quest_completions"], 1)
        self.assertEqual(trial.counters["drop_opportunities:quest_complete"], 1)
        self.assertEqual(sum(trial.inventory.values()), 1)
        self.assertFalse(trial.pets)
