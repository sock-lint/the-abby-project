"""Retry discovery describes the same frozen taxonomy checked by retry writes."""
from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.quests.controls import control_context, retry_challenge, retry_state
from apps.quests.goals import _occurrence
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyRetryProjectionTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "retry-projection-child"}]).children[0]
        self.category = SkillCategory.objects.create(name="Retry projection category")
        self.subject = Subject.objects.create(category=self.category, name="Retry projection subject")
        self.skill = Skill.objects.create(category=self.category, subject=self.subject, name="Retry projection skill")

    def expired(self, *, tag=True, filtered=False):
        definition = QuestDefinition.objects.create(name=f"Saved attempt {QuestDefinition.objects.count()}",
            is_system=True, quest_type="collection", target_value=2,
            trigger_filter={"allowed_triggers": ["chore_complete"]})
        now = timezone.now()
        goal = ChallengeGoal.objects.create(user=self.child, family=self.child.family, catalog_definition=definition,
            is_catalog=True, name=definition.name, metric="count", target=2, unit="actions", timezone_name="UTC",
            starts_at=now-timedelta(days=8), ends_at=now-timedelta(days=1),
            trigger_filter={"skill_category_id": self.category.pk} if filtered else {},
            skill_tags=[{"skill_id": self.skill.pk, "xp_weight": 1}] if tag else [])
        return _occurrence(goal, goal.starts_at)

    def assert_unavailable(self, occurrence):
        state = retry_state(occurrence, control_context(self.child))
        self.assertFalse(state["allowed"], state)
        self.assertEqual(state["reason"], "retired")
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            retry_challenge(self.child, occurrence.pk)
        self.assertFalse(ChallengeOccurrence.objects.filter(retry_of=occurrence).exists())

    def test_saved_reward_tags_reject_direct_and_inherited_retirement_even_after_definition_tags_change(self):
        occurrence = self.expired()
        self.assertTrue(retry_state(occurrence, control_context(self.child))["allowed"])
        for model, obj in ((Skill, self.skill), (Subject, self.subject), (SkillCategory, self.category)):
            with self.subTest(model=model.__name__):
                model.objects.filter(pk=obj.pk).update(is_retired=True)
                self.assert_unavailable(occurrence)
                model.objects.filter(pk=obj.pk).update(is_retired=False)

    def test_saved_filter_category_rejects_retirement_even_after_definition_filter_changes(self):
        occurrence = self.expired(tag=False, filtered=True)
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        self.assert_unavailable(occurrence)

    def test_existing_retry_replay_survives_retired_snapshot_choices(self):
        occurrence = self.expired()
        successor, created = retry_challenge(self.child, occurrence.pk)
        self.assertTrue(created)
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=True)
        replay, created = retry_challenge(self.child, occurrence.pk)
        self.assertFalse(created)
        self.assertEqual(replay.pk, successor.pk)
        self.assertEqual(ChallengeOccurrence.objects.filter(retry_of=occurrence).count(), 1)

    def test_snapshot_availability_is_batched_and_reused_by_repeated_projections(self):
        self.expired()
        with CaptureQueriesContext(connection) as single:
            control_context(self.child)
        for _ in range(7):
            self.expired()
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=True)
        with CaptureQueriesContext(connection) as multiple:
            context = control_context(self.child)
        self.assertLessEqual(len(multiple), len(single) + 1)
        rows = list(ChallengeOccurrence.objects.select_related("goal__catalog_definition"))
        with CaptureQueriesContext(connection) as projected:
            for _ in range(3):
                self.assertTrue(all(not retry_state(row, context)["allowed"] for row in rows))
        self.assertEqual(len(projected), 0)
