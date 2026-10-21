"""Homework template MCP writes share native taxonomy and ownership admission."""
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import TestCase, override_settings

from apps.achievements.models import Skill, SkillCategory, Subject
from apps.homework.models import HomeworkAssignment, HomeworkSkillTag, HomeworkTemplate
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HomeworkTemplateAdmissionTests(TestCase):
    def setUp(self):
        household = make_family(parents=[{"username": "template-admission-parent", "is_staff": True},
                                        {"username": "template-admission-coparent", "is_staff": True}],
                                children=[{"username": "template-admission-child"}])
        self.parent, self.child = household.parents[0], household.children[0]
        self.coparent = household.parents[1]
        self.category = SkillCategory.objects.create(name="Template admission")
        self.skill = Skill.objects.create(name="Available template skill", category=self.category)

    def call(self, name, values, *, actor=None):
        with override_user(actor or self.parent):
            result = async_to_sync(mcp.call_tool)(name, {"params": values, "confirmation": True})
        return result.structuredContent if hasattr(result, "structuredContent") else result[1]

    def unavailable_choices(self):
        category = SkillCategory.objects.create(name="Archived template category", is_retired=True)
        subject = Subject.objects.create(name="Archived template subject", category=self.category, is_retired=True)
        return {
            "missing": 999999,
            "retired_skill": Skill.objects.create(name="Archived template skill", category=self.category, is_retired=True).pk,
            "retired_category": Skill.objects.create(name="Archived category child", category=category).pk,
            "retired_subject": Skill.objects.create(name="Archived subject child", category=self.category, subject=subject).pk,
        }

    def assert_no_assignments(self):
        self.assertFalse(HomeworkAssignment.objects.exists())
        self.assertFalse(HomeworkSkillTag.objects.exists())

    def assert_invalid(self, result):
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "invalid_request")
        self.assertIs(result["error"]["retryable"], False)

    def test_create_rejects_missing_and_retired_choices_without_writes(self):
        with patch("apps.homework.services.notify") as notify:
            for label, skill_id in self.unavailable_choices().items():
                with self.subTest(choice=label):
                    result = self.call("create_homework_template", {
                        "title": f"Invalid {label}", "skill_tags": [{"skill_id": skill_id}],
                    })
                    self.assert_invalid(result)
                    self.assertFalse(HomeworkTemplate.objects.exists())
            notify.assert_not_called()
        self.assert_no_assignments()

    def test_update_rejects_missing_and_retired_choices_without_partial_writes(self):
        template = HomeworkTemplate.objects.create(title="Keep title", created_by=self.parent,
                                                  skill_tags=[{"skill_id": self.skill.pk, "xp_amount": 23}])
        before = HomeworkTemplate.objects.values().get(pk=template.pk)
        with patch("apps.homework.services.notify") as notify:
            for label, skill_id in self.unavailable_choices().items():
                with self.subTest(choice=label):
                    result = self.call("update_homework_template", {
                        "template_id": template.pk, "title": "Must not save", "skill_tags": [{"skill_id": skill_id}],
                    })
                    self.assert_invalid(result)
                    self.assertEqual(HomeworkTemplate.objects.values().get(pk=template.pk), before)
            notify.assert_not_called()
        self.assert_no_assignments()

    def test_available_choices_preserve_response_defaults_and_creator(self):
        with patch("apps.homework.services.notify") as notify:
            result = self.call("create_homework_template", {
                "title": "Available template", "subject": "math", "skill_tags": [{"skill_id": self.skill.pk}],
            })
            self.assertEqual(set(result), {"id", "title", "description", "subject", "effort_level", "skill_tags",
                                           "created_at", "updated_at"})
            self.assertEqual(result["skill_tags"], [{"skill_id": self.skill.pk, "xp_amount": 15}])
            self.assertEqual((result["subject"], result["effort_level"]), ("math", 3))
            self.assertEqual(HomeworkTemplate.objects.get(pk=result["id"]).created_by_id, self.parent.pk)
            updated = self.call("update_homework_template", {
                "template_id": result["id"], "title": "Updated template",
                "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 27}],
            })
            self.assertEqual(updated["title"], "Updated template")
            self.assertEqual(updated["skill_tags"], [{"skill_id": self.skill.pk, "xp_amount": 27}])
            notify.assert_not_called()
        self.assert_no_assignments()

    def test_retained_retired_ids_allow_metadata_same_id_none_and_removal(self):
        tags = [{"skill_id": str(self.skill.pk), "xp_amount": 23}]
        template = HomeworkTemplate.objects.create(title="Retained template", created_by=self.parent, skill_tags=tags)
        Skill.objects.filter(pk=self.skill.pk).update(is_retired=True)
        for values in ({"title": "Metadata edit"}, {"title": "Ignore null tags", "skill_tags": None}):
            with self.subTest(values=values):
                result = self.call("update_homework_template", {"template_id": template.pk, **values})
                self.assertNotIn("error", result)
                self.assertEqual(result["skill_tags"], tags)
        result = self.call("update_homework_template", {
            "template_id": template.pk, "skill_tags": [{"skill_id": self.skill.pk, "xp_amount": 31}],
        })
        self.assertEqual(result["skill_tags"], [{"skill_id": self.skill.pk, "xp_amount": 31}])
        clone = self.call("create_homework_from_template", {
            "template_id": template.pk, "assigned_to_id": self.child.pk, "due_date": "2026-10-30",
        })
        self.assert_invalid(clone)
        cleared = self.call("update_homework_template", {"template_id": template.pk, "skill_tags": []})
        self.assertEqual(cleared["skill_tags"], [])
        self.assert_no_assignments()

    def test_duplicate_template_tags_keep_json_and_clone_still_fails_cleanly(self):
        tags = [{"skill_id": self.skill.pk, "xp_amount": 23}, {"skill_id": self.skill.pk, "xp_amount": 41}]
        created = self.call("create_homework_template", {"title": "Duplicate saved tags", "skill_tags": tags})
        self.assertEqual(created["skill_tags"], tags)
        updated = self.call("update_homework_template", {"template_id": created["id"], "skill_tags": tags})
        self.assertEqual(updated["skill_tags"], tags)
        with patch("apps.homework.services.notify") as notify:
            clone = self.call("create_homework_from_template", {
                "template_id": created["id"], "assigned_to_id": self.child.pk, "due_date": "2026-10-30",
            })
            self.assert_invalid(clone)
            notify.assert_not_called()
        self.assertEqual(HomeworkTemplate.objects.get(pk=created["id"]).skill_tags, tags)
        self.assert_no_assignments()

    def test_other_authors_and_missing_templates_remain_not_found(self):
        other = make_family(parents=[{"username": "foreign-template-owner", "is_staff": True}]).parents[0]
        template = HomeworkTemplate.objects.create(title="Private template", created_by=other)
        same_family = HomeworkTemplate.objects.create(title="Other author's template", created_by=self.coparent)
        for template_id in (template.pk, same_family.pk, 999999):
            with self.subTest(template_id=template_id):
                result = self.call("update_homework_template", {"template_id": template_id, "title": "Must not save"})
                self.assertEqual(result["error"]["code"], "not_found")
        template.refresh_from_db()
        self.assertEqual(template.title, "Private template")
        same_family.refresh_from_db()
        self.assertEqual(same_family.title, "Other author's template")
        self.assert_no_assignments()

    def test_children_cannot_create_or_update_templates(self):
        template = HomeworkTemplate.objects.create(title="Parent template", created_by=self.parent)
        for name, values in (("create_homework_template", {"title": "Must not save"}),
                             ("update_homework_template", {"template_id": template.pk, "title": "Must not save"})):
            with self.subTest(tool=name):
                result = self.call(name, values, actor=self.child)
                self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(HomeworkTemplate.objects.count(), 1)
        template.refresh_from_db()
        self.assertEqual(template.title, "Parent template")
        self.assert_no_assignments()

    def test_owner_change_before_locked_save_returns_not_found_without_overwriting(self):
        other = make_family(parents=[{"username": "new-template-owner", "is_staff": True}]).parents[0]
        template = HomeworkTemplate.objects.create(title="Keep title", created_by=self.parent)
        original_get = HomeworkTemplate.objects.get

        def change_owner_after_lookup(*args, **kwargs):
            result = original_get(*args, **kwargs)
            HomeworkTemplate.objects.filter(pk=template.pk).update(created_by=other)
            return result

        with patch.object(HomeworkTemplate.objects, "get", side_effect=change_owner_after_lookup):
            result = self.call("update_homework_template", {"template_id": template.pk, "title": "Must not save"})
        self.assertIn("error", result)
        self.assertEqual(result["error"]["code"], "not_found")
        template.refresh_from_db()
        self.assertEqual((template.title, template.created_by_id), ("Keep title", other.pk))
        self.assert_no_assignments()
