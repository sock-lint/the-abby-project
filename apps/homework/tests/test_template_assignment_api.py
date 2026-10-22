"""Template assignment routes validate dates before saving or notifying."""
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory
from apps.homework.models import HomeworkAssignment, HomeworkSkillTag, HomeworkTemplate
from apps.notifications.models import Notification, NotificationType
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TemplateAssignmentApiTests(TestCase):
    def setUp(self):
        family = make_family(parents=[{"username": "template-api-parent"}, {"username": "template-api-coparent"}],
                             children=[{"username": "template-api-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.coparent = family.parents[1]
        category = SkillCategory.objects.create(name="Template API category")
        self.skill = Skill.objects.create(name="Template API skill", category=category)
        self.tags = [{"skill_id": str(self.skill.pk), "xp_amount": 23}]
        self.template = HomeworkTemplate.objects.create(title="Saved practice", subject="math", created_by=self.parent,
                                                        skill_tags=self.tags)
        self.client = APIClient(raise_request_exception=False)
        self.client.force_authenticate(self.parent)
        self.payload = {"assigned_to_id": self.child.pk, "due_date": "2030-01-04"}

    def path(self, action="create-assignment", *, template_id=None):
        return f"/api/homework-templates/{template_id or self.template.pk}/{action}/"

    def counts(self):
        return (HomeworkAssignment.objects.count(), HomeworkSkillTag.objects.count(),
                Notification.objects.filter(notification_type=NotificationType.HOMEWORK_CREATED).count())

    def assert_success(self, action):
        response = self.client.post(self.path(action), self.payload, format="json")
        # A serialization error used to return 500 after these three rows committed.
        self.assertEqual((response.status_code, *self.counts()), (201, 1, 1, 1))
        assignment = HomeworkAssignment.objects.get()
        self.assertEqual(assignment.due_date, date(2030, 1, 4))
        self.assertEqual((assignment.assigned_to_id, assignment.created_by_id), (self.child.pk, self.parent.pk))
        self.assertEqual(response.data["id"], assignment.pk)
        self.assertEqual(response.data["due_date"], "2030-01-04")
        self.assertEqual(list(assignment.skill_tags.values_list("skill_id", "xp_amount")), [(self.skill.pk, 23)])
        notification = Notification.objects.get(notification_type=NotificationType.HOMEWORK_CREATED)
        self.assertEqual(notification.user_id, self.child.pk)
        self.template.refresh_from_db()
        self.assertEqual(self.template.skill_tags, self.tags)

    def test_valid_iso_date_returns_created_once_through_existing_underscore_route(self):
        self.assert_success("create_assignment")

    def test_frontend_hyphenated_route_returns_created_once(self):
        self.assertEqual(reverse("homework-template-create-assignment", args=[self.template.pk]), self.path())
        self.assert_success("create-assignment")

    def test_malformed_dates_do_not_save_or_notify_through_either_route(self):
        invalid = ("not-a-date", "2030-02-30", "2030-01-04T12:00:00Z", 123, True, ["2030-01-04"], {"date": "2030-01-04"})
        for action in ("create_assignment", "create-assignment"):
            for value in invalid:
                with self.subTest(action=action, value=value):
                    response = self.client.post(self.path(action), {**self.payload, "due_date": value}, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(self.counts(), (0, 0, 0))

    def test_required_input_errors_do_not_save_or_notify(self):
        for values in ({}, {"assigned_to_id": self.child.pk}, {"due_date": "2030-01-04"},
                       {**self.payload, "due_date": None}, {**self.payload, "due_date": ""}):
            with self.subTest(values=values):
                response = self.client.post(self.path(), values, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.counts(), (0, 0, 0))

    def test_missing_and_foreign_children_remain_not_found(self):
        foreign = make_family(children=[{"username": "foreign-template-child"}]).children[0]
        for action in ("create_assignment", "create-assignment"):
            for child_id in (999999, foreign.pk, self.parent.pk):
                with self.subTest(action=action, child_id=child_id):
                    response = self.client.post(self.path(action), {**self.payload, "assigned_to_id": child_id}, format="json")
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(self.counts(), (0, 0, 0))

    def test_missing_and_other_authors_templates_remain_not_found(self):
        foreign = make_family(parents=[{"username": "foreign-template-parent"}]).parents[0]
        template = HomeworkTemplate.objects.create(title="Private template", created_by=foreign)
        same_family = HomeworkTemplate.objects.create(title="Other parent's template", created_by=self.coparent)
        for action in ("create_assignment", "create-assignment"):
            for template_id in (999999, template.pk, same_family.pk):
                with self.subTest(action=action, template_id=template_id):
                    response = self.client.post(self.path(action, template_id=template_id), self.payload, format="json")
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(self.counts(), (0, 0, 0))

    def test_children_cannot_assign_templates(self):
        self.client.force_authenticate(self.child)
        for action in ("create_assignment", "create-assignment"):
            with self.subTest(action=action):
                response = self.client.post(self.path(action), self.payload, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.counts(), (0, 0, 0))

    def test_retired_and_duplicate_saved_tags_still_reject_before_writes(self):
        for tags in ([*self.tags, *self.tags], self.tags):
            if tags == self.tags:
                Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
            self.template.skill_tags = tags
            self.template.save(update_fields=["skill_tags"])
            for action in ("create_assignment", "create-assignment"):
                with self.subTest(action=action, tags=tags):
                    response = self.client.post(self.path(action), self.payload, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(self.counts(), (0, 0, 0))
