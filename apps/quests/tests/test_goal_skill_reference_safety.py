"""Saved JSON reward promises must not race with removal of their skill."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings

from apps.achievements.models import Skill, SkillCategory
from apps.quests.controls import update_schedule
from apps.quests.goal_serializers import GoalWriteSerializer
from apps.quests.goals import create_goal
from apps.quests.models import ChallengeGoal, ChallengeSchedule
from apps.rpg.content.taxonomy_deletion import TaxonomyInUse, delete_taxonomy
from config.tests.factories import make_family


class GoalSkillFixtures:
    def setUp(self):
        own = make_family("Skill promise", parents=[{"username": "promise-parent", "is_staff": True}],
                          children=[{"username": "promise-child"}])
        other = make_family("Skill deletion", parents=[{"username": "promise-deleter", "is_staff": True}])
        self.parent, self.child, self.deleter = own.parents[0], own.children[0], other.parents[0]
        self.skill = Skill.objects.create(name="Promise skill", category=SkillCategory.objects.create(name="Promise taxonomy"))

    def data(self, **values):
        return {"name": "Saved chores", "description": "Synthetic", "metric": "count", "target": Decimal(2),
                "unit": "actions", "trigger_type": "chore_complete", "period": "this_week", "repeat_weekly": True,
                "coin_reward": 0, "xp_reward": 15, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}], **values}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GoalSkillValidationTests(GoalSkillFixtures, TestCase):
    def test_goal_rechecks_a_skill_deleted_after_request_validation(self):
        serializer = GoalWriteSerializer(data={**self.data(), "user_id": self.child.pk},
                                         context={"request": SimpleNamespace(user=self.parent)})
        serializer.is_valid(raise_exception=True)
        self.skill.delete()
        with self.assertRaisesRegex(ValueError, "existing skills"):
            create_goal(self.parent, self.child, serializer.validated_data)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_future_setup_rechecks_a_skill_deleted_after_validation(self):
        occurrence = create_goal(self.parent, self.child, self.data(xp_reward=0, skill_tags=[]))
        original = GoalWriteSerializer.is_valid

        def validate_then_remove(serializer, **kwargs):
            result = original(serializer, **kwargs)
            Skill.objects.filter(pk=self.skill.pk).delete()
            return result

        with patch.object(GoalWriteSerializer, "is_valid", validate_then_remove):
            with self.assertRaisesRegex(ValueError, "existing skills"):
                update_schedule(self.parent, occurrence.goal_id, {"expected_revision": 0, "next_week": {
                    "xp_reward": 15, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}],
                }})
        self.assertFalse(ChallengeSchedule.objects.exists())
        occurrence.goal.refresh_from_db()
        self.assertEqual(occurrence.goal.schedule_revision, 0)


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GoalSkillDeletionConcurrencyTests(GoalSkillFixtures, TransactionTestCase):
    def assert_writer_preserves_skill(self, model, method, action):
        writer_ready, release, deletion_done = Event(), Event(), Event()
        pids = {}
        original = getattr(model.objects, method)

        def pause_write(*args, **kwargs):
            writer_ready.set()
            if not release.wait(8):
                raise RuntimeError("Writer was not released")
            return original(*args, **kwargs)

        def run(role, callback):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '6s'")
                    cursor.execute("SET statement_timeout = '12s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[role] = cursor.fetchone()[0]
                return callback()
            finally:
                if role == "deletion":
                    deletion_done.set()
                connection.close()

        def delete():
            try:
                delete_taxonomy(self.deleter, Skill, self.skill.pk)
                return "deleted"
            except TaxonomyInUse:
                return "in_use"

        blocked = False
        with patch.object(model.objects, method, pause_write), ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(run, "writer", action)
            deletion = None
            try:
                self.assertTrue(writer_ready.wait(5), "Writer never reached its persistence boundary")
                deletion = pool.submit(run, "deletion", delete)
                deadline = monotonic() + 5
                while monotonic() < deadline and not deletion_done.is_set():
                    if "deletion" in pids:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [pids["writer"], pids["deletion"]])
                            blocked = cursor.fetchone()[0]
                        if blocked:
                            break
                    deletion_done.wait(0.01)
            finally:
                release.set()
            writer.result(timeout=15)
            self.assertIsNotNone(deletion)
            outcome = deletion.result(timeout=15)
        self.assertTrue(blocked, "Deletion did not wait for the new JSON reward promise")
        self.assertEqual(outcome, "in_use")
        self.assertTrue(Skill.objects.filter(pk=self.skill.pk).exists())

    def test_new_goal_holds_skill_until_its_reward_promise_commits(self):
        self.assert_writer_preserves_skill(ChallengeGoal, "create", lambda: create_goal(self.parent, self.child, self.data()))
        self.assertEqual(ChallengeGoal.objects.get().skill_tags, self.data()["skill_tags"])

    def test_future_setup_holds_skill_until_its_reward_promise_commits(self):
        occurrence = create_goal(self.parent, self.child, self.data(xp_reward=0, skill_tags=[]))
        self.assert_writer_preserves_skill(ChallengeSchedule, "update_or_create", lambda: update_schedule(
            self.parent, occurrence.goal_id, {"expected_revision": 0, "next_week": {
                "xp_reward": 15, "skill_tags": self.data()["skill_tags"],
            }},
        ))
        self.assertEqual(ChallengeSchedule.objects.get().snapshot["skill_tags"], self.data()["skill_tags"])
