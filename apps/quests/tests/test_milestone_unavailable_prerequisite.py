"""Milestone offers whose one-time prerequisite can no longer finish are hidden."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress
from apps.quests.goals import ingest_activity, list_goals
from apps.quests.milestone_eligibility import prerequisite_unavailable
from apps.quests.models import ChallengeGoal, QuestDefinition
from config.tests.factories import make_family

READING = {"allowed_triggers": ["reading_logged"]}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UnavailablePrerequisiteTests(TestCase):
    def setUp(self):
        family = make_family("Expired prerequisite family", parents=[{"username": "dead-parent"}],
                             children=[{"username": "dead-child"}])
        self.child = family.children[0]
        category = SkillCategory.objects.create(name="Dead-end reading")
        self.skill = Skill.objects.create(name="Reading Comprehension", category=category)
        self.prior = QuestDefinition.objects.create(
            name="Reading Companion", description="Starter", quest_type="collection",
            target_value=3, duration_days=14, is_system=True, trigger_filter=READING,
        )
        self.voyager = self.gated("Reading Voyager", self.prior, duration_days=56, target=20)
        SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=100, level=1)
        self.start = timezone.now()

    def gated(self, name, prerequisite, *, duration_days=28, target=10):
        definition = QuestDefinition(
            name=name, description=name, quest_type="collection", target_value=target,
            duration_days=duration_days, is_system=True, trigger_filter=READING,
            prerequisite_quest=prerequisite, required_skill=self.skill, required_skill_level=1,
        )
        definition.full_clean()
        definition.save()
        return definition

    def at(self, days):
        return patch("django.utils.timezone.now", return_value=self.start + timedelta(days=days))

    def locked_ids(self, days):
        with self.at(days):
            return [row["id"] for row in list_goals(self.child)["locked_catalog"]]

    def test_expired_one_time_prerequisite_hides_its_successor(self):
        self.assertIn(self.voyager.pk, self.locked_ids(0))
        self.assertTrue(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.prior).exists())
        with self.at(31):
            ingest_activity(self.child, "reading_logged", "late-reading", "reading_logged",
                            occurred_at=timezone.now(), fresh_milestone=True)
            payload = list_goals(self.child)
            self.assertTrue(prerequisite_unavailable(self.child, self.prior.pk))
        self.assertNotIn(self.voyager.pk, [row["id"] for row in payload["locked_catalog"]])
        prior_row = next(row for row in payload["results"] if row["name"] == self.prior.name)
        self.assertEqual(prior_row["status"], "expired")
        self.assertFalse(ChallengeGoal.objects.filter(user=self.child, catalog_definition=self.voyager).exists())

    def test_child_challenges_response_omits_the_dead_end(self):
        client = APIClient()
        client.force_authenticate(self.child)
        with self.at(0):
            client.get("/api/challenges/")
        with self.at(31):
            response = client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.voyager.pk, [row["id"] for row in response.data["locked_catalog"]])

    def test_open_prerequisite_window_keeps_the_successor_listed(self):
        self.locked_ids(0)
        self.assertIn(self.voyager.pk, self.locked_ids(13))
        with self.at(13):
            self.assertFalse(prerequisite_unavailable(self.child, self.prior.pk))

    def test_prerequisite_without_an_accepted_window_stays_available(self):
        self.assertFalse(prerequisite_unavailable(self.child, self.prior.pk))

    def test_repeatable_prerequisite_never_dead_ends(self):
        QuestDefinition.objects.filter(pk=self.prior.pk).update(is_repeatable=True)
        self.locked_ids(0)
        self.assertIn(self.voyager.pk, self.locked_ids(31))

    def test_gated_prerequisite_inherits_an_expired_upstream_window(self):
        bridge = self.gated("Reading Bridge", self.prior)
        QuestDefinition.objects.filter(pk=self.voyager.pk).update(prerequisite_quest=bridge)
        self.assertEqual(set(self.locked_ids(0)), {bridge.pk, self.voyager.pk})
        self.assertEqual(self.locked_ids(31), [])
        with self.at(31):
            self.assertTrue(prerequisite_unavailable(self.child, bridge.pk))
