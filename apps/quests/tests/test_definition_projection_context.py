"""Accepted history and new admission use different taxonomy boundaries."""
from datetime import timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, SkillProgress, Subject
from apps.quests.milestone_eligibility import milestone_eligibility
from apps.quests.models import ChallengeGoal, Quest, QuestDefinition, QuestParticipant, QuestSkillTag
from apps.quests.reference_locks import admit_definition_choices
from apps.quests.serializers import QuestDefinitionSerializer, QuestSerializer
from apps.quests.services import QuestService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DefinitionProjectionContextTests(TestCase):
    def setUp(self):
        self.child = make_family(children=[{"username": "definition-projection"}]).children[0]
        self.category = SkillCategory.objects.create(name="Projection category")
        self.subject = Subject.objects.create(category=self.category, name="Projection subject")
        self.skill = Skill.objects.create(category=self.category, subject=self.subject, name="Projection skill")
        self.definition = QuestDefinition.objects.create(
            name="Retained promise", quest_type="collection", target_value=5, is_system=True,
        )

    def test_nested_definition_keeps_offer_eligibility_without_losing_accepted_tags(self):
        tag = QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill, xp_weight=2)
        progress = SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=75)
        quest = Quest.objects.create(
            definition=self.definition, end_date=timezone.now() + timedelta(days=1),
            reward_items_snapshot=[],
        )
        QuestParticipant.objects.create(quest=quest, user=self.child)
        context = {"eligibility_user": self.child}
        for model, obj in ((Skill, self.skill), (Subject, self.subject), (SkillCategory, self.category)):
            with self.subTest(retired=model.__name__):
                model.objects.filter(pk=obj.pk).update(is_retired=True)
                accepted = QuestSerializer(quest, context=context).data
                offer = QuestDefinitionSerializer(self.definition, context=context).data
                self.assertFalse(accepted["definition"]["milestone_eligibility"]["unlocked"])
                self.assertEqual(accepted["definition"]["skill_tags"][0]["id"], tag.pk)
                self.assertEqual(accepted["definition"]["skill_tags"][0]["skill"], self.skill.pk)
                self.assertFalse(offer["milestone_eligibility"]["unlocked"])
                self.assertEqual(offer["milestone_eligibility"]["requirements"][0]["kind"], "taxonomy")
                with self.assertRaisesRegex(ValueError, "[Rr]etired"):
                    QuestService.start_quest(self.child, self.definition.pk)
                progress.refresh_from_db()
                self.assertEqual(progress.xp_points, 75)
                self.assertEqual(Quest.objects.count(), 1)
                model.objects.filter(pk=obj.pk).update(is_retired=False)
        self.assertEqual(context, {"eligibility_user": self.child})

    def test_empty_prefetched_tags_need_no_query_and_unprefetched_tags_still_work(self):
        prefetched = QuestDefinition.objects.prefetch_related("skill_tags").get(pk=self.definition.pk)
        with self.assertNumQueries(0):
            admit_definition_choices(prefetched)
        fallback = QuestDefinition.objects.get(pk=self.definition.pk)
        with self.assertNumQueries(1):
            admit_definition_choices(fallback)

    def test_taxonomy_free_eligibility_uses_empty_prefetch_and_preserves_fallback(self):
        prefetched = QuestDefinition.objects.prefetch_related("skill_tags").get(pk=self.definition.pk)
        with self.assertNumQueries(0):
            self.assertTrue(milestone_eligibility(self.child, prefetched)["unlocked"])
        fallback = QuestDefinition.objects.get(pk=self.definition.pk)
        with self.assertNumQueries(2):
            self.assertTrue(milestone_eligibility(self.child, fallback)["unlocked"])

    def test_prefetched_reference_ids_still_receive_fresh_retirement_admission(self):
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)
        prefetched = QuestDefinition.objects.prefetch_related(
            "skill_tags__skill__category", "skill_tags__skill__subject",
        ).get(pk=self.definition.pk)
        admit_definition_choices(prefetched)
        for model, obj in ((Skill, self.skill), (Subject, self.subject), (SkillCategory, self.category)):
            with self.subTest(retired=model.__name__):
                model.objects.filter(pk=obj.pk).update(is_retired=True)
                for definition in (prefetched, QuestDefinition.objects.get(pk=self.definition.pk)):
                    self.assertFalse(milestone_eligibility(self.child, definition)["unlocked"])
                    with self.assertRaisesRegex(ValueError, "[Rr]etired"):
                        admit_definition_choices(definition)
                model.objects.filter(pk=obj.pk).update(is_retired=False)

    def test_category_filter_prevents_the_empty_tag_fast_path(self):
        self.definition.trigger_filter = {"skill_category_id": self.category.pk}
        self.definition.save(update_fields=["trigger_filter"])
        prefetched = QuestDefinition.objects.prefetch_related("skill_tags").get(pk=self.definition.pk)
        SkillCategory.objects.filter(pk=self.category.pk).update(is_retired=True)
        for definition in (prefetched, QuestDefinition.objects.get(pk=self.definition.pk)):
            self.assertFalse(milestone_eligibility(self.child, definition)["unlocked"])
            with self.assertRaisesRegex(ValueError, "[Rr]etired"):
                admit_definition_choices(definition)

    def test_warm_tagged_legacy_history_skips_new_admission_with_constant_queries(self):
        def accepted(definition, status):
            QuestSkillTag.objects.create(quest_definition=definition, skill=self.skill)
            quest = Quest.objects.create(definition=definition, status=status,
                end_date=timezone.now() + timedelta(days=1), reward_items_snapshot=[])
            QuestParticipant.objects.create(quest=quest, user=self.child)
            return quest

        quests = [accepted(self.definition, "completed")]
        client = APIClient()
        client.force_authenticate(self.child)
        client.get("/api/challenges/")
        with CaptureQueriesContext(connection) as small:
            response = client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        for index in range(4):
            for status in ("active", "completed"):
                definition = QuestDefinition.objects.create(name=f"Tagged legacy {index} {status}",
                    quest_type="collection", target_value=5, is_system=True)
                quests.append(accepted(definition, status))
        with CaptureQueriesContext(connection) as large:
            response = client.get("/api/challenges/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data["results"]},
            {f"legacy:{quest.pk}" for quest in quests})
        self.assertFalse(ChallengeGoal.objects.exists())
        self.assertFalse(SkillProgress.objects.exists())
        self.assertEqual(len(large), len(small), f"Tagged legacy reads grew: {len(small)} -> {len(large)}")

    def test_genuinely_new_catalog_promise_still_checks_current_tag_retirement(self):
        QuestSkillTag.objects.create(quest_definition=self.definition, skill=self.skill)
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=True)
        client = APIClient()
        client.force_authenticate(self.child)
        blocked = client.get("/api/challenges/")
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.data["results"], [])
        self.assertFalse(ChallengeGoal.objects.exists())
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=False)
        restored = client.get("/api/challenges/")
        self.assertEqual(restored.status_code, 200)
        goal = ChallengeGoal.objects.get()
        self.assertEqual(goal.catalog_definition_id, self.definition.pk)
        self.assertEqual(goal.skill_tags, [{"skill_id": self.skill.pk, "xp_weight": 1}])
        self.assertFalse(SkillProgress.objects.exists())
