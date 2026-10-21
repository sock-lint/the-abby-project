"""Clone compatible saved template IDs without weakening new choice admission."""
from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.homework.models import HomeworkAssignment, HomeworkSkillTag, HomeworkTemplate
from apps.homework.services import HomeworkError, HomeworkService
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LegacyTemplateSkillIdTests(TestCase):
    def setUp(self):
        family = make_family(parents=[{"username": "legacy-template-parent"}],
                             children=[{"username": "legacy-template-child"}])
        self.parent, self.child = family.parents[0], family.children[0]
        self.category = SkillCategory.objects.create(name="Template category")
        self.skill = Skill.objects.create(name="Saved template skill", category=self.category)
        self.template = HomeworkTemplate.objects.create(title="Saved template", subject="other", created_by=self.parent,
            skill_tags=[{"skill_id": str(self.skill.pk), "xp_amount": 23}])
        self.due = date(2030, 1, 1)

    def test_saved_canonical_string_id_clones_same_identity_and_xp_without_rewriting_template(self):
        assignment = HomeworkService.create_from_template(self.template, self.child, self.due)
        self.assertEqual(list(assignment.skill_tags.values_list("skill_id", "xp_amount")), [(self.skill.pk, 23)])
        self.template.refresh_from_db()
        self.assertEqual(self.template.skill_tags, [{"skill_id": str(self.skill.pk), "xp_amount": 23}])

    def test_mixed_saved_integer_and_string_ids_preserve_exact_xp_and_defaults(self):
        other = Skill.objects.create(name="Second template skill", category=self.category)
        self.template.skill_tags += [{"skill_id": other.pk}]
        self.template.save(update_fields=["skill_tags"])
        assignment = HomeworkService.create_from_template(self.template, self.child, self.due)
        self.assertEqual(list(assignment.skill_tags.order_by("pk").values_list("skill_id", "xp_amount")),
                         [(self.skill.pk, 23), (other.pk, 15)])

    def assert_no_assignment(self):
        self.assertFalse(HomeworkAssignment.objects.exists())
        self.assertFalse(HomeworkSkillTag.objects.exists())

    def test_retired_string_target_is_rejected_before_any_assignment_or_notification(self):
        other = Skill.objects.create(name="Retired template skill", category=self.category, is_retired=True)
        self.template.skill_tags += [{"skill_id": str(other.pk)}]
        with patch("apps.homework.services.notify") as notify, self.assertRaisesMessage(HomeworkError, "Retired taxonomy"):
            HomeworkService.create_from_template(self.template, self.child, self.due)
        notify.assert_not_called()
        self.assert_no_assignment()

    def test_retired_ancestry_still_rejects_normalized_saved_reference(self):
        subject = Subject.objects.create(name="Archived grouping", category=self.category, is_retired=True)
        self.skill.subject = subject
        self.skill.save(update_fields=["subject"])
        with self.assertRaisesMessage(HomeworkError, "Retired taxonomy"):
            HomeworkService.create_from_template(self.template, self.child, self.due)
        self.assert_no_assignment()

    def test_malformed_or_noncanonical_saved_ids_fail_closed_without_partial_assignment(self):
        for value in (True, False, 1.0, None, {}, [], "01", "+1", " 1", "1 ", "1.0", "0", "-1",
                      "١", "", "9" * 10000, "9223372036854775808", 9223372036854775808):
            with self.subTest(value_type=type(value).__name__, sample=str(value)[:24]):
                self.template.skill_tags = [{"skill_id": self.skill.pk}, {"skill_id": value}]
                with patch("apps.homework.services.notify") as notify, self.assertRaises(HomeworkError):
                    HomeworkService.create_from_template(self.template, self.child, self.due)
                notify.assert_not_called()
                self.assert_no_assignment()

    def test_invalid_saved_tag_shape_is_a_domain_error_before_writes(self):
        for tags in ({}, "invalid", [None], [[]], [{}]):
            with self.subTest(tags=tags):
                self.template.skill_tags = tags
                with self.assertRaises(HomeworkError):
                    HomeworkService.create_from_template(self.template, self.child, self.due)
                self.assert_no_assignment()

    def test_canonical_but_missing_id_is_checked_against_current_database(self):
        self.template.skill_tags += [{"skill_id": "999999"}]
        with self.assertRaises(HomeworkError):
            HomeworkService.create_from_template(self.template, self.child, self.due)
        self.assert_no_assignment()

    def test_new_rest_template_and_native_assignment_inputs_stay_strict(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.post("/api/homework-templates/", {"title": "New template", "subject": "other",
            "skill_tags": [{"skill_id": str(self.skill.pk)}]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(HomeworkTemplate.objects.count(), 1)
        with self.assertRaises(HomeworkError):
            HomeworkService.create_assignment(self.parent, {"title": "New assignment", "subject": "other",
                "assigned_to": self.child, "due_date": self.due, "skill_tags": [{"skill_id": str(self.skill.pk)}]})
        self.assert_no_assignment()

    def test_full_get_payload_with_saved_string_tags_can_update_title(self):
        client = APIClient()
        client.force_authenticate(self.parent)
        path = f"/api/homework-templates/{self.template.pk}/"
        payload = client.get(path).data
        self.assertEqual(payload["skill_tags"], [{"skill_id": str(self.skill.pk), "xp_amount": 23}])
        payload["title"] = "Renamed saved template"
        response = client.patch(path, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.template.refresh_from_db()
        self.assertEqual(self.template.title, "Renamed saved template")
        self.assertEqual(self.template.skill_tags, [{"skill_id": str(self.skill.pk), "xp_amount": 23}])

    def test_convert_saved_string_to_integer_retains_same_retired_reference(self):
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.patch(f"/api/homework-templates/{self.template.pk}/", {
            "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 23}],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.template.refresh_from_db()
        self.assertEqual(self.template.skill_tags, [{"skill_id": self.skill.pk, "xp_amount": 23}])
        with self.assertRaisesMessage(HomeworkError, "Retired taxonomy"):
            HomeworkService.create_from_template(self.template, self.child, self.due)
        self.assert_no_assignment()

    def test_saved_string_resend_retains_retired_reference_but_new_strings_remain_invalid(self):
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        other = Skill.objects.create(name="New template choice", category=self.category)
        client = APIClient()
        client.force_authenticate(self.parent)
        path = f"/api/homework-templates/{self.template.pk}/"
        response = client.patch(path, {"title": "Saved retired tag", "skill_tags": self.template.skill_tags}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        for value in (str(other.pk), "0" + str(self.skill.pk), True, float(self.skill.pk)):
            with self.subTest(value=value):
                response = client.patch(path, {"title": "Unsafe change", "skill_tags": [{"skill_id": value}]}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.template.refresh_from_db()
                self.assertEqual(self.template.title, "Saved retired tag")
        response = client.patch(path, {"skill_tags": self.template.skill_tags + [{"skill_id": other.pk}]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_malformed_old_tags_can_be_removed_without_retaining_them(self):
        self.template.skill_tags = [{"skill_id": "01"}, {"bad": "old data"}]
        self.template.save(update_fields=["skill_tags"])
        client = APIClient()
        client.force_authenticate(self.parent)
        response = client.patch(f"/api/homework-templates/{self.template.pk}/", {"skill_tags": []}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.template.refresh_from_db()
        self.assertEqual(self.template.skill_tags, [])
