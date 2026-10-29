"""Personal project authoring keeps ownership and cash rewards server-owned."""
from decimal import Decimal
from unittest.mock import patch

from apps.achievements.models import (
    MilestoneSkillTag, ProjectSkillTag, Skill, SkillCategory, SkillProgress,
)
from apps.ingestion.models import ProjectIngestionJob
from apps.payments.models import PaymentLedger
from apps.projects.models import MilestoneCompletionRewardReceipt, Project, ProjectMilestone
from apps.rewards.models import CoinLedger
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class ParentPersonalProjectAuthoringTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "personal-maker"}, {"username": "personal-coparent"}]
    family_children = [{"username": "family-maker"}]

    def setUp(self):
        self.parent, self.coparent = self.parents
        self.child = self.children[0]
        self.foreign = make_family("Other makers", parents=[{"username": "foreign-maker"}]).parents[0]
        self.client.force_authenticate(self.parent)
        category = SkillCategory.objects.create(name="Personal making")
        self.skill = Skill.objects.create(name="Making practice", category=category)
        loop_patch = patch("apps.rpg.services.GameLoopService.on_task_completed")
        self.game_loop = loop_patch.start()
        self.addCleanup(loop_patch.stop)

    def personal(self, method, url, data=None):
        return getattr(self.client, method)(url, data, format="json", HTTP_X_ABBY_SPACE="personal")

    def import_job(self, owner=None):
        return ProjectIngestionJob.objects.create(
            created_by=owner or self.parent, source_type="url", status="ready",
            result_json={"title": "Imported project", "steps": [{"title": "Build"}]},
        )

    def own_project(self):
        return Project.objects.create(
            title="Personal project", created_by=self.parent, assigned_to=self.parent,
            bonus_amount="40.00", hourly_rate_override="12.00",
        )

    def milestone(self, project=None, bonus="18.00"):
        milestone = ProjectMilestone.objects.create(
            project=project or self.own_project(), title="Make a phase", bonus_amount=bonus,
        )
        MilestoneSkillTag.objects.create(milestone=milestone, skill=self.skill, xp_amount=23)
        return milestone

    @staticmethod
    def milestone_url(milestone):
        return f"/api/projects/{milestone.project_id}/milestones/{milestone.pk}/"

    def test_personal_import_assigns_self_is_accessible_and_reuses_saved_project(self):
        job = self.import_job()
        url = f"/api/projects/ingest/{job.pk}/commit/"
        created = self.personal("post", url, {"bonus_amount": "999.00", "hourly_rate_override": "99.00"})
        self.assertEqual(created.status_code, 201, created.content)
        project = Project.objects.get(pk=created.data["id"])
        self.assertEqual(project.assigned_to_id, self.parent.pk)
        self.assertEqual((project.bonus_amount, project.hourly_rate_override), (0, 0))
        self.assertEqual(self.personal("get", f"/api/projects/{project.pk}/").status_code, 200)
        steps = self.personal("get", f"/api/projects/{project.pk}/steps/")
        self.assertEqual(steps.status_code, 200, steps.content)
        self.assertEqual(steps.data["results"][0]["title"], "Build")
        replay = self.personal("post", url, {"bonus_amount": "500.00"})
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.data["id"], project.pk)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(project.steps.count(), 1)
        ProjectSkillTag.objects.create(project=project, skill=self.skill)
        for _ in range(2):
            approved = self.personal("post", f"/api/projects/{project.pk}/approve/", {})
            self.assertEqual(approved.status_code, 200, approved.content)
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 100)
        self.assertEqual(list(CoinLedger.objects.values_list("user_id", "amount")), [(self.parent.pk, 20)])

    def test_explicit_self_import_cannot_keep_a_client_cash_bonus(self):
        job = self.import_job()
        response = self.personal("post", f"/api/projects/ingest/{job.pk}/commit/", {
            "assigned_to_id": self.parent.pk, "bonus_amount": "120.00",
        })
        self.assertEqual(response.status_code, 201, response.content)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual((project.bonus_amount, project.hourly_rate_override), (0, 0))

    def test_personal_project_approval_clears_existing_pay_and_awards_progress_once(self):
        project = self.own_project()
        ProjectSkillTag.objects.create(project=project, skill=self.skill)
        for _ in range(2):
            completed = self.personal("post", f"/api/projects/{project.pk}/approve/", {})
            self.assertEqual(completed.status_code, 200, completed.content)
        project.refresh_from_db()
        self.assertEqual(project.status, "completed")
        self.assertEqual((project.bonus_amount, project.hourly_rate_override), (0, 0))
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 50)
        self.assertEqual(list(CoinLedger.objects.values_list("user_id", "amount")), [(self.parent.pk, 10)])

    def test_family_project_pay_and_historical_personal_approval_receipt_are_preserved(self):
        project = self.own_project()
        ProjectSkillTag.objects.create(project=project, skill=self.skill)
        url = f"/api/projects/{project.pk}/approve/"
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 200)
        Project.objects.filter(pk=project.pk).update(status="in_review")
        self.assertEqual(self.personal("post", url, {}).status_code, 200)
        project.refresh_from_db()
        self.assertEqual((project.bonus_amount, project.hourly_rate_override), (0, 0))
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 50)
        child_project = Project.objects.create(
            title="Family paid project", created_by=self.parent, assigned_to=self.child, bonus_amount="7.00",
        )
        self.assertEqual(self.client.post(f"/api/projects/{child_project.pk}/approve/", {}, format="json").status_code, 200)
        self.assertEqual(list(PaymentLedger.objects.order_by("pk").values_list("user_id", "amount")), [
            (self.parent.pk, Decimal("40.00")), (self.child.pk, Decimal("7.00")),
        ])

    def test_personal_import_rejects_other_assignees_and_other_job_owners(self):
        for target in (self.child, self.coparent, self.foreign):
            with self.subTest(target=target.pk):
                job = self.import_job()
                response = self.personal("post", f"/api/projects/ingest/{job.pk}/commit/", {
                    "assigned_to_id": target.pk,
                })
                self.assertEqual(response.status_code, 400, response.content)
                job.refresh_from_db()
                self.assertEqual(job.status, "ready")
                self.assertIsNone(job.project_id)
        for owner in (self.coparent, self.foreign):
            job = self.import_job(owner)
            response = self.personal("post", f"/api/projects/ingest/{job.pk}/commit/", {})
            self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(Project.objects.exists())

    def test_family_import_keeps_assignment_bonus_and_personal_retry_cannot_return_it(self):
        job = self.import_job()
        url = f"/api/projects/ingest/{job.pk}/commit/"
        created = self.client.post(url, {"assigned_to_id": self.child.pk, "bonus_amount": "7.00"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        project = Project.objects.get(pk=created.data["id"])
        self.assertEqual((project.assigned_to_id, project.bonus_amount), (self.child.pk, Decimal("7.00")))
        self.assertEqual(self.personal("post", url, {}).status_code, 404)
        retry = self.client.post(url, {}, format="json")
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(retry.data["id"], project.pk)
        project.refresh_from_db()
        self.assertEqual((project.assigned_to_id, project.bonus_amount), (self.child.pk, Decimal("7.00")))
        self.assertEqual(Project.objects.count(), 1)

    def test_personal_milestone_create_and_update_force_zero_cash(self):
        project = self.own_project()
        url = f"/api/projects/{project.pk}/milestones/"
        created = self.personal("post", url, {"title": "My phase", "bonus_amount": "600.00"})
        self.assertEqual(created.status_code, 201, created.content)
        milestone = ProjectMilestone.objects.get(pk=created.data["id"])
        self.assertEqual(milestone.bonus_amount, 0)
        edited = self.personal("patch", self.milestone_url(milestone), {"bonus_amount": "700.00"})
        self.assertEqual(edited.status_code, 200, edited.content)
        milestone.refresh_from_db()
        self.assertEqual(milestone.bonus_amount, 0)
        self.assertFalse(PaymentLedger.objects.exists())

    def test_personal_completion_of_existing_cash_milestone_keeps_xp_once_without_cash(self):
        for action in ("complete", "patch"):
            with self.subTest(action=action):
                milestone = self.milestone()
                url = self.milestone_url(milestone)
                if action == "complete":
                    completed = self.personal("post", url + "complete/", {})
                else:
                    completed = self.personal("patch", url, {"bonus_amount": "900.00", "is_completed": True})
                self.assertEqual(completed.status_code, 200, completed.content)
                milestone.refresh_from_db()
                self.assertTrue(milestone.is_completed)
                self.assertIsNotNone(milestone.completed_at)
                self.assertEqual(milestone.bonus_amount, 0)
                self.assertEqual(MilestoneCompletionRewardReceipt.objects.get(milestone=milestone).user_id, self.parent.pk)
                reopened = self.personal("patch", url, {"is_completed": False, "bonus_amount": "99.00"})
                self.assertEqual(reopened.status_code, 200, reopened.content)
                retried = self.personal("post", url + "complete/", {})
                self.assertEqual(retried.status_code, 200, retried.content)
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 46)
        self.assertFalse(SkillProgress.objects.exclude(user=self.parent).exists())
        self.assertFalse(PaymentLedger.objects.exists())
        self.assertEqual(self.game_loop.call_count, 2)

    def test_personal_create_already_completed_milestone_cannot_pay_cash(self):
        project = self.own_project()
        created = self.personal("post", f"/api/projects/{project.pk}/milestones/", {
            "title": "Complete immediately", "is_completed": True, "bonus_amount": "800.00",
        })
        self.assertEqual(created.status_code, 201, created.content)
        self.assertTrue(ProjectMilestone.objects.get(pk=created.data["id"]).is_completed)
        self.assertFalse(PaymentLedger.objects.exists())

    def test_family_milestone_bonus_and_historical_payments_remain_unchanged(self):
        project = Project.objects.create(title="Child project", assigned_to=self.child, created_by=self.parent)
        created = self.client.post(f"/api/projects/{project.pk}/milestones/", {
            "title": "Family phase", "bonus_amount": "5.00",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        milestone = ProjectMilestone.objects.get(pk=created.data["id"])
        url = self.milestone_url(milestone)
        edited = self.client.patch(url, {"bonus_amount": "7.00"}, format="json")
        self.assertEqual(edited.status_code, 200, edited.content)
        for _ in range(2):
            self.assertEqual(self.client.post(url + "complete/", {}, format="json").status_code, 200)
        historical = self.milestone()
        own_url = self.milestone_url(historical)
        self.assertEqual(self.client.post(own_url + "complete/", {}, format="json").status_code, 200)
        self.assertEqual(self.personal("patch", own_url, {"is_completed": False}).status_code, 200)
        self.assertEqual(self.personal("post", own_url + "complete/", {}).status_code, 200)
        self.assertEqual(list(PaymentLedger.objects.order_by("pk").values_list("user_id", "amount")), [
            (self.child.pk, Decimal("7.00")), (self.parent.pk, Decimal("18.00")),
        ])
        self.assertEqual(SkillProgress.objects.get(user=self.parent, skill=self.skill).xp_points, 23)

    def test_personal_milestones_cannot_modify_other_work_and_child_keeps_write_denial(self):
        for owner in (self.child, self.coparent, self.foreign):
            project = Project.objects.create(title="Other project", assigned_to=owner, created_by=owner)
            milestone = self.milestone(project)
            url = self.milestone_url(milestone)
            self.assertEqual(self.personal("post", f"/api/projects/{project.pk}/milestones/", {"title": "Intrusion"}).status_code, 404)
            self.assertEqual(self.personal("patch", url, {"is_completed": True}).status_code, 404)
            self.assertEqual(self.personal("post", url + "complete/", {}).status_code, 404)
            milestone.refresh_from_db()
            self.assertFalse(milestone.is_completed)
            self.assertEqual(milestone.bonus_amount, Decimal("18.00"))
        self.client.force_authenticate(self.child)
        self.assertEqual(self.personal("post", url + "complete/", {}).status_code, 403)
        self.assertFalse(PaymentLedger.objects.exists())
