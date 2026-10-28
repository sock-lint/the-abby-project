"""Source category snapshots follow native XP contracts and preserve saved receipts."""

from copy import deepcopy
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from django.utils import timezone

from apps.achievements.models import MilestoneSkillTag, ProjectSkillTag, Skill, SkillCategory, SkillProgress
from apps.chores.models import Chore, ChoreCompletion, ChoreSkillTag
from apps.chores.services import ChoreService
from apps.homework.models import HomeworkAssignment, HomeworkSkillTag
from apps.habits.models import Habit, HabitLog, HabitSkillTag
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.homework.services import HomeworkService
from apps.movement.models import MovementType, MovementTypeSkillTag
from apps.movement.services import MovementSessionService
from apps.projects.models import Project, ProjectMilestone
from apps.quests.activity import SOURCE_KEYS, record_activity
from apps.quests.goals import list_goals
from apps.quests.models import ChallengeActivity, ChallengeOccurrence, QuestDefinition
from apps.quests.services import QuestService
from apps.rewards.models import CoinLedger
from apps.rpg.services import GameLoopService
from apps.timecards.models import TimeEntry
from apps.timecards.services import ClockService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativeTaggedProducerCategoryTests(TestCase):
    def setUp(self):
        family = make_family(
            "Producer category household",
            parents=[{"username": "producer-parent"}],
            children=[{"username": "producer-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Native XP destination")
        self.decoy = SkillCategory.objects.create(name="Different native XP destination")
        self.skill = Skill.objects.create(name="Native source skill", category=self.category)
        self.decoy_skill = Skill.objects.create(name="Unrelated parent tag", category=self.decoy)
        for skill in (self.skill, self.decoy_skill):
            SkillProgress.objects.create(user=self.child, skill=skill, unlocked=True, level=1)

    def campaigns(self, trigger):
        common = dict(quest_type="collection", target_value=3, duration_days=7, coin_reward=0, xp_reward=0)
        legacy_definition = QuestDefinition.objects.create(
            name="Native category campaign",
            created_by=self.parent,
            trigger_filter={"allowed_triggers": [trigger], "skill_category_id": self.category.pk},
            **common,
        )
        legacy = QuestService.start_quest(self.child, legacy_definition.pk)
        definitions = []
        for category in (self.category, self.decoy):
            definitions.append(
                QuestDefinition.objects.create(
                    name="Automatic " + category.name,
                    is_system=True,
                    trigger_filter={"allowed_triggers": [trigger], "skill_category_id": category.pk},
                    **common,
                )
            )
        list_goals(self.child)
        return legacy, definitions

    def project(self, tag_skill=None):
        project = Project.objects.create(
            title="Native tagged project",
            assigned_to=self.child,
            created_by=self.parent,
            status="in_progress",
            xp_reward=20,
        )
        ProjectSkillTag.objects.create(project=project, skill=tag_skill or self.skill, xp_weight=2)
        return project

    def prove_native_source(self, trigger, perform, *, expected_weight=2, native_milestone_xp=None):
        legacy, definitions = self.campaigns(trigger)
        source = perform()
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type=trigger, source_id=str(source.pk))
        occurrences = [
            ChallengeOccurrence.objects.get(goal__catalog_definition=definition) for definition in definitions
        ]
        xp = dict(SkillProgress.objects.filter(user=self.child).values_list("skill_id", "xp_points"))
        legacy.refresh_from_db()
        # XP is the independent contract witness, rather than reading the
        # challenge resolver to derive the expected category.
        self.assertGreater(xp.get(self.skill.pk, 0), 0)
        if native_milestone_xp is None:
            self.assertEqual(xp.get(self.decoy_skill.pk, 0), 0)
            self.assertEqual(
                fact.context["skill_tags"],
                [{"skill_id": self.skill.pk, "category_id": self.category.pk, "xp_weight": expected_weight}],
            )
        else:
            # The signal's fixed milestone XP is independent evidence. Keep
            # the existing project-tagged daily bonus allocation unchanged.
            self.assertEqual(source._completion_reward_xp, native_milestone_xp)
            self.assertEqual(xp.get(self.skill.pk, 0), native_milestone_xp)
            self.assertEqual(xp.get(self.decoy_skill.pk, 0), 20)
            self.assertEqual(
                fact.context["skill_tags"],
                [{"skill_id": self.decoy_skill.pk, "category_id": self.decoy.pk, "xp_weight": 2}],
            )
        category_tags = fact.context.get("category_skill_tags", fact.context["skill_tags"])
        self.assertEqual(
            category_tags, [{"skill_id": self.skill.pk, "category_id": self.category.pk, "xp_weight": expected_weight}]
        )
        self.assertEqual(legacy.current_progress, 1)
        self.assertEqual([row.progress for row in occurrences], [1, 0])
        frozen = deepcopy(fact.context)
        Skill.objects.filter(pk=self.skill.pk).update(category=self.decoy)
        record_activity(self.child, trigger, {SOURCE_KEYS[trigger]: source.pk})
        fact.refresh_from_db()
        for row in occurrences:
            row.refresh_from_db()
        self.assertEqual(fact.context, frozen)
        self.assertEqual([row.progress for row in occurrences], [1, 0])
        self.assertEqual(occurrences[0].contributions.count(), 1)
        self.assertEqual(occurrences[1].contributions.count(), 0)
        self.assertEqual(dict(SkillProgress.objects.filter(user=self.child).values_list("skill_id", "xp_points")), xp)

    def test_clock_out_uses_native_project_xp_tags_and_freezes_category(self):
        def perform():
            TimeEntry.objects.create(
                user=self.child, project=self.project(), clock_in=timezone.now() - timedelta(hours=1)
            )
            return ClockService.clock_out(self.child)

        self.prove_native_source("clock_out", perform)

    def test_chore_approval_uses_native_chore_xp_tags_and_freezes_category(self):
        def perform():
            chore = Chore.objects.create(
                title="Native tagged duty", created_by=self.parent, assigned_to=self.child, xp_reward=18, coin_reward=0
            )
            ChoreSkillTag.objects.create(chore=chore, skill=self.skill, xp_weight=2)
            completion = ChoreCompletion.objects.create(
                chore=chore,
                user=self.child,
                completed_date=timezone.localdate(),
                reward_amount_snapshot=0,
                coin_reward_snapshot=0,
            )
            return ChoreService.approve_completion(completion, self.parent)

        self.prove_native_source("chore_complete", perform)

    def test_homework_approval_uses_fixed_xp_amount_and_freezes_category(self):
        def perform():
            assignment = HomeworkAssignment.objects.create(
                title="Native tagged homework",
                subject="math",
                due_date=timezone.localdate(),
                assigned_to=self.child,
                created_by=self.parent,
                effort_level=3,
            )
            HomeworkSkillTag.objects.create(assignment=assignment, skill=self.skill, xp_amount=23)
            submission = HomeworkService.submit_completion(
                self.child, assignment, [], proof_url="https://example.invalid/proof"
            )
            return HomeworkService.approve_submission(submission, self.parent)

        self.prove_native_source("homework_complete", perform, expected_weight=23)

    def test_movement_uses_native_activity_xp_tags_and_freezes_category(self):
        def perform():
            movement = MovementType.objects.create(name="Native tagged movement", slug="native-tagged-movement")
            MovementTypeSkillTag.objects.create(movement_type=movement, skill=self.skill, xp_weight=2)
            return MovementSessionService.log_session(self.child, movement_type=movement, duration_minutes=20)

        self.prove_native_source("movement_session", perform)

    def test_project_completion_uses_native_project_xp_tags_and_freezes_category(self):
        def perform():
            project = self.project()
            project.status = "completed"
            project.save()
            return project

        self.prove_native_source("project_complete", perform)

    def test_milestone_without_own_tags_uses_native_project_fallback(self):
        def perform():
            milestone = ProjectMilestone.objects.create(project=self.project(), title="Native untagged milestone")
            milestone.is_completed = True
            milestone.save()
            return milestone

        self.prove_native_source("milestone_complete", perform)

    def test_milestone_own_fixed_xp_tags_override_different_parent_project_tags(self):
        def perform():
            project = self.project(tag_skill=self.decoy_skill)
            milestone = ProjectMilestone.objects.create(project=project, title="Native tagged milestone")
            MilestoneSkillTag.objects.create(milestone=milestone, skill=self.skill, xp_amount=19)
            milestone.is_completed = True
            milestone.save()
            return milestone

        self.prove_native_source("milestone_complete", perform, expected_weight=19, native_milestone_xp=19)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HabitSavedReceiptEvidenceTests(TestCase):
    def setUp(self):
        family = make_family(
            "Habit receipt household",
            parents=[{"username": "receipt-parent", "is_staff": True}],
            children=[{"username": "receipt-child"}],
        )
        self.child = family.children[0]
        category = SkillCategory.objects.create(name="Receipt source category")
        self.skill = Skill.objects.create(name="Receipt practice", category=category)
        SkillProgress.objects.create(user=self.child, skill=self.skill, unlocked=True, level=1)
        self.habit = Habit.objects.create(
            user=self.child, created_by=family.parents[0], name="Receipt habit", xp_reward=13
        )
        HabitSkillTag.objects.create(habit=self.habit, skill=self.skill)
        self.definition = QuestDefinition.objects.create(
            name="One actual habit",
            is_system=True,
            quest_type="collection",
            target_value=1,
            duration_days=7,
            coin_reward=7,
            xp_reward=0,
            trigger_filter={"allowed_triggers": ["habit_log"], "skill_category_id": category.pk},
        )

    def state(self):
        return {
            "logs": list(HabitLog.objects.values()),
            "coins": list(CoinLedger.objects.values()),
            "xp": list(SkillProgress.objects.values()),
            "occurrences": list(ChallengeOccurrence.objects.values()),
        }

    def assert_saved_receipt(self, response):
        self.assertEqual(set(response), {"direction", "xp_reward", "new_strength", "game_event"})
        self.assertNotIn("habit_log_id", response)
        occurrence = ChallengeOccurrence.objects.get(goal__catalog_definition=self.definition)
        self.assertIsNotNone(occurrence.awarded_at)
        self.assertEqual(occurrence.contributions.count(), 1)
        fact = ChallengeActivity.objects.get(user=self.child, trigger_type="habit_log")
        receipt = deepcopy(fact.context["_receipt"])
        self.assertTrue(response["game_event"]["challenge_goals"])
        self.assertEqual(response["game_event"]["challenge_goals"], receipt["goals"])
        self.assertEqual(response["game_event"]["challenge_receipts"], [receipt])
        self.assertEqual(receipt["goals"][0]["rewards"]["coins"], 7)
        before = self.state()
        for _ in range(2):
            replay = GameLoopService.record_challenge_activity(
                self.child, "habit_log", {"habit_log_id": fact.source_id}
            )
            self.assertEqual(replay["goals"], receipt["goals"])
        self.assertEqual(self.state(), before)
        self.assertEqual(HabitLog.objects.count(), 1)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 13)

    def test_rest_positive_tap_exposes_saved_receipt_without_extra_award(self):
        client = APIClient()
        client.force_authenticate(self.child)
        response = client.post(f"/api/habits/{self.habit.pk}/log/", {"direction": 1}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_saved_receipt(response.data)

    def test_registered_mcp_positive_tap_exposes_saved_receipt_without_extra_award(self):
        with override_user(self.child):
            result = async_to_sync(mcp.call_tool)(
                "log_habit", {"params": {"habit_id": self.habit.pk, "amount": 1}, "confirmation": True}
            )
        response = result[1] if isinstance(result, tuple) else result.structuredContent
        self.assertNotIn("error", response, response)
        self.assert_saved_receipt(response)
