"""Fixed journal and untagged daily XP forecasts match persisted native awards."""
from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Badge, ProjectSkillTag, Skill, SkillCategory, SkillProgress, UserBadge
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.movement.models import MovementType
from apps.movement.services import MovementSessionService
from apps.projects.models import Project
from apps.quests.daily_bonus import process_daily_bonus
from apps.quests.models import ChallengeActivity, DailyBonus
from apps.rpg.models import RPGContentOverride
from apps.rpg.progression.catalog import load_catalog
from apps.rpg.progression.engine import Trial
from apps.timecards.models import TimeEntry
from apps.timecards.services import ClockService
from config.tests.factories import make_family


QUIET_CONFIG = {
    "horizon_days": 30, "trials": 1, "active_days_per_week": 7,
    "reading_minutes": 0, "project_minutes": 0, "chores_per_day": 0,
    "habits_per_day": 0, "movement_sessions_per_day": 0, "creations_per_day": 0,
    "journal_per_day": False, "expeditions_per_day": 0,
}
JOURNAL_CONFIG = {**QUIET_CONFIG, "journal_per_day": True}
# No Endurance choice is installed in this synthetic catalog, so Movement
# supplies no assumed source tag. Only the native daily fallback can earn XP.
UNTAGGED_CONFIG = {**QUIET_CONFIG, "movement_sessions_per_day": 1, "movement_minutes": 10}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LabFixedXPRoutesTests(TestCase):
    def setUp(self):
        cache.clear()
        family = make_family("Lab fixed XP routes", parents=[{
            "username": "lab-fixed-parent", "is_staff": True,
        }], children=[{"username": f"lab-fixed-child-{i}"} for i in range(3)])
        self.parent, self.children = family.parents[0], family.children
        self.language = SkillCategory.objects.create(name="Language Arts")
        self.life = SkillCategory.objects.create(name="Life Skills")
        self.other = SkillCategory.objects.create(name="Other practice")
        self.writing = Skill.objects.create(category=self.language, name="Creative Writing")
        self.vocabulary = Skill.objects.create(category=self.language, name="Vocabulary")
        self.persistence = Skill.objects.create(category=self.life, name="Persistence")

    def wire(self, name, params):
        with override_user(self.parent, scopes=frozenset({"mcp:catalog", "mcp:publish"})):
            result = async_to_sync(mcp.call_tool)(name, {"params": params, "confirmation": True})
        data = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", data, data)
        return data

    def report(self, config):
        private_tables = (
            "projects_user", "families_family", "achievements_skillprogress", "achievements_userbadge",
            "rewards_coinledger", "rpg_characterprofile", "rpg_userinventory", "chronicle_chronicleentry",
            "quests_challengeactivity", "quests_dailybonus",
            "timecards_timeentry", "movement_movementsession", "movement_movementdailycounter",
        )
        with CaptureQueriesContext(connection) as queries, patch(
            "apps.achievements.services.AwardService.grant", side_effect=AssertionError("Native forecast award"),
        ), patch("random.random", side_effect=AssertionError("Global RNG used by forecast")):
            result = self.wire("simulate_progression_scenario", {"config": config})
        for row in queries:
            self.assertTrue(row["sql"].lstrip().upper().startswith("SELECT"), row["sql"])
            for table in private_tables:
                self.assertNotIn(connection.ops.quote_name(table), row["sql"])
        return result

    def trial(self, config):
        # The retained identities are captured before Trial starts. Runtime
        # execution must stay detached even after its source rows change.
        catalog = load_catalog()
        with self.assertNumQueries(0), patch(
            "apps.achievements.services.AwardService.grant", side_effect=AssertionError("Native forecast writer"),
        ):
            trial = Trial(config, catalog, 3)
        return trial

    @staticmethod
    def source_xp(report, source):
        return next(row["xp"] for row in report["flows"]["sources"] if row["source"] == source)

    def progress(self, child):
        return dict(SkillProgress.objects.filter(user=child, xp_points__gt=0).values_list("skill_id", "xp_points"))

    def assert_journal(self, expected, *, child_index=0):
        report = self.report(JOURNAL_CONFIG)
        self.assertEqual(self.source_xp(report, "journal"), 30 * sum(expected.values()))
        trial = self.trial(JOURNAL_CONFIG)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertEqual(dict(trial.xp), expected)
        self.assertEqual(trial.source_totals["journal"]["xp"], sum(expected.values()))
        client = APIClient()
        child = self.children[child_index]
        client.force_authenticate(child)
        response = client.post("/api/chronicle/journal/", {
            "client_entry_id": str(uuid4()), "title": "Synthetic memory", "summary": "A saved practice memory.",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        receipt = response.data["reward_receipt"]
        self.assertEqual(receipt["xp_awarded"], sum(expected.values()))
        self.assertEqual({row["skill_id"]: row["xp"] for row in receipt["skills"]}, expected)
        self.assertEqual(self.progress(child), expected)

    def native_bonus(self, expected, *, raw_tags=None, child_index=0):
        child = self.children[child_index]
        fact = ChallengeActivity.objects.create(user=child, source_type="synthetic_lab_parity",
            source_id=str(uuid4()), trigger_type="chore_complete", occurred_at=timezone.now(),
            occurred_on=timezone.localdate(), context={"skill_tags": raw_tags or []})
        result = process_daily_bonus(child, fact)
        self.assertIsNotNone(result)
        self.assertEqual(result["xp_awarded"], sum(expected.values()))
        self.assertEqual(self.progress(child), expected)
        saved = list(DailyBonus.objects.filter(user=child).values())
        self.assertIsNone(process_daily_bonus(child, fact))
        self.assertEqual(list(DailyBonus.objects.filter(user=child).values()), saved)

    def assert_bonus(self, expected, *, child_index=0, config=None):
        config = config or UNTAGGED_CONFIG
        report = self.report(config)
        self.assertEqual(self.source_xp(report, "daily_bonus"), 30 * sum(expected.values()))
        trial = self.trial(config)
        with self.assertNumQueries(0):
            trial.daily(1)
        self.assertEqual(dict(trial.xp), expected)
        self.assertEqual(trial.source_totals["daily_bonus"]["xp"], sum(expected.values()))
        before = dict(trial.xp)
        with self.assertNumQueries(0):
            trial.daily_bonus([])
        self.assertEqual(dict(trial.xp), before)
        self.native_bonus(expected, child_index=child_index)
        return trial, report

    def retained(self, obj, name, category=None, *, version=1):
        lookup = {"name": name}
        if category is not None:
            lookup["category_id"] = category.pk
        RPGContentOverride.objects.create(family=self.parent.family, model_label=obj._meta.label_lower,
            object_id=obj.pk, source_lookup=lookup, values={"_authoring": {"version": version, "source": "mcp"}})

    def test_journal_source_less_canonical_routes_keep_ten_five_split(self):
        self.assertFalse(RPGContentOverride.objects.exists())
        self.assert_journal({self.writing.pk: 10, self.vocabulary.pk: 5})

    def test_journal_registered_category_rename_keeps_original_routes(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        self.assert_journal({self.writing.pk: 10, self.vocabulary.pk: 5})

    def test_journal_registered_skill_renames_keep_original_weights(self):
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Story practice"})
        self.wire("update_skill", {"skill_id": self.vocabulary.pk, "name": "Word practice"})
        self.assert_journal({self.writing.pk: 10, self.vocabulary.pk: 5})

    def test_journal_retired_reparented_renamed_skills_keep_installed_routes(self):
        self.wire("update_category", {"category_id": self.language.pk,
            "name": "Communication Arts", "is_retired": True})
        for skill, name in ((self.writing, "Story practice"), (self.vocabulary, "Word practice")):
            self.wire("update_skill", {"skill_id": skill.pk, "name": name,
                "category_id": self.other.pk, "clear_subject": True, "is_retired": True})
        self.assert_journal({self.writing.pk: 10, self.vocabulary.pk: 5})

    def test_journal_rename_restore_deduplicates_current_and_retained_same_identity(self):
        for index, name in enumerate(("Story practice", "Creative Writing")):
            self.wire("update_skill", {"skill_id": self.writing.pk, "name": name})
            self.assert_journal({self.writing.pk: 10, self.vocabulary.pk: 5}, child_index=index)

    def test_journal_current_and_retained_categories_fail_closed(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        namesake = SkillCategory.objects.create(name="Language Arts")
        Skill.objects.create(category=namesake, name="Creative Writing")
        Skill.objects.create(category=namesake, name="Vocabulary")
        self.assert_journal({})

    def test_journal_empty_current_category_still_makes_retained_route_ambiguous(self):
        self.wire("update_category", {"category_id": self.language.pk, "name": "Communication Arts"})
        SkillCategory.objects.create(name="Language Arts")
        self.assert_journal({})

    def test_journal_distinct_retained_category_cannot_redirect_award(self):
        self.retained(self.other, "Language Arts")
        self.assert_journal({})

    def test_journal_ambiguous_writing_routes_all_fifteen_to_surviving_vocabulary(self):
        self.wire("update_skill", {"skill_id": self.writing.pk, "name": "Story practice"})
        Skill.objects.create(category=self.language, name="Creative Writing")
        self.assert_journal({self.vocabulary.pk: 15})

    def test_journal_distinct_retained_writing_preserves_only_unambiguous_tag(self):
        rogue = Skill.objects.create(category=self.other, name="Other practice writing")
        self.retained(rogue, "Creative Writing", self.language)
        self.assert_journal({self.vocabulary.pk: 15})

    def test_journal_missing_writing_routes_full_pool_to_vocabulary(self):
        self.writing.delete()
        self.assert_journal({self.vocabulary.pk: 15})

    def test_journal_missing_vocabulary_routes_full_pool_to_writing(self):
        self.vocabulary.delete()
        self.assert_journal({self.writing.pk: 15})

    def test_journal_missing_destinations_never_use_foreign_category_namesakes(self):
        self.writing.delete()
        self.vocabulary.delete()
        Skill.objects.create(category=self.other, name="Creative Writing")
        Skill.objects.create(category=self.other, name="Vocabulary")
        self.assert_journal({})

    def test_journal_locked_writing_stays_in_weighted_denominator(self):
        self.wire("update_skill", {"skill_id": self.writing.pk, "is_locked_by_default": True})
        self.assert_journal({self.vocabulary.pk: 5})

    def test_journal_locked_renamed_vocabulary_stays_in_weighted_denominator(self):
        self.wire("update_skill", {"skill_id": self.vocabulary.pk,
            "name": "Word practice", "is_locked_by_default": True})
        self.assert_journal({self.writing.pk: 10})

    def test_journal_inexact_provenance_cannot_restore_missing_route(self):
        self.writing.name = "Story practice"
        self.writing.save(update_fields=["name"])
        self.retained(self.writing, "Creative Writing", self.language, version=2)
        self.assert_journal({self.vocabulary.pk: 15})

    def test_daily_canonical_fallback_is_independent_of_missing_movement_tag(self):
        self.assert_bonus({self.persistence.pk: 20})

    def test_daily_registered_skill_rename_keeps_original_fallback(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice"})
        self.assert_bonus({self.persistence.pk: 20})

    def test_daily_registered_category_rename_keeps_original_fallback(self):
        self.wire("update_category", {"category_id": self.life.pk, "name": "Everyday practice"})
        self.assert_bonus({self.persistence.pk: 20})

    def test_daily_retired_reparented_renamed_fallback_still_awards(self):
        self.wire("update_category", {"category_id": self.life.pk,
            "name": "Everyday practice", "is_retired": True})
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice",
            "category_id": self.other.pk, "clear_subject": True, "is_retired": True})
        self.assert_bonus({self.persistence.pk: 20})

    def test_daily_rename_restore_deduplicates_current_and_retained_identity(self):
        for index, name in enumerate(("Steady practice", "Persistence")):
            self.wire("update_skill", {"skill_id": self.persistence.pk, "name": name})
            self.assert_bonus({self.persistence.pk: 20}, child_index=index)

    def test_daily_current_and_retained_categories_do_not_redirect_fallback(self):
        self.wire("update_category", {"category_id": self.life.pk, "name": "Everyday practice"})
        namesake = SkillCategory.objects.create(name="Life Skills")
        Skill.objects.create(category=namesake, name="Persistence")
        self.assert_bonus({})

    def test_daily_distinct_retained_skill_does_not_redirect_fallback(self):
        rogue = Skill.objects.create(category=self.other, name="Other steady practice")
        self.retained(rogue, "Persistence", self.life)
        self.assert_bonus({})

    def test_daily_missing_original_ignores_same_name_in_other_category(self):
        self.persistence.delete()
        Skill.objects.create(category=self.other, name="Persistence")
        self.assert_bonus({})

    def test_daily_locked_installed_fallback_preserves_native_eligibility(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "is_locked_by_default": True})
        self.assert_bonus({})

    def test_daily_fallback_does_not_change_synthetic_chore_tag_assumption(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice"})
        config = {**QUIET_CONFIG, "chores_per_day": 1, "chore_xp": 10, "chore_coins": 0}
        trial, report = self.assert_bonus({self.persistence.pk: 20}, config=config)
        self.assertEqual(trial.tags["chores"], [])
        self.assertEqual(self.source_xp(report, "chores"), 0)

    def assert_explicit_bonus(self, tags, expected, *, raw_tags=None):
        trial = self.trial(QUIET_CONFIG)
        trial.day = 1
        with self.assertNumQueries(0):
            trial.daily_bonus(tags(trial))
        self.assertEqual(dict(trial.xp), expected)
        self.assertEqual(trial.source_totals["daily_bonus"]["xp"], sum(expected.values()))
        self.native_bonus(expected, raw_tags=raw_tags)

    def test_daily_nonempty_source_tags_precede_renamed_fallback(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice"})
        physical = SkillCategory.objects.create(name="Physical")
        endurance = Skill.objects.create(category=physical, name="Endurance")
        report = self.report(UNTAGGED_CONFIG)
        self.assertEqual(self.source_xp(report, "daily_bonus"), 600)
        self.assert_explicit_bonus(lambda trial: trial.tags["movement"], {endurance.pk: 20},
            raw_tags=[{"skill_id": endurance.pk, "xp_weight": 1}])

    def test_daily_explicit_weights_keep_native_rounding(self):
        raw = [{"skill_id": self.writing.pk, "xp_weight": 2},
               {"skill_id": self.vocabulary.pk, "xp_weight": 1}]
        self.assert_explicit_bonus(lambda trial: [SimpleNamespace(skill=trial.catalog.skills[row["skill_id"]],
            xp_weight=row["xp_weight"]) for row in raw], {self.writing.pk: 13, self.vocabulary.pk: 7}, raw_tags=raw)

    def test_daily_equal_weights_preserve_per_tag_rounding_without_remainder_rewrite(self):
        raw = [{"skill_id": skill.pk, "xp_weight": 1}
               for skill in (self.writing, self.vocabulary, self.persistence)]
        self.assert_explicit_bonus(lambda trial: [SimpleNamespace(skill=trial.catalog.skills[row["skill_id"]],
            xp_weight=1) for row in raw], {row["skill_id"]: 7 for row in raw}, raw_tags=raw)

    def test_daily_nonempty_locked_tag_does_not_fall_back(self):
        self.wire("update_skill", {"skill_id": self.writing.pk, "is_locked_by_default": True})
        self.assert_explicit_bonus(lambda trial: [SimpleNamespace(skill=trial.catalog.skills[self.writing.pk],
            xp_weight=1)], {}, raw_tags=[{"skill_id": self.writing.pk, "xp_weight": 1}])

    def test_daily_nonempty_zero_weight_tag_does_not_fall_back(self):
        self.assert_explicit_bonus(lambda trial: [SimpleNamespace(skill=trial.catalog.skills[self.writing.pk],
            xp_weight=0)], {}, raw_tags=[{"skill_id": self.writing.pk, "xp_weight": 0}])

    def test_daily_nonempty_missing_tag_does_not_fall_back(self):
        missing = max(self.writing.pk, self.vocabulary.pk, self.persistence.pk) + 1000
        self.assert_explicit_bonus(lambda trial: [SimpleNamespace(skill=SimpleNamespace(pk=missing), xp_weight=1)], {},
            raw_tags=[{"skill_id": missing, "xp_weight": 1}])

    def test_daily_fixed_fallback_contributes_to_reachable_badges(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice"})
        badge = Badge.objects.create(name="Steady practice mastery", criteria_type="category_mastery",
            criteria_value={"category": "Life Skills", "min_level": 1}, xp_bonus=0, award_coins=False)
        trial, report = self.assert_bonus({self.persistence.pk: 20})
        self.assertIn(f"badge:{badge.pk}", trial.finite_keys)
        self.assertEqual(report["summary"]["finite_content_total"], 1)
        self.assertEqual(report["trace"][-1]["badges_p50"], 1)

    def assert_minute_reachability(self, project_minutes, movement_minutes, *, finite, daily_xp, project_xp=0):
        badge = Badge.objects.create(name="Short practice mastery", criteria_type="category_mastery",
            criteria_value={"category": "Life Skills", "min_level": 1}, xp_bonus=0, award_coins=False)
        config = {**QUIET_CONFIG, "project_minutes": project_minutes,
            "movement_sessions_per_day": int(bool(movement_minutes)), "movement_minutes": movement_minutes or 10}
        report = self.report(config)
        trial = self.trial(config)
        with self.assertNumQueries(0):
            trial.daily(1)
        flows = {row["source"]: row for row in report["flows"]["sources"]}
        self.assertEqual(flows.get("daily_bonus", {}).get("xp", 0), daily_xp * 30)
        self.assertEqual(flows.get("project_time", {}).get("xp", 0), project_xp * 30)
        self.assertEqual(dict(trial.xp), {self.persistence.pk: daily_xp + project_xp}
            if daily_xp + project_xp else {})

        child = self.children[0]
        project = Project.objects.create(title="Synthetic short practice", created_by=self.parent,
            assigned_to=child, status="in_progress")
        # Match the Lab's explicit project-tag assumption, including when the
        # native rounded pool is zero. Movement intentionally has no tags.
        ProjectSkillTag.objects.create(project=project, skill=self.persistence, xp_weight=1)
        movement = MovementType.objects.create(name="Synthetic untagged practice", slug="lab-short-practice")
        for index in range(5):
            now = datetime(2026, 10, 20, 19, tzinfo=dt_timezone.utc) + timedelta(days=index)
            with patch("django.utils.timezone.now", return_value=now):
                if project_minutes:
                    TimeEntry.objects.create(user=child, project=project,
                        clock_in=now - timedelta(minutes=project_minutes), status="active")
                    saved = ClockService.clock_out(child)
                    self.assertEqual(saved.duration_minutes, project_minutes)
                if movement_minutes:
                    MovementSessionService.log_session(child, movement_type=movement,
                        duration_minutes=movement_minutes, client_request_id=uuid4())
        self.assertEqual(self.progress(child), {self.persistence.pk: 5 * (daily_xp + project_xp)}
            if daily_xp + project_xp else {})
        self.assertEqual(list(DailyBonus.objects.filter(user=child).order_by("date")
            .values_list("xp_awarded", flat=True)), [daily_xp] * 5 if daily_xp else [])
        earned = 5 * (daily_xp + project_xp) >= 100
        self.assertEqual(UserBadge.objects.filter(user=child, badge=badge).exists(), earned)
        # Finite content means eventually reachable under this same routine;
        # the horizon can still be too short to earn that reachable badge.
        self.assertEqual(f"badge:{badge.pk}" in trial.finite_keys, finite)
        self.assertEqual(report["summary"]["finite_content_total"], int(finite))
        self.assertEqual(report["trace"][-1]["badges_p50"], int(30 * (daily_xp + project_xp) >= 100))

    def test_combined_project_and_untagged_movement_minutes_reach_daily_mastery(self):
        self.assert_minute_reachability(2, 8, finite=True, daily_xp=20)

    def test_combined_minutes_reach_retained_daily_mastery_after_skill_rename(self):
        self.wire("update_skill", {"skill_id": self.persistence.pk, "name": "Steady practice"})
        self.assert_minute_reachability(2, 8, finite=True, daily_xp=20)

    def test_nine_combined_minutes_cannot_pay_or_advertise_mastery(self):
        self.assert_minute_reachability(2, 7, finite=False, daily_xp=0)

    def test_three_project_minutes_round_to_zero_and_cannot_advertise_mastery(self):
        self.assert_minute_reachability(3, 0, finite=False, daily_xp=0)

    def test_four_project_minutes_earn_one_xp_and_keep_eventual_mastery_reachable(self):
        self.assert_minute_reachability(4, 0, finite=True, daily_xp=0, project_xp=1)

    def test_ten_untagged_movement_minutes_keep_daily_mastery_reachable(self):
        self.assert_minute_reachability(0, 10, finite=True, daily_xp=20)
