"""A personal workspace uses parent-owned data without changing authority."""
from rest_framework.test import APITestCase

from apps.habits.models import Habit
from apps.projects.models import Project
from config.tests.factories import make_family


class PersonalWorkspaceTests(APITestCase):
    def setUp(self):
        family = make_family(
            "Personal spaces",
            parents=[{"username": "parent"}, {"username": "coparent"}],
            children=[{"username": "child"}],
        )
        self.parent, self.coparent = family.parents
        self.child = family.children[0]
        self.foreign = make_family("Other", parents=[{"username": "outsider"}]).parents[0]
        self.client.force_authenticate(self.parent)

    def personal(self, method, path, data=None):
        return getattr(self.client, method)(
            path, data, format="json", HTTP_X_ABBY_SPACE="personal",
        )

    def test_parent_personal_dashboard_has_own_tasks_without_family_counts(self):
        Habit.objects.create(user=self.parent, created_by=self.parent, name="My habit")
        Habit.objects.create(user=self.child, created_by=self.parent, name="Child habit")
        response = self.personal("get", "/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["role"], "parent")
        self.assertIn("since_last_visit", response.data)
        self.assertNotIn("children_count", response.data)
        self.assertEqual([row["title"] for row in response.data["next_actions"]], ["My habit"])
        family = self.client.get("/api/dashboard/")
        self.assertEqual(family.data["children_count"], 1)
        self.assertEqual(family.data["next_actions"], [])

    def test_personal_projects_exclude_children_coparents_and_other_families(self):
        own = Project.objects.create(title="My project", assigned_to=self.parent, created_by=self.parent)
        for owner in (self.child, self.coparent, self.foreign):
            project = Project.objects.create(title="Another project", assigned_to=owner, created_by=owner)
            response = self.personal("get", f"/api/projects/{project.pk}/")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.personal("get", f"/api/projects/{project.pk}/steps/").status_code, 404)
        response = self.personal("get", "/api/projects/")
        self.assertEqual([row["id"] for row in response.data["results"]], [own.pk])

    def test_personal_project_create_assigns_self_and_has_no_money_rewards(self):
        response = self.personal("post", "/api/projects/", {"title": "My project"})
        self.assertEqual(response.status_code, 201, response.data)
        project = Project.objects.get(pk=response.data["id"])
        self.assertEqual(project.assigned_to, self.parent)
        self.assertEqual(project.bonus_amount, 0)
        self.assertEqual(project.hourly_rate_override, 0)
        invalid = self.personal("post", "/api/projects/", {
            "title": "Wrong owner", "assigned_to_id": self.child.pk,
        })
        self.assertEqual(invalid.status_code, 400)

    def test_personal_hint_never_gives_child_parent_permissions(self):
        self.client.force_authenticate(self.child)
        response = self.personal("post", "/api/projects/", {"title": "Unauthorized"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.personal("get", "/api/children/").status_code, 403)

    def test_personal_project_edits_keep_cash_rewards_zero_through_completion(self):
        from apps.payments.models import PaymentLedger

        created = self.personal("post", "/api/projects/", {"title": "My personal project"})
        self.assertEqual(created.status_code, 201)
        project = Project.objects.get(pk=created.data["id"])
        edited = self.personal("patch", f"/api/projects/{project.pk}/", {
            "bonus_amount": "20.00", "hourly_rate_override": "15.00",
        })
        self.assertEqual(edited.status_code, 200, edited.data)
        project.refresh_from_db()
        self.assertEqual(project.bonus_amount, 0)
        self.assertEqual(project.hourly_rate_override, 0)
        project.status = "in_progress"
        project.save()
        completed = self.personal("post", f"/api/projects/{project.pk}/approve/", {})
        self.assertEqual(completed.status_code, 200, completed.data)
        self.assertFalse(PaymentLedger.objects.filter(user=self.parent).exists())

    def test_parent_personal_coin_selector_cannot_target_a_child(self):
        response = self.personal("get", f"/api/coins/?user_id={self.child.pk}")
        self.assertEqual(response.status_code, 400)
