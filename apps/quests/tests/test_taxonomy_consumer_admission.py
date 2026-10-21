"""Retirement gates new choices, while saved references keep their identity."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, Subject, ProjectSkillTag
from apps.chores.models import Chore, ChoreSkillTag
from apps.habits.models import Habit, HabitSkillTag
from apps.homework.models import HomeworkAssignment, HomeworkTemplate
from apps.homework.services import HomeworkService, HomeworkError
from apps.creations.models import Creation
from apps.creations.services import CreationService, CreationError
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.movement.services import MovementTypeService, MovementTypeError
from apps.projects.models import Project, ProjectTemplate, TemplateSkillTag
from apps.projects.template_services import instantiate_project_template, save_project_template
from apps.quests.controls import update_schedule
from apps.quests.goals import create_goal
from apps.quests.goals import _occurrence
from apps.quests.controls import retry_challenge
from apps.quests.milestone_eligibility import milestone_eligibility
from apps.quests.models import ChallengeGoal, ChallengeOccurrence, QuestDefinition
from apps.quests.reference_locks import lock_filter_category
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyConsumerAdmissionTests(TestCase):
    def setUp(self):
        family = make_family("Consumer retirement", parents=[{"username": "consumer-parent", "is_staff": True}],
                             children=[{"username": "consumer-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Consumer category")
        self.subject = Subject.objects.create(name="Consumer subject", category=self.category)
        self.skill = Skill.objects.create(name="Consumer skill", category=self.category, subject=self.subject)
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def goal_data(self, **changes):
        return {"name": "Saved goal", "description": "", "metric": "count", "target": Decimal(2),
                "unit": "actions", "trigger_type": "chore_complete", "period": "from_today", "repeat_weekly": True,
                "coin_reward": 0, "xp_reward": 15, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}], **changes}

    def retire(self, model):
        model.objects.filter(pk={Skill: self.skill.pk, Subject: self.subject.pk, SkillCategory: self.category.pk}[model]).update(is_retired=True)

    def wire(self, name, payload):
        with override_user(self.parent):
            return async_to_sync(mcp.call_tool)(name, {"params": payload, "confirmation": True})

    def test_new_goal_rejects_each_effectively_retired_reference(self):
        for model in (Skill, Subject, SkillCategory):
            with self.subTest(model=model.__name__):
                self.retire(model)
                with self.assertRaisesRegex(ValueError, "[Rr]etired"):
                    create_goal(self.parent, self.child, self.goal_data())
                model.objects.all().update(is_retired=False)
        self.assertFalse(ChallengeGoal.objects.exists())

    def test_goal_uuid_replay_and_retained_schedule_remain_valid(self):
        data = self.goal_data(request_id=uuid4())
        original = create_goal(self.parent, self.child, data)
        self.retire(SkillCategory)
        replay = create_goal(self.parent, self.child, data)
        self.assertEqual(replay.pk, original.pk)
        update_schedule(self.parent, original.goal_id, {"expected_revision": 0, "next_week": {"name": "Kept promise"}})
        self.assertEqual(ChallengeGoal.objects.count(), 1)

    def test_schedule_rejects_new_retired_reward_without_changing_revision(self):
        original = create_goal(self.parent, self.child, self.goal_data(xp_reward=0, skill_tags=[]))
        self.retire(Subject)
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            update_schedule(self.parent, original.goal_id, {"expected_revision": 0, "next_week": {
                "xp_reward": 15, "skill_tags": self.goal_data()["skill_tags"]}})
        original.goal.refresh_from_db()
        self.assertEqual(original.goal.schedule_revision, 0)

    def test_private_category_filter_rejects_retirement(self):
        self.retire(SkillCategory)
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            lock_filter_category({"skill_category_id": self.category.pk})

    def test_rest_chore_and_habit_new_tags_reject_retired_ancestor(self):
        self.retire(Subject)
        for url, payload in (("/api/chores/", {"title": "Unavailable chore", "xp_reward": 10}),
                             ("/api/habits/", {"name": "Unavailable habit", "user": self.child.pk, "xp_reward": 10})):
            with self.subTest(url=url):
                response = self.client.post(url, {**payload, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 1}]}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Chore.objects.filter(title="Unavailable chore").exists())
        self.assertFalse(Habit.objects.filter(name="Unavailable habit").exists())

    def test_rest_project_category_new_rejected_but_retained_edit_allowed(self):
        project = Project.objects.create(title="Saved project", assigned_to=self.child, created_by=self.parent, category=self.category)
        self.retire(SkillCategory)
        response = self.client.post("/api/projects/", {"title": "New project", "assigned_to_id": self.child.pk, "category_id": self.category.pk}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(f"/api/projects/{project.pk}/", {"title": "Still saved", "category_id": self.category.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_registered_mcp_setters_reject_new_retired_tags_without_losing_existing(self):
        chore = Chore.objects.create(title="Scoped chore", family=self.parent.family, created_by=self.parent)
        habit = Habit.objects.create(name="Scoped habit", user=self.child, created_by=self.parent)
        assignment = HomeworkAssignment.objects.create(title="Scoped homework", assigned_to=self.child, created_by=self.parent,
                                                       due_date=timezone.localdate() + timedelta(days=2))
        project = Project.objects.create(title="Scoped project", assigned_to=self.child, created_by=self.parent)
        self.retire(Skill)
        for tool, selector in (("set_chore_skill_tags", {"chore_id": chore.pk}),
                               ("set_habit_skill_tags", {"habit_id": habit.pk}),
                               ("set_homework_skill_tags", {"assignment_id": assignment.pk}),
                               ("set_project_skill_tags", {"project_id": project.pk})):
            with self.subTest(tool=tool):
                tag = {"skill_id": self.skill.pk, ("xp_amount" if "homework" in tool else "xp_weight"): 15 if "homework" in tool else 1}
                result = self.wire(tool, {**selector, "skill_tags": [tag]})
                self.assertTrue(getattr(result, "isError", False), result)
                self.assertEqual(result.structuredContent["error"]["code"], "invalid_request")
        self.assertFalse(ProjectSkillTag.objects.filter(project=project).exists())

    def test_mcp_retained_chore_tags_can_be_reweighted(self):
        chore = Chore.objects.create(title="Saved chore", family=self.parent.family, created_by=self.parent)
        ChoreSkillTag.objects.create(chore=chore, skill=self.skill, xp_weight=1)
        self.retire(SkillCategory)
        result = self.wire("set_chore_skill_tags", {"chore_id": chore.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_weight": 2}]})
        self.assertFalse(getattr(result, "isError", False), result)
        self.assertEqual(chore.skill_tags.get().xp_weight, 2)

    def test_homework_creation_and_template_clone_reject_retired_skill(self):
        self.retire(Skill)
        with self.assertRaisesRegex(HomeworkError, "[Rr]etired"):
            HomeworkService.create_assignment(self.parent, {"title": "New homework", "assigned_to": self.child,
                "due_date": timezone.localdate() + timedelta(days=2), "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 15}]})
        template = HomeworkTemplate.objects.create(title="Old template", created_by=self.parent,
                                                  skill_tags=[{"skill_id": self.skill.pk, "xp_amount": 15}])
        with self.assertRaisesRegex(HomeworkError, "[Rr]etired"):
            HomeworkService.create_from_template(template, self.child, timezone.localdate() + timedelta(days=2))

    def test_project_template_cloning_does_not_create_retired_references(self):
        template = ProjectTemplate.objects.create(title="Saved template", created_by=self.parent, family=self.parent.family)
        TemplateSkillTag.objects.create(template=template, skill=self.skill, xp_weight=1)
        self.retire(Subject)
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            instantiate_project_template(template, parent=self.parent, assignee=self.child)
        self.assertFalse(Project.objects.exists())

    def test_movement_new_type_cannot_choose_retired_physical_skill(self):
        self.category.name = "Physical"
        self.category.save(update_fields=["name"])
        self.retire(SkillCategory)
        with self.assertRaisesRegex(MovementTypeError, "[Rr]etired"):
            MovementTypeService.create_type(self.child, name="New retired movement", primary_skill_id=self.skill.pk)

    def test_retirement_preserves_existing_occurrence_and_stops_new_weekly_promise(self):
        original = create_goal(self.parent, self.child, self.goal_data(period="this_week"))
        self.retire(SkillCategory)
        self.assertEqual(_occurrence(original.goal, original.starts_at).pk, original.pk)
        self.assertIsNone(_occurrence(original.goal, original.starts_at + timedelta(days=8)))
        self.assertEqual(original.goal.occurrences.count(), 1)

    def test_new_retry_rejects_retirement_but_existing_retry_is_idempotent(self):
        definition = QuestDefinition.objects.create(name="Retryable choice", quest_type="collection", target_value=2,
                                                    is_system=True, trigger_filter={"allowed_triggers": ["chore_complete"]})
        now = timezone.now()
        goal = ChallengeGoal.objects.create(user=self.child, family=self.child.family, catalog_definition=definition,
            is_catalog=True, name=definition.name, metric="count", target=2, unit="actions", timezone_name="America/Phoenix",
            starts_at=now-timedelta(days=8), ends_at=now-timedelta(days=1), skill_tags=self.goal_data()["skill_tags"])
        original = _occurrence(goal, goal.starts_at)
        self.retire(Subject)
        with self.assertRaisesRegex(ValueError, "[Rr]etired"):
            retry_challenge(self.child, original.pk)
        self.retire(Subject)  # Keep exact saved identity for the replay control below.
        Subject.objects.filter(pk=self.subject.pk).update(is_retired=False)
        retry, created = retry_challenge(self.child, original.pk)
        self.assertTrue(created)
        self.retire(Subject)
        replay, created = retry_challenge(self.child, original.pk)
        self.assertFalse(created)
        self.assertEqual(replay.pk, retry.pk)

    def test_retired_required_skill_is_unavailable_even_with_saved_level(self):
        from apps.achievements.models import SkillProgress
        SkillProgress.objects.create(user=self.child, skill=self.skill, level=3, unlocked=True)
        definition = QuestDefinition.objects.create(name="Retired gate", quest_type="collection", target_value=2,
            is_system=True, trigger_filter={"allowed_triggers": ["reading_logged"]}, required_skill=self.skill, required_skill_level=2)
        self.assertTrue(milestone_eligibility(self.child, definition)["unlocked"])
        self.retire(Subject)
        self.assertFalse(milestone_eligibility(self.child, definition)["unlocked"])

    def test_creations_cannot_add_retired_skill_but_saved_bonus_fallback_can_pay(self):
        from unittest.mock import patch
        self.category.name = "Art & Crafts"
        self.category.save(update_fields=["name"])
        creation = Creation.objects.create(user=self.child, image="synthetic.jpg", primary_skill=self.skill,
                                          occurred_on=timezone.localdate(), status=Creation.Status.PENDING)
        self.retire(Skill)
        with self.assertRaisesRegex(CreationError, "[Rr]etired"):
            CreationService.log_creation(self.child, image="synthetic-new.jpg", primary_skill_id=self.skill.pk)
        with patch("apps.achievements.services.AwardService.grant") as grant:
            CreationService.approve_bonus(creation, self.parent)
        self.assertEqual(grant.call_count, 1)
        self.assertEqual(grant.call_args.kwargs["xp_tags"][0].skill.pk, self.skill.pk)

    def test_homework_template_json_cannot_add_retired_reference(self):
        self.retire(Subject)
        response = self.client.post("/api/homework-templates/", {"title": "New saved choice",
            "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 15}]}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
