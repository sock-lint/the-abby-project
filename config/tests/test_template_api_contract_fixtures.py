"""Synthetic authenticated template responses retain reusable skill wiring."""
from unittest.mock import patch

from django.core.management.color import no_style
from django.db import connection
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.achievements.models import MilestoneSkillTag, ProjectSkillTag, Skill, SkillCategory
from apps.projects.models import Project, ProjectMilestone, ProjectTemplate, TemplateMilestone
from config.tests import test_api_contract_fixtures as shared
from config.tests.factories import make_family


@override_settings(ALLOWED_HOSTS=["testserver"], VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
class TemplateApiResponseFixtureTests(APITestCase):
    assert_response_fixture = shared.SharedApiResponseFixtureTests.assert_response_fixture

    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=shared.FIXED_NOW)
        clock.start()
        self.addCleanup(clock.stop)
        family = make_family(
            "Template Fixture Family", family_id=41,
            parents=[{"id": 6, "username": "template-fixture-parent"}],
            children=[{"id": 7, "username": "template-fixture-child"}],
        )
        self.parent, self.child = family.parents[0], family.children[0]
        category = SkillCategory.objects.create(id=21, name="Making")
        self.skill = Skill.objects.create(id=22, name="Measuring", category=category)
        self.project = Project.objects.create(id=401, title="Measure a birdhouse", category=category, created_by=self.parent, assigned_to=self.child)
        milestone = ProjectMilestone.objects.create(id=501, project=self.project, title="Measure the boards")
        ProjectSkillTag.objects.create(project=self.project, skill=self.skill, xp_weight=3)
        MilestoneSkillTag.objects.create(milestone=milestone, skill=self.skill, xp_amount=27)
        # Sequences remain deterministic when this joins the PostgreSQL suite.
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [ProjectTemplate, TemplateMilestone]):
                cursor.execute(sql)
        self.client.force_authenticate(self.parent)

    def test_real_template_save_get_and_instantiate_preserve_skill_wiring(self):
        template = self.assert_response_fixture(self.client.post(
            "/api/templates/from-project/", {"project_id": self.project.pk}, format="json",
        ), "template-skills.json", status=201)
        self.assertEqual(template["skill_tags"], [{"skill_id": 22, "xp_weight": 3}])
        self.assertEqual(template["milestones"][0]["skill_tags"], [{"skill_id": 22, "xp_amount": 27}])
        self.assert_response_fixture(self.client.get(f"/api/templates/{template['id']}/"), "template-skills.json")
        created = self.client.post(f"/api/templates/{template['id']}/create-project/", {"assigned_to_id": self.child.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        clone = Project.objects.get(pk=created.json()["id"])
        self.assertEqual(list(clone.skill_tags.values_list("skill_id", "xp_weight")), [(22, 3)])
        self.assertEqual(list(clone.milestones.get().skill_tags.values_list("skill_id", "xp_amount")), [(22, 27)])
