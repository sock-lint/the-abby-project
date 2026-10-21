"""Accepted recurring rules retain rewards when their taxonomy is archived."""
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory, SkillProgress, Subject
from apps.quests.controls import schedule_payload, update_schedule
from apps.quests.goals import create_goal, ingest_activity, list_goals
from apps.quests.models import ChallengeOccurrence, QuestDefinition, QuestSkillTag
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RetainedRecurringPromiseReviewTests(TestCase):
    def setUp(self):
        family = make_family("Retained recurring review", parents=[{"username": "retained-parent"}],
                             children=[{"username": "retained-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        family.family.timezone = "UTC"
        family.family.save(update_fields=["timezone"])
        self.category = SkillCategory.objects.create(name="Retained category")
        self.subject = Subject.objects.create(name="Retained subject", category=self.category)
        self.skill = Skill.objects.create(name="Retained skill", category=self.category, subject=self.subject)
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1, unlocked=True)
        self.accepted_at = datetime(2026, 10, 19, 12, tzinfo=datetime_timezone.utc)
        suppress_drops = patch("apps.rpg.services.DropService.award_accomplishment", return_value=[])
        suppress_drops.start()
        self.addCleanup(suppress_drops.stop)

    def weekly(self):
        with patch("django.utils.timezone.now", return_value=self.accepted_at):
            return create_goal(self.parent, self.child, {
                "name": "Accepted standing reward", "description": "A weekly promise",
                "metric": "count", "target": Decimal(1), "unit": "actions",
                "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
                "coin_reward": 7, "xp_reward": 15,
                "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
            })

    def finish_next_week(self, original):
        at = self.accepted_at + timedelta(days=7)
        with patch("django.utils.timezone.now", return_value=at):
            advertised = schedule_payload(original.goal)["next_week"]
            self.assertEqual((advertised["coin_reward"], advertised["xp_reward"]), (7, 15))
            ingest_activity(self.child, "chore_complete", "next-week-approved", "chore_complete",
                            occurred_at=at, occurred_on=at.date())
        return list(ChallengeOccurrence.objects.filter(goal=original.goal).exclude(pk=original.pk))

    def assert_standing_reward(self, original, *, deleted=False):
        original_snapshot = original.snapshot.copy()
        rows = self.finish_next_week(original)
        actual = {
            "new_windows": len(rows),
            "coins": list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)),
            "receipt_xp": rows[0].reward_receipt.get("xp") if rows else None,
            "skill_xp": list(SkillProgress.objects.filter(user=self.child).values_list("xp_points", flat=True)),
        }
        self.assertEqual(actual, {
            "new_windows": 1, "coins": [7], "receipt_xp": 0 if deleted else 15,
            "skill_xp": [] if deleted else [115],
        }, "Accepted recurring rewards must survive saved taxonomy retirement/deletion.")
        self.assertEqual(rows[0].snapshot["skill_tags"], original_snapshot["skill_tags"])
        original.refresh_from_db()
        self.assertEqual(original.snapshot, original_snapshot)

    def test_saved_weekly_rule_keeps_retired_skill_rewards(self):
        original = self.weekly()
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        self.assert_standing_reward(original)

    def test_saved_weekly_rule_keeps_inherited_retired_category_rewards(self):
        original = self.weekly()
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        self.assert_standing_reward(original)

    def test_saved_weekly_rule_keeps_coins_without_inventing_xp_for_deleted_skill(self):
        original = self.weekly()
        self.skill.delete()  # A saved JSON reference that can predate this upgrade.
        self.assert_standing_reward(original, deleted=True)

    def test_accepted_future_version_keeps_its_setup_after_retirement(self):
        original = self.weekly()
        original_snapshot = original.snapshot.copy()
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        with patch("django.utils.timezone.now", return_value=self.accepted_at):
            update_schedule(self.parent, original.goal_id, {"expected_revision": 0, "next_week": {
                "name": "Accepted future reward", "target": 2, "coin_reward": 9,
            }})
        at = self.accepted_at + timedelta(days=7)
        with patch("django.utils.timezone.now", return_value=at):
            for index in range(2):
                ingest_activity(self.child, "chore_complete", f"future-version-{index}", "chore_complete",
                                occurred_at=at, occurred_on=at.date())
        following = original.goal.occurrences.exclude(pk=original.pk).get()
        self.assertEqual((following.snapshot["name"], following.snapshot["target"], following.snapshot["coins"]),
                         ("Accepted future reward", "2", 9))
        self.assertEqual(following.reward_receipt, {"coins": 9, "xp": 15, "items": []})
        self.assertEqual(SkillProgress.objects.get(user=self.child).xp_points, 115)
        original.refresh_from_db()
        self.assertEqual(original.snapshot, original_snapshot)

    def test_saved_repeat_catalog_rule_keeps_retired_subject_rewards(self):
        with patch("django.utils.timezone.now", return_value=self.accepted_at):
            definition = QuestDefinition.objects.create(
                name="Accepted repeated catalog reward", quest_type="collection", target_value=1,
                duration_days=1, is_system=True, is_repeatable=True, coin_reward=7, xp_reward=15,
                trigger_filter={"allowed_triggers": ["chore_complete"]},
            )
            QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
            list_goals(self.child)
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=True)
        at = self.accepted_at + timedelta(days=1, hours=1)
        with patch("django.utils.timezone.now", return_value=at):
            ingest_activity(self.child, "chore_complete", "next-cycle-approved", "chore_complete",
                            occurred_at=at, occurred_on=at.date())
        self.assertEqual({
            "windows": ChallengeOccurrence.objects.filter(goal__catalog_definition=definition).count(),
            "coins": list(CoinLedger.objects.filter(user=self.child).values_list("amount", flat=True)),
            "skill_xp": SkillProgress.objects.get(user=self.child).xp_points,
        }, {"windows": 2, "coins": [7], "skill_xp": 115})

    def test_saved_repeat_category_filter_keeps_its_matching_boundary(self):
        with patch("django.utils.timezone.now", return_value=self.accepted_at):
            definition = QuestDefinition.objects.create(
                name="Accepted category rule", quest_type="collection", target_value=1,
                duration_days=1, is_system=True, is_repeatable=True, coin_reward=7, xp_reward=0,
                trigger_filter={"allowed_triggers": ["chore_complete"], "skill_category_id": self.category.pk},
            )
            list_goals(self.child)
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        at = self.accepted_at + timedelta(days=1, hours=1)
        with patch("django.utils.timezone.now", return_value=at):
            ingest_activity(self.child, "chore_complete", "wrong-saved-category", "chore_complete",
                            occurred_at=at, occurred_on=at.date())
            following = ChallengeOccurrence.objects.filter(goal__catalog_definition=definition).latest("starts_at")
            self.assertEqual(following.progress, 0)
            self.assertEqual(following.snapshot["filter"]["skill_category_id"], self.category.pk)
            ingest_activity(self.child, "chore_complete", "right-saved-category", "chore_complete",
                            occurred_at=at, occurred_on=at.date(), context={"skill_category_id": self.category.pk})
        following.refresh_from_db()
        self.assertEqual(following.reward_receipt, {"coins": 7, "xp": 0, "items": []})
